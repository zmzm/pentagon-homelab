import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync, writeFileSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { createGateway } from '../src/server.mjs';
import { createBroker, decodeLogs } from '../src/broker.mjs';
import { operation, executor } from '../src/operations.mjs';
import { redact, Failure } from '../src/common.mjs';

const env = {GATEWAY_TOKEN: 'a'.repeat(32), APPROVER_TOKEN: 'b'.repeat(32), BROKER_TOKEN: 'c'.repeat(32)};
const policy = {
  services: {vaultwarden: {container: 'vaultwarden', restart: 'CONFIRM'}, homepage: {container: 'homepage', restart: 'AUTO_SAFE'}, caddy: {container: 'caddy', restart: 'DENY'}},
  workflows: {'fixture-workflow': {permission: 'CONFIRM'}}, projects: {mentory: '/vaults/coding'},
};
async function fixture(t, execute) {
  const state = mkdtempSync(`${tmpdir()}/gateway-test-`);
  const {server} = createGateway({env, policy, state, execute});
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(async () => { await new Promise(resolve => server.close(resolve)); rmSync(state, {recursive: true}); });
  const request = async (path, {admin = false, method = 'GET', data, approval, token} = {}) => {
    const response = await fetch(`http://127.0.0.1:${server.address().port}${path}`, {method, headers: {authorization: `Bearer ${token || (admin ? env.APPROVER_TOKEN : env.GATEWAY_TOKEN)}`, 'content-type': 'application/json', 'x-session-id': 'session-1', 'x-user-request': encodeURIComponent('Sprawdź usługę'), ...(approval ? {'x-approval-id': approval} : {})}, body: data === undefined ? undefined : JSON.stringify(data)});
    return {status: response.status, data: await response.json()};
  };
  return {request, state};
}

test('unauthorized access and agent self-approval cannot call a tool', async t => {
  let calls = 0; const {request} = await fixture(t, async () => {calls++;});
  assert.equal((await request('/flowforge/workflows', {token: 'invalid'})).status, 401);
  assert.equal((await request('/approvals')).status, 401);
  assert.equal((await request('/homelab/services/missing')).status, 403);
  assert.equal((await request('/homelab/services/caddy/restart', {method: 'POST', data: {}})).status, 403);
  assert.equal(calls, 0);
});

test('confirmation is durable, bound to exact action and consumed once under concurrent replay', async t => {
  const calls = []; const {request, state} = await fixture(t, async (tool, args) => {calls.push({tool, args}); return {restarted: true};});
  const pending = await request('/homelab/services/vaultwarden/restart', {method: 'POST', data: {}});
  assert.equal(pending.data.error, 'APPROVAL_REQUIRED'); const id = pending.data.approvalId;
  assert.equal(calls.length, 0);
  assert.equal((await request(`/approvals/${id}`, {method: 'POST', data: {approve: true, operator: 'alice'}})).status, 401);
  assert.equal((await request(`/approvals/${id}`, {admin: true, method: 'POST', data: {approve: true, operator: 'alice'}})).status, 200);
  assert.equal(JSON.parse(readFileSync(`${state}/approvals/${id}.json`)).status, 'APPROVED');
  assert.equal((await request('/flowforge/run', {method: 'POST', data: {workflow: 'fixture-workflow'}, approval: id})).status, 403);
  const results = await Promise.all([1,2].map(() => request('/homelab/services/vaultwarden/restart', {method: 'POST', data: {}, approval: id})));
  assert.deepEqual(results.map(r => r.status).sort(), [200,403]); assert.equal(calls.length, 1);
  assert.equal(JSON.parse(readFileSync(`${state}/approvals/${id}.json`)).status, 'DONE');
  const records = readFileSync(`${state}/audit.jsonl`, 'utf8').trim().split('\n').map(JSON.parse);
  assert.ok(records.some(r => r.approvedByUser && r.durationMs >= 0));
  assert.ok(records.some(r => r.userRequest === 'Sprawdź usługę'));
});

test('approved decisions survive restart, and rejected/expired decisions fail closed', async t => {
  const {request, state} = await fixture(t, async () => ({}));
  const pending = async () => (await request('/homelab/services/vaultwarden/restart', {method: 'POST', data: {}})).data.approvalId;
  const rejected = await pending();
  await request(`/approvals/${rejected}`, {admin: true, method: 'POST', data: {approve: false, operator: 'alice'}});
  assert.equal((await request('/homelab/services/vaultwarden/restart', {method: 'POST', data: {}, approval: rejected})).status, 403);
  const approved = await pending();
  await request(`/approvals/${approved}`, {admin: true, method: 'POST', data: {approve: true, operator: 'alice'}});
  let calls = 0;
  const fresh = createGateway({env, policy, state, execute: async () => {calls++; return {};}});
  await fresh.invoke('homelab.restartService', {service: 'vaultwarden'}, {sessionId: 'session-1', userRequest: 'restart'}, approved);
  assert.equal(calls, 1);
  const expired = await pending();
  const path = `${state}/approvals/${expired}.json`;
  const record = JSON.parse(readFileSync(path)); record.status = 'APPROVED'; record.expiresAt = Date.now() - 1;
  writeFileSync(path, JSON.stringify(record));
  await assert.rejects(fresh.invoke('homelab.restartService', {service: 'vaultwarden'}, {sessionId: 'session-1', userRequest: 'restart'}, expired), /INVALID_APPROVAL/);
  assert.equal(calls, 1);
});

test('an unavailable audit sink prevents an AUTO_SAFE side effect', async t => {
  let calls = 0;
  const {request, state} = await fixture(t, async () => {calls++; return {};});
  mkdirSync(`${state}/audit.jsonl`);
  const result = await request('/homelab/services/homepage/restart', {method: 'POST', data: {}});
  assert.equal(result.status, 503); assert.equal(result.data.error, 'AUDIT_UNAVAILABLE'); assert.equal(calls, 0);
});

test('safe operations and structured failures are audited; secrets are redacted', async t => {
  const {request, state} = await fixture(t, async tool => {
    if (tool === 'knowledge.search') throw new Failure('KNOWLEDGE_FAILED', 502);
    return {password: 'hidden', logs: `token=hidden\nBearer private\n${env.GATEWAY_TOKEN}`};
  });
  const restart = await request('/homelab/services/homepage/restart', {method: 'POST', data: {}});
  assert.equal(restart.data.success, true);
  assert.ok(!JSON.stringify(restart.data).includes('hidden')); assert.ok(!JSON.stringify(restart.data).includes(env.GATEWAY_TOKEN));
  const failed = await request('/knowledge/search', {method: 'POST', data: {query: 'find token=private', project: 'mentory'}});
  assert.equal(failed.status, 502); assert.equal(failed.data.error, 'KNOWLEDGE_FAILED');
  const audit = readFileSync(`${state}/audit.jsonl`, 'utf8');
  assert.ok(!audit.includes('private')); assert.ok(audit.includes('"resultStatus":"failed"'));
});

test('invalid input cannot reach upstream executors', async t => {
  let calls = 0; const {request} = await fixture(t, async () => {calls++; return {};});
  for (const path of ['/homelab/services/vaultwarden/logs?lines=1000', '/homelab/services/vaultwarden/logs?lines=NaN', '/homelab/services/vaultwarden/logs?since=yesterday', '/homelab/services/vaultwarden/logs?command=rm']) assert.equal((await request(path)).status, 400);
  assert.equal((await request('/homelab/services/vaultwarden/restart', {method: 'POST', data: {approvedByUser: true}})).status, 400);
  assert.equal((await request('/knowledge/search', {method: 'POST', data: {query: 'x', project: 'mentory', limit: -1}})).status, 400);
  assert.equal((await request('/knowledge/search', {method: 'POST', data: {query: 'x'.repeat(70000), project: 'mentory'}})).status, 413);
  assert.equal(calls, 0);
});

test('broker limits Docker API surface, strips inspect secrets and redacts configured log secrets', async t => {
  const seen = []; const request = async (path, method) => {
    seen.push({path, method});
    if (path.endsWith('/json')) return Buffer.from(JSON.stringify({State: {Status: 'running', Running: true, Health: {Status: 'healthy'}}, Config: {Tty: true, Env: ['PASSWORD=veryprivatevalue']}}));
    if (path.includes('/logs?')) return Buffer.from('password=veryprivatevalue\nstandalone veryprivatevalue');
    return Buffer.alloc(0);
  };
  const server = createBroker(env, policy, request); await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  const call = async (tool, args) => {
    const res = await fetch(`http://127.0.0.1:${server.address().port}/execute`, {method: 'POST', headers: {authorization: `Bearer ${env.BROKER_TOKEN}`, 'content-type': 'application/json'}, body: JSON.stringify({tool, arguments: args})}); return {status: res.status, data: await res.json()};
  };
  const info = await call('homelab.inspectService', {service: 'vaultwarden'});
  assert.equal(info.data.health, 'healthy'); assert.ok(!JSON.stringify(info.data).includes('Config'));
  assert.ok(!JSON.stringify((await call('homelab.getLogs', {service: 'vaultwarden', lines: 10})).data).includes('veryprivatevalue'));
  assert.equal((await call('homelab.restartService', {service: 'caddy'})).status, 403);
  assert.equal((await call('homelab.inspectService', {service: '../etc'})).status, 403);
  assert.equal((await call('flowforge.run', {workflow: 'shell'})).status, 404);
  assert.equal(seen.length, 3);
});

test('Docker multiplex logs are decoded and malformed frames rejected', () => {
  const header = Buffer.alloc(8); header[0] = 1; header.writeUInt32BE(5, 4);
  assert.equal(decodeLogs(Buffer.concat([header, Buffer.from('hello')]), false), 'hello');
  assert.throws(() => decodeLogs(header, false), /INVALID_DOCKER_LOGS/);
});

test('workflow discovery and missing backend fail honestly without executing a substitute', async () => {
  const execute = executor({}, policy);
  assert.deepEqual(await execute('flowforge.listWorkflows', {}), {workflows: [{name: 'fixture-workflow', permission: 'CONFIRM'}]});
  await assert.rejects(execute('flowforge.run', {workflow: 'fixture-workflow'}), /FLOWFORGE_NOT_CONFIGURED/);
  assert.throws(() => operation('flowforge.run', {workflow: 'arbitrary'}, policy), /WORKFLOW_NOT_ALLOWED/);
});

test('redaction removes bearer values, sensitive fields and private key blocks', () => {
  const value = redact({apiKey: 'private', nested: ['Authorization=private', 'Bearer private', '-----BEGIN PRIVATE KEY-----\nprivate\n-----END PRIVATE KEY-----']});
  assert.ok(!JSON.stringify(value).includes('private'));
});

test('operator execution uses exact stored action and records verified Matrix evidence', async t => {
  const calls = []; const {request, state} = await fixture(t, async (tool,args) => {calls.push({tool,args}); return {restarted:true};});
  const {data} = await request('/homelab/services/vaultwarden/restart', {method:'POST',data:{}});
  const id = data.approvalId;
  assert.equal((await request(`/approvals/${id}/execute`, {method:'POST',data:{}})).status,401);
  await request(`/approvals/${id}`,{admin:true,method:'POST',data:{approve:true,operator:'@owner:server',matrixEventId:'$decision',matrixRoomId:'!room:server',promptEventId:'$prompt'}});
  assert.equal((await request(`/approvals/${id}/execute`,{admin:true,method:'POST',data:{}})).data.success,true);
  assert.deepEqual(calls,[{tool:'homelab.restartService',args:{service:'vaultwarden'}}]);
  assert.equal((await request(`/approvals/${id}`,{admin:true})).data.status,'DONE');
  assert.equal((await request(`/approvals/${id}/execute`,{admin:true,method:'POST',data:{}})).status,403);
  assert.equal(calls.length,1);
  const audit=readFileSync(`${state}/audit.jsonl`,'utf8'); assert.ok(audit.includes('"matrixEventId":"$decision"'));
});

test('task-analysis requires a concrete Mentory task and immutable task content hash', () => {
  const planningPolicy = {...policy, workflows: {'task-analysis': {permission: 'CONFIRM'}}};
  assert.throws(() => operation('flowforge.run', {workflow:'task-analysis',input:{project:'mentory',task_id:'test'}}, planningPolicy), /INVALID_INPUT/);
  assert.equal(operation('flowforge.run', {workflow:'task-analysis',input:{project:'mentory',task_id:'test',task_sha256:'a'.repeat(64),context:'retrieved evidence'}}, planningPolicy),'CONFIRM');
  assert.equal(operation('flowforge.listTasks', {}, planningPolicy),'READ');
  assert.equal(operation('flowforge.getRun', {run_id:'12345678-1234-1234-1234-123456789abc'}, planningPolicy),'READ');
});
