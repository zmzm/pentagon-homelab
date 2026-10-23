import http from 'node:http';
import { randomUUID } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync, renameSync, readdirSync, appendFileSync, openSync, closeSync, fsyncSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { Failure, check, authenticate, object, str, body, redact, send } from './common.mjs';
import { operation, validatePolicy, executor } from './operations.mjs';
import { uncertainRestart } from './restart.mjs';

const canonical = value => JSON.stringify(value, function (_key, item) {
  return item && typeof item === 'object' && !Array.isArray(item) ? Object.fromEntries(Object.entries(item).sort(([a],[b]) => a.localeCompare(b))) : item;
});
export function createGateway({env, policy, execute = executor(env, policy), state = '/state'}) {
  validatePolicy(policy);
  check(env.GATEWAY_TOKEN?.length >= 32 && env.APPROVER_TOKEN?.length >= 32 && env.GATEWAY_TOKEN !== env.APPROVER_TOKEN, 'INVALID_AUTH_CONFIG');
  mkdirSync(`${state}/approvals`, {recursive: true, mode: 0o700});
  const secrets = Object.entries(env).filter(([k]) => /TOKEN|KEY|PASSWORD|SECRET/.test(k)).map(([,v]) => v);
  const counts = {tool_calls_total: 0, tool_call_errors_total: 0, tool_call_duration_ms_sum: 0, approvals_requested: 0, approvals_rejected: 0, workflow_runs: 0};
  function audit(record) {
    appendFileSync(`${state}/audit.jsonl`, JSON.stringify(redact({timestamp: new Date().toISOString(), ...record}, secrets)) + '\n', {mode: 0o600, flush: true});
  }
  function load(id) { check(/^[0-9a-f-]{36}$/.test(id), 'INVALID_APPROVAL'); try { return JSON.parse(readFileSync(`${state}/approvals/${id}.json`)); } catch { throw new Failure('APPROVAL_NOT_FOUND', 404); } }
  function save(record) {
    const path = `${state}/approvals/${record.id}.json`;
    writeFileSync(`${path}.tmp`, JSON.stringify(record), {mode: 0o600, flush: true}); renameSync(`${path}.tmp`, path);
    const directory = openSync(`${state}/approvals`, 'r');
    try { fsyncSync(directory); } finally { closeSync(directory); }
  }
  async function invoke(tool, args, context, approvalId) {
    const start = performance.now(); let permission, approved = false;
    counts.tool_calls_total++;
    const entry = {sessionId: context.sessionId, userRequest: context.userRequest, tool, arguments: args, requiresApproval: false};
    try {
      permission = operation(tool, args, policy); entry.requiresApproval = permission === 'CONFIRM';
      check(permission !== 'DENY', 'POLICY_DENIED', 403);
      if (permission === 'CONFIRM') {
        if (!approvalId) {
          const request = {id: randomUUID(), tool, arguments: args, context, status: 'PENDING', expiresAt: Date.now() + 600000};
          save(request); counts.approvals_requested++;
          audit({...entry, resultStatus: 'denied', error: 'APPROVAL_REQUIRED', approvalId: request.id, durationMs: performance.now() - start});
          return {success: false, error: 'APPROVAL_REQUIRED', approvalId: request.id, expiresAt: request.expiresAt, message: 'A trusted listener posts the exact action in Matrix. The authorized user can tap the seeded ✅ (approve) or ❌ (reject) reaction on that prompt, or use !approve <approvalId> / !reject <approvalId>. Execution and results are handled by that listener; do not create a second request.'};
        }
        const record = load(approvalId);
        check(record.status === 'APPROVED' && record.expiresAt > Date.now() && record.tool === tool && canonical(record.arguments) === canonical(args) && record.context.sessionId === context.sessionId, 'INVALID_APPROVAL', 403);
        // Consume durably before awaiting a side effect. A crash cannot replay it.
        record.status = 'CONSUMED'; save(record); approved = true;
      }
      audit({...entry, event: 'execution_started', approvedByUser: approved, approvalId, resultStatus: 'success'});
      let executed;
      try { executed = await execute(tool, args); }
      catch (err) {
        if (tool !== 'homelab.restartService') throw err;
        // The broker response may have been lost after Docker accepted the write.
        executed = uncertainRestart(args.service);
      }
      const result = redact(executed, secrets);
      check(Buffer.byteLength(JSON.stringify(result)) <= 131072, 'OUTPUT_TOO_LARGE', 502);
      const uncertain = tool === 'homelab.restartService' && result.restart?.status === 'uncertain';
      const outcome = {success: !uncertain, ...(uncertain ? {error: 'RESTART_UNCERTAIN'} : {}), data: result};
      if (uncertain) counts.tool_call_errors_total++;
      audit({...entry, resultStatus: uncertain ? 'uncertain' : 'success', approvedByUser: approved, approvalId, durationMs: performance.now() - start});
      if (approved) save({...load(approvalId), status: uncertain ? 'UNCERTAIN' : 'DONE', outcome});
      if (tool === 'flowforge.run') counts.workflow_runs++;
      return outcome;
    } catch (err) {
      counts.tool_call_errors_total++;
      const failure = err instanceof Failure ? err : new Failure('INTERNAL_ERROR', 500);
      audit({...entry, resultStatus: failure.status < 500 ? 'denied' : 'failed', error: failure.code, approvedByUser: approved, approvalId, durationMs: performance.now() - start});
      if (approved) save({...load(approvalId), status: 'FAILED', outcome: {success: false, error: failure.code}});
      throw failure;
    } finally { counts.tool_call_duration_ms_sum += performance.now() - start; }
  }
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, 'http://gateway'); const path = url.pathname;
      if (req.method === 'GET' && path === '/health') return send(res, 200, {success: true, status: 'alive'});
      const admin = path.startsWith('/approvals'); authenticate(req, admin ? env.APPROVER_TOKEN : env.GATEWAY_TOKEN);
      if (admin) {
        if (req.method === 'GET' && path === '/approvals') {
          const requests = readdirSync(`${state}/approvals`).filter(p => p.endsWith('.json')).map(p => load(p.slice(0, -5))).filter(r => r.status === 'PENDING' && r.expiresAt > Date.now()).sort((a,b) => a.expiresAt - b.expiresAt).slice(0,100);
          return send(res, 200, redact({requests}, secrets));
        }
        const match = path.match(/^\/approvals\/([0-9a-f-]{36})(\/(?:execute|workflow))?$/); check(match, 'NOT_FOUND', 404);
        const record = load(match[1]);
        if (req.method === 'GET' && match[2] === '/workflow') {
          check(record.tool === 'flowforge.run' && record.outcome?.data?.run_id, 'NO_WORKFLOW_RUN', 404);
          return send(res, 200, await invoke('flowforge.getRun', {run_id: record.outcome.data.run_id}, record.context));
        }
        if (req.method === 'GET' && !match[2]) return send(res, 200, redact(record, secrets));
        check(req.method === 'POST', 'METHOD_NOT_ALLOWED', 405);
        if (match[2] === '/execute') {
          object(await body(req), []);
          return send(res, 200, await invoke(record.tool, record.arguments, record.context, record.id));
        }
        check(!match[2], 'NOT_FOUND', 404);
        const decision = await body(req); object(decision, ['approve', 'operator', 'matrixEventId', 'matrixRoomId', 'promptEventId']); check(typeof decision.approve === 'boolean'); str(decision.operator, 100);
        if (decision.matrixEventId !== undefined) {
          str(decision.matrixEventId, 255); str(decision.matrixRoomId, 255); str(decision.promptEventId, 255);
        }
        check(record.status === 'PENDING' && record.expiresAt > Date.now(), 'APPROVAL_EXPIRED_OR_USED', 409);
        audit({sessionId: record.context.sessionId, userRequest: record.context.userRequest, tool: record.tool, arguments: record.arguments, resultStatus: decision.approve ? 'success' : 'denied', requiresApproval: true, approvedByUser: decision.approve, operator: decision.operator, matrixEventId: decision.matrixEventId, matrixRoomId: decision.matrixRoomId, promptEventId: decision.promptEventId, event: 'approval_decision', approvalId: record.id});
        record.status = decision.approve ? 'APPROVED' : 'REJECTED'; record.decision = decision; save(record);
        if (!decision.approve) counts.approvals_rejected++;
        return send(res, 200, {success: true, status: record.status});
      }
      if (path === '/metrics' && req.method === 'GET') {
        res.writeHead(200, {'content-type': 'text/plain; version=0.0.4'}); return res.end(Object.entries(counts).map(([key,value]) => `${key} ${value}`).join('\n') + '\n');
      }
      const context = {sessionId: str(decodeURIComponent(req.headers['x-session-id'] || ''), 200), userRequest: str(decodeURIComponent(req.headers['x-user-request'] || ''), 2000)};
      let tool, args;
      if (req.method === 'POST' && path === '/knowledge/search') { tool = 'knowledge.search'; args = await body(req); }
      else if (req.method === 'POST' && path === '/flowforge/run') { tool = 'flowforge.run'; args = await body(req); }
      else if (req.method === 'GET' && path === '/flowforge/tasks') { tool = 'flowforge.listTasks'; args = {}; }
      else if (req.method === 'GET' && /^\/flowforge\/runs\/[0-9a-f-]{36}$/.test(path)) { tool = 'flowforge.getRun'; args = {run_id: path.split('/').at(-1)}; }
      else if (req.method === 'GET' && path === '/flowforge/workflows') { tool = 'flowforge.listWorkflows'; args = {}; }
      else if (path === '/homelab/services') {
        check(req.method === 'GET', 'METHOD_NOT_ALLOWED', 405);
        check(!url.search, 'INVALID_INPUT');
        tool = 'homelab.listServices'; args = {};
      }
      else {
        const match = path.match(/^\/homelab\/services\/([a-z0-9_-]+)(?:\/(logs|restart))?$/); check(match, 'NOT_FOUND', 404);
        check(match[2] === 'restart' ? req.method === 'POST' : req.method === 'GET', 'METHOD_NOT_ALLOWED', 405);
        tool = match[2] === 'restart' ? 'homelab.restartService' : match[2] === 'logs' ? 'homelab.getLogs' : 'homelab.inspectService';
        args = {service: match[1]};
        if (match[2] === 'restart') object(await body(req), []);
        for (const key of url.searchParams.keys()) check(match[2] === 'logs' && ['lines','since'].includes(key));
        if (url.searchParams.has('lines')) args.lines = Number(url.searchParams.get('lines'));
        if (url.searchParams.has('since')) args.since = url.searchParams.get('since');
      }
      send(res, 200, await invoke(tool, args, context, req.headers['x-approval-id']));
    } catch (err) {
      const failure = err instanceof Failure ? err : new Failure('INTERNAL_ERROR', 500);
      // Transport/authentication failures are audited without recording attacker-supplied bodies.
      try { audit({sessionId: 'transport', userRequest: '', tool: 'http', arguments: {}, resultStatus: failure.status < 500 ? 'denied' : 'failed', requiresApproval: false, error: failure.code}); }
      catch { return send(res, 503, {success: false, error: 'AUDIT_UNAVAILABLE'}); }
      send(res, failure.status, {success: false, error: failure.code, message: failure.code.replaceAll('_', ' ')});
    }
  });
  server.requestTimeout = 35000; server.headersTimeout = 10000;
  return {server, invoke};
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const policy = JSON.parse(readFileSync(process.env.POLICY_PATH || '/config/policy.json'));
  createGateway({env: process.env, policy}).server.listen(8080, '0.0.0.0');
}
