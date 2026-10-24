import { mkdirSync, readFileSync, writeFileSync, renameSync, openSync, fsyncSync, closeSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { bounded, check } from './common.mjs';
import { planNames, workflowDelivery, workflowFallback, restartResultText } from './matrix-approval-messages.mjs';

const markdownType = 'text/markdown; charset=utf-8';

export function decisionFor(event, room, expectedRoom, users, prompts, now) {
  if (room !== expectedRoom || !users.includes(event.sender) || event.unsigned?.redacted_because) return null;
  const content = event.content || {};
  let id, approve;
  if (event.type === 'm.reaction') {
    const relation = content['m.relates_to'];
    if (relation?.rel_type !== 'm.annotation' || !['✅', '❌'].includes(relation.key)) return null;
    const matches = Object.entries(prompts).filter(([, prompt]) => prompt.eventId && prompt.eventId === relation.event_id);
    if (matches.length !== 1) return null;
    id = matches[0][0]; approve = relation.key === '✅';
  } else if (event.type === 'm.room.message') {
    if (content.msgtype !== 'm.text' || content['m.relates_to']?.rel_type === 'm.replace') return null;
    const match = content.body?.trim().match(/^!(approve|reject) ([0-9a-f-]{36})$/);
    if (!match) return null;
    id = match[2]; approve = match[1] === 'approve';
  } else return null;
  if (!event.event_id || event.event_id.length > 255) return null;
  const prompt = prompts[id];
  if (!prompt?.eventId || !Number.isFinite(prompt.expiresAt) || prompt.expiresAt <= now || !Number.isFinite(event.origin_server_ts) || event.origin_server_ts < prompt.preparedAt || event.origin_server_ts > now + 60000 || now - event.origin_server_ts > 600000) return null;
  if (prompt.decision || prompt.finished) return null;
  return {id, approve, operator: event.sender, matrixEventId: event.event_id, matrixRoomId: room, promptEventId: prompt.eventId};
}

export class ApprovalRelay {
  constructor({room, users, matrix, gateway, state, save, now = Date.now, log = entry => process.stdout.write(JSON.stringify(entry) + '\n')}) {
    Object.assign(this, {room, users, matrix, gateway, state, save, now, log});
    this.state.prompts ||= {};
  }
  async processOperation(id, stage, operation) {
    try { await operation(); }
    catch {
      // Keep retry state and execution claims intact; never log upstream errors or payloads.
      this.log({timestamp: new Date(this.now()).toISOString(), event: 'approval_relay_operation_failed',
        code: 'APPROVAL_RELAY_OPERATION_FAILED', approvalId: id, stage});
    }
  }
  async sync() {
    const filter = {room: {rooms: [this.room], timeline: {types: ['m.room.message', 'm.reaction'], limit: 100}, state: {types: []}, ephemeral: {types: []}}, presence: {types: []}, account_data: {types: []}};
    const query = new URLSearchParams({timeout: '0', filter: JSON.stringify(filter), set_presence: 'offline'});
    if (this.state.since) query.set('since', this.state.since);
    return this.matrix('GET', `/sync?${query}`);
  }
  async sendEvent(id, suffix, type, content) {
    // Check encryption before every send, including retries. Never leak plaintext into encrypted rooms.
    await this.checkRoom();
    return this.matrix('PUT', `/rooms/${encodeURIComponent(this.room)}/send/${type}/${encodeURIComponent(`approval-${id}-${suffix}`)}`, content);
  }
  async checkRoom() {
    const state = await this.matrix('GET', `/rooms/${encodeURIComponent(this.room)}/state`);
    check(!state.some(event => event.type === 'm.room.encryption'), 'ENCRYPTED_APPROVAL_ROOM');
  }
  async notify(id, suffix, text) {
    return this.sendEvent(id, suffix, 'm.room.message', {msgtype: 'm.notice', body: text});
  }
  async controls(id, prompt) {
    prompt.controls ||= {};
    for (const [action, key] of [['approve', '✅'], ['reject', '❌']]) {
      if (prompt.controls[action]) continue;
      const response = await this.sendEvent(id, `control-${action}`, 'm.reaction', {'m.relates_to': {rel_type: 'm.annotation', event_id: prompt.eventId, key}});
      check(response.event_id, 'MISSING_CONTROL_EVENT');
      prompt.controls[action] = response.event_id; this.save(this.state);
    }
  }
  async reconcile(id, prompt) {
    const record = await this.gateway('GET', `/approvals/${id}`);
    if (record.status === 'PENDING') {
      const decision = {...prompt.decision}; delete decision.id;
      await this.gateway('POST', `/approvals/${id}`, decision);
      return this.reconcile(id, prompt);
    }
    if (record.status === 'APPROVED') {
      // Claim once locally before the HTTP call. If delivery is ambiguous, read gateway state;
      // never blindly replay an execution request after a network failure.
      if (!prompt.executionAttempted) {
        prompt.executionAttempted = true; this.save(this.state);
        await this.gateway('POST', `/approvals/${id}/execute`, {});
      }
      return this.finish(id, prompt, await this.gateway('GET', `/approvals/${id}`));
    }
    return this.finish(id, prompt, record);
  }
  async finish(id, prompt, record) {
    let text;
    if (record.status === 'REJECTED') text = `Rejected ${id}. No action was executed.`;
    else if (record.tool === 'homelab.restartService' &&
      (record.status === 'UNCERTAIN' || record.outcome?.data?.restart)) text = restartResultText(id, record);
    else if (['DONE', 'FAILED'].includes(record.status)) text = `Approval ${id}: ${record.status}\n${JSON.stringify(record.outcome).slice(0, 10000)}`;
    else if (record.expiresAt <= this.now()) text = `Approval ${id} expired. No new execution was attempted.`;
    else text = `Approval ${id}: execution outcome is uncertain (${record.status}). Inspect safely; do not retry the action automatically.`;
    if (record.tool === 'flowforge.run' && record.outcome?.data?.run_id) {
      text = `Approved ${id}. FlowForge planning run ${record.outcome.data.run_id} started. Only concept and grounded planning steps run; the source repository stays read-only. I will post the completed plans here.`;
    }
    await this.notify(id, 'result', text);
    if (record.tool === 'flowforge.run' && record.outcome?.data?.run_id) prompt.workflowPending = true;
    prompt.finished = true; this.save(this.state);
  }
  async workflowResult(id, prompt) {
    if (!prompt.workflowDelivery) {
      const {data: run} = await this.gateway('GET', `/approvals/${id}/workflow`);
      if (run.status === 'RUNNING') return;
      check(['DONE', 'FAILED'].includes(run.status), 'INVALID_WORKFLOW_STATUS');
      prompt.workflowDelivery = workflowDelivery(run);
      // Freeze the sanitized bytes and message bodies before the first send so
      // retries keep both the same transaction IDs and the same content.
      this.save(this.state);
    }
    const delivery = prompt.workflowDelivery;
    await this.workflowNotice(id, 'workflow-completion', delivery.notice);
    if (delivery.outcome === 'FAILED') {
      delivery.status = 'delivered'; prompt.workflowPending = false; this.save(this.state); return;
    }
    for (const file of delivery.files) {
      if (file.eventId) continue;
      await this.processOperation(id, 'workflow_attachment', async () => {
        await this.uploadPlan(file);
        if (file.uploadStatus !== 'uploaded') return;
        try {
          const response = await this.sendEvent(id, `workflow-file-${file.name}`, 'm.room.message', {
            msgtype: 'm.file', body: file.name, filename: file.name, url: file.mxc,
            info: {mimetype: markdownType, size: Buffer.byteLength(file.text, 'utf8')},
          });
          check(response.event_id, 'MISSING_FILE_EVENT');
          file.eventId = response.event_id; delete file.sendError;
        } catch {
          file.sendError = 'MATRIX_SEND_UNCONFIRMED'; this.save(this.state);
          throw new Error('MATRIX_SEND_UNCONFIRMED');
        }
        this.save(this.state);
      });
    }
    const complete = planNames.every(name => delivery.files.some(file => file.name === name && file.eventId));
    delivery.status = complete ? 'delivered' : 'failed'; this.save(this.state);
    if (!complete) {
      // Persist this body too: subsequent progress must not change an ambiguous
      // send's payload under the same Matrix transaction ID.
      delivery.fallback ||= workflowFallback(delivery); this.save(this.state);
      await this.workflowNotice(id, 'workflow-fallback', delivery.fallback);
    }
    const retryable = delivery.files.some(file => !file.eventId && ['pending', 'uploaded'].includes(file.uploadStatus));
    prompt.workflowPending = !complete && retryable; this.save(this.state);
  }
  async workflowNotice(id, suffix, message) {
    if (message.eventId) return;
    try {
      const response = await this.notify(id, suffix, message.body);
      check(response.event_id, 'MISSING_WORKFLOW_EVENT');
      message.eventId = response.event_id; delete message.error;
    } catch {
      message.error = 'MATRIX_SEND_UNCONFIRMED'; this.save(this.state);
      throw new Error('MATRIX_SEND_UNCONFIRMED');
    }
    this.save(this.state);
  }
  async uploadPlan(file) {
    // POST /upload has no transaction ID. A persisted claim without a saved URI
    // means the upload may have succeeded; never repeat it automatically.
    if (file.uploadStatus === 'uploading') {
      file.uploadStatus = 'uncertain'; file.uploadError = 'MATRIX_UPLOAD_UNCONFIRMED'; this.save(this.state);
    }
    if (file.uploadStatus !== 'pending' || file.retryAt > this.now()) return;
    await this.checkRoom();
    file.uploadStatus = 'uploading'; file.uploadAttempts++; this.save(this.state);
    try {
      const response = await this.matrix('POST', `/_matrix/media/v3/upload?filename=${encodeURIComponent(file.name)}`,
        Buffer.from(file.text, 'utf8'), {contentType: markdownType});
      check(typeof response.content_uri === 'string' && /^mxc:\/\/[^/\s?#]+\/[^/\s?#]+$/.test(response.content_uri), 'INVALID_MEDIA_URI');
      file.mxc = response.content_uri; file.uploadStatus = 'uploaded'; delete file.uploadError; delete file.retryAt;
    } catch (error) {
      const rejected = error.httpStatus >= 400 && error.httpStatus < 500 && error.httpStatus !== 408;
      file.uploadStatus = rejected ? 'failed' : 'uncertain';
      file.uploadError = rejected ? `MATRIX_UPLOAD_HTTP_${error.httpStatus}` : 'MATRIX_UPLOAD_UNCONFIRMED';
      // Only an explicit rate-limit rejection is automatically replayable.
      if (error.httpStatus === 429 && file.uploadAttempts < 3) {
        file.uploadStatus = 'pending'; file.retryAt = this.now() + Math.max(30000, error.retryAfterMs || 0);
      }
    }
    this.save(this.state);
  }
  async tick() {
    if (!this.state.since) {
      this.state.since = (await this.sync()).next_batch; this.save(this.state);
    }
    const pending = (await this.gateway('GET', '/approvals')).requests;
    for (const request of pending) {
      await this.processOperation(request.id, 'prompt', async () => {
        let prompt = this.state.prompts[request.id];
        if (!prompt) {
          prompt = this.state.prompts[request.id] = {preparedAt: this.now(), expiresAt: request.expiresAt}; this.save(this.state);
        }
        if (!prompt.eventId && !prompt.finished) {
          const description = JSON.stringify({tool: request.tool, arguments: request.arguments, userRequest: request.context.userRequest}, null, 2);
          // Never truncate a proposed action: approval must present every argument.
          if (description.length > 10000) {
            await this.notify(request.id, 'oversize', `Approval ${request.id} is too large to review safely in Matrix. No action will execute; use the operator API to review or reject it.`);
            prompt.finished = true; this.save(this.state); return;
          }
          const response = await this.notify(request.id, 'prompt', `Approval required (expires ${new Date(request.expiresAt).toISOString()})\n${description}\nTap ✅ to approve this exact action, or ❌ to reject. Your tap takes effect immediately; removing a reaction does not undo it.\nText fallback:\n!approve ${request.id}\n!reject ${request.id}`);
          prompt.eventId = response.event_id; check(prompt.eventId, 'MISSING_PROMPT_EVENT'); this.save(this.state);
        }
        if (prompt.eventId && !prompt.finished && !prompt.decision) await this.controls(request.id, prompt);
      });
    }
    const response = await this.sync();
    const timeline = response.rooms?.join?.[this.room]?.timeline;
    // A limited sync has a gap: skip its commands rather than acting on incomplete history.
    for (const event of timeline?.limited ? [] : timeline?.events || []) {
      const decision = decisionFor(event, this.room, this.room, this.users, this.state.prompts, this.now());
      if (decision) { this.state.prompts[decision.id].decision = decision; this.save(this.state); }
    }
    this.state.since = response.next_batch; this.save(this.state);
    for (const [id, prompt] of Object.entries(this.state.prompts)) {
      if (prompt.workflowPending) await this.processOperation(id, 'workflow_result', () => this.workflowResult(id, prompt));
      else if (prompt.decision && !prompt.finished) await this.processOperation(id, 'reconcile', () => this.reconcile(id, prompt));
      else if (!prompt.finished && prompt.expiresAt <= this.now()) await this.processOperation(id, 'expiry', () => this.finish(id, prompt, {status: 'EXPIRED', expiresAt: prompt.expiresAt}));
    }
    // Bound local bookkeeping; gateway audit remains authoritative.
    const done = Object.entries(this.state.prompts).filter(([, p]) => p.finished && !p.workflowPending &&
      (!p.workflowDelivery || p.workflowDelivery.status === 'delivered'));
    for (const [id] of done.slice(0, Math.max(0, done.length - 200))) delete this.state.prompts[id];
    this.save(this.state);
  }
}

export function jsonClient(base, token, prefix = '') {
  return async (method, path, payload, {contentType = 'application/json'} = {}) => {
    const response = await fetch(base + (path.startsWith('/_matrix/media/') ? '' : prefix) + path, {method, headers: {authorization: `Bearer ${token}`, 'content-type': contentType, 'user-agent': 'Pentagon-Approval-Relay/1.0'}, body: payload === undefined ? undefined : Buffer.isBuffer(payload) ? payload : JSON.stringify(payload), redirect: 'error', signal: AbortSignal.timeout(35000)});
    if (!response.ok) {
      // Expose status/retry timing only, never upstream error text or credentials.
      let retryAfterMs = Number(response.headers.get('retry-after')) * 1000;
      try {
        const error = JSON.parse((await bounded(response.body, 16384)).toString());
        if (Number.isFinite(error.retry_after_ms)) retryAfterMs = Math.max(retryAfterMs, error.retry_after_ms);
      } catch {}
      throw Object.assign(new Error('APPROVAL_RELAY_HTTP_FAILED'), {httpStatus: response.status,
        retryAfterMs: Number.isFinite(retryAfterMs) ? Math.min(3600000, Math.max(0, retryAfterMs)) : 0});
    }
    const raw = await bounded(response.body, 1048576);
    return JSON.parse(raw.toString());
  };
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const env = process.env;
  check(env.APPROVER_TOKEN?.length >= 32 && env.MATRIX_ACCESS_TOKEN && env.MATRIX_HOME_ROOM && env.MATRIX_ALLOWED_USERS, 'INVALID_APPROVAL_RELAY_CONFIG');
  const directory = '/state'; mkdirSync(directory, {recursive: true, mode: 0o700});
  const path = `${directory}/matrix-approvals.json`;
  let state; try {state = JSON.parse(readFileSync(path));} catch (e) { if (e.code !== 'ENOENT') throw e; state = {}; }
  function save(value) {
    writeFileSync(`${path}.tmp`, JSON.stringify(value), {mode: 0o600, flush: true}); renameSync(`${path}.tmp`, path);
    const fd = openSync(directory, 'r'); try {fsyncSync(fd);} finally {closeSync(fd);}
  }
  const relay = new ApprovalRelay({room: env.MATRIX_HOME_ROOM, users: env.MATRIX_ALLOWED_USERS.split(',').map(x => x.trim()).filter(Boolean), matrix: jsonClient(env.MATRIX_HOMESERVER, env.MATRIX_ACCESS_TOKEN, '/_matrix/client/v3'), gateway: jsonClient(env.GATEWAY_URL, env.APPROVER_TOKEN), state, save});
  while (true) {
    try {await relay.tick();} catch {process.stdout.write(JSON.stringify({timestamp: new Date().toISOString(), event: 'approval_relay_retry', status: 'failed'}) + '\n');}
    await new Promise(resolve => setTimeout(resolve, 3000));
  }
}
