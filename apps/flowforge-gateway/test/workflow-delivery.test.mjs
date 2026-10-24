import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { mkdtempSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { ApprovalRelay, jsonClient } from '../src/matrix-approvals.mjs';
import { createGateway } from '../src/server.mjs';

const id = '12345678-1234-1234-1234-123456789abc';
const runId = '22345678-1234-1234-1234-123456789abc';
const room = '!planning:server';
const names = ['concept-plan.md', 'grounded-plan.md'];
const outputs = {
  'concept-plan.md': '# Concept\n\nZażółć gęślą jaźń 🧭\n'.repeat(450) + '\nConcept ending.\n',
  'grounded-plan.md': '# Grounded\n\nImplementation details.\n'.repeat(450) + '\nGrounded ending.\n',
};

function fixture({run = {status: 'DONE', task_id: 'TASK-12', run_id: runId, outputs}, failUpload, failSend, encrypted = false} = {}) {
  const state = {since: 'initial', prompts: {[id]: {finished: true, workflowPending: true}}};
  const uploads = [], attempts = [], sent = new Map(), logs = [];
  let durable = structuredClone(state), now = 1000000, lookups = 0;
  const matrix = async (method, path, data, options) => {
    if (path.startsWith('/sync?')) return {next_batch: 'next'};
    if (method === 'GET') return encrypted ? [{type: 'm.room.encryption'}] : [];
    if (path.startsWith('/_matrix/media/')) {
      const name = new URL(path, 'https://matrix').searchParams.get('filename');
      const file = durable.prompts[id].workflowDelivery.files.find(file => file.name === name);
      assert.equal(file.uploadStatus, 'uploading'); // Claim must be durable before POST.
      uploads.push({name, bytes: Buffer.from(data), options});
      const result = failUpload?.(name, uploads.length);
      if (result) return result;
      return {content_uri: `mxc://server/${name}`};
    }
    attempts.push({path, data: structuredClone(data)});
    // Emulate homeserver transaction deduplication, including a lost response.
    if (!sent.has(path)) sent.set(path, {data: structuredClone(data), event_id: `$${sent.size}`});
    else assert.deepEqual(data, sent.get(path).data);
    failSend?.(path, data);
    return {event_id: sent.get(path).event_id};
  };
  const gateway = async (method, path) => {
    assert.equal(method, 'GET');
    if (path === '/approvals') return {requests: []};
    assert.equal(path, `/approvals/${id}/workflow`); lookups++;
    return {success: true, data: structuredClone(run)};
  };
  let relay = new ApprovalRelay({room, users: [], state, matrix, gateway, save: value => {durable = structuredClone(value);},
    now: () => now, log: entry => logs.push(entry)});
  return {
    get relay() {return relay;}, get state() {return relay.state;}, get durable() {return durable;},
    uploads, attempts, sent, logs, get lookups() {return lookups;},
    advance: milliseconds => {now += milliseconds;},
    restart: () => {relay = new ApprovalRelay({...relay, state: JSON.parse(JSON.stringify(durable))});},
    delivery: () => relay.state.prompts[id].workflowDelivery,
  };
}

test('one deterministic English notice and complete UTF-8 Markdown attachments, without text plan dumping', async () => {
  const f = fixture(); await f.relay.tick();
  assert.equal(f.attempts.length, 3);
  assert.equal(f.attempts[0].data.body,
    `FlowForge planning completed: task TASK-12, run ${runId}. Outcome: DONE. Available plans: concept-plan.md, grounded-plan.md.`);
  assert.equal(f.attempts[0].data.msgtype, 'm.notice');
  assert.deepEqual(f.uploads.map(item => item.name), names);
  for (const upload of f.uploads) {
    assert.deepEqual(upload.bytes, Buffer.from(outputs[upload.name], 'utf8'));
    assert.equal(upload.options.contentType, 'text/markdown; charset=utf-8');
    const file = f.attempts.find(item => item.data.filename === upload.name).data;
    assert.deepEqual(file, {msgtype: 'm.file', body: upload.name, filename: upload.name,
      url: `mxc://server/${upload.name}`, info: {mimetype: 'text/markdown; charset=utf-8', size: upload.bytes.length}});
  }
  assert.equal(f.delivery().status, 'delivered');
  f.restart(); await f.relay.tick();
  assert.equal(f.attempts.length, 3); assert.equal(f.uploads.length, 2); assert.equal(f.lookups, 1);
});

test('partial upload rejection preserves the other attachment and a bounded fallback plus full plans', async () => {
  const f = fixture({failUpload: name => {
    if (name === names[1]) throw Object.assign(new Error('sensitive upstream error'), {httpStatus: 413});
  }});
  await f.relay.tick();
  assert.ok(f.delivery().files[0].eventId);
  assert.equal(f.delivery().files[1].uploadStatus, 'failed');
  assert.equal(f.delivery().files[1].uploadError, 'MATRIX_UPLOAD_HTTP_413');
  assert.equal(f.delivery().status, 'failed');
  assert.equal(f.state.prompts[id].workflowPending, false);
  const fallback = f.delivery().fallback.body;
  assert.ok(fallback.includes('Undelivered files: grounded-plan.md'));
  assert.ok(fallback.includes('[Truncated; full sanitized plan retained in relay state.]'));
  assert.ok(Buffer.byteLength(fallback) < 8000);
  assert.equal(f.durable.prompts[id].workflowDelivery.files[1].text, outputs[names[1]]);
  assert.ok(!JSON.stringify(f.durable).includes('sensitive upstream error'));
  // Failed deliveries survive normal pruning of older successful approvals.
  for (let index = 0; index < 205; index++) f.state.prompts[`done-${index}`] = {finished: true};
  await f.relay.tick(); f.restart(); await f.relay.tick();
  assert.ok(f.state.prompts[id]); assert.equal(f.uploads.length, 2); assert.equal(f.attempts.length, 3);
});

test('lost upload responses and malformed successful responses are not uploaded again after restart', async () => {
  for (const failUpload of [() => {throw new Error('response lost');}, () => ({}),
    () => ({content_uri: 'https://unsafe.example/plan'}),
    () => {throw Object.assign(new Error('proxy response'), {httpStatus: 502});}]) {
    const f = fixture({failUpload}); await f.relay.tick();
    assert.ok(f.delivery().files.every(file => file.uploadStatus === 'uncertain'));
    assert.equal(f.delivery().status, 'failed');
    assert.ok(f.delivery().fallback.body.includes('uncertain uploads require operator review'));
    assert.ok(Buffer.byteLength(f.delivery().fallback.body) < 8000);
    f.restart(); await f.relay.tick();
    assert.equal(f.uploads.length, 2); assert.equal(f.sent.size, 2);
  }
});

test('a process crash after the upload claim stops replay and still delivers the other file', async () => {
  const f = fixture();
  // Save the exact durable claim at the crash boundary, before recording a URI.
  let crashState;
  const original = f.relay.matrix;
  f.relay.matrix = async (method, path, data, options) => {
    if (path.includes('filename=concept-plan.md')) crashState = structuredClone(f.durable);
    return original(method, path, data, options);
  };
  await f.relay.tick();
  const statePath = mkdtempSync(`${tmpdir()}/workflow-restart-`);
  try {
    writeFileSync(`${statePath}/state.json`, JSON.stringify(crashState));
    const relay = new ApprovalRelay({...f.relay, state: JSON.parse(readFileSync(`${statePath}/state.json`, 'utf8'))});
    const before = f.uploads.length;
    await relay.tick();
    const files = relay.state.prompts[id].workflowDelivery.files;
    assert.equal(files[0].uploadStatus, 'uncertain');
    assert.equal(files[0].mxc, undefined); assert.ok(files[1].eventId);
    assert.equal(f.uploads.length, before + 1);
    assert.equal(f.uploads.at(-1).name, names[1]);
  } finally {rmSync(statePath, {recursive: true});}
});

test('ambiguous notice, file and fallback sends reuse frozen transaction content after restart', async () => {
  for (const target of ['workflow-completion', 'workflow-file-concept-plan.md', 'workflow-file-grounded-plan.md', 'workflow-fallback']) {
    let fail = true;
    const f = fixture({
      failUpload: target === 'workflow-fallback' ? () => {throw Object.assign(new Error('too large'), {httpStatus: 413});} : undefined,
      failSend: path => {if (path.endsWith(target) && fail) throw new Error('send response lost');},
    });
    await f.relay.tick();
    assert.equal(f.state.prompts[id].workflowPending, true);
    const uploads = f.uploads.length;
    f.restart(); fail = false;
    await f.relay.tick(); await f.relay.tick();
    const retried = f.attempts.filter(item => item.path.endsWith(target));
    assert.equal(retried.length, 2); assert.deepEqual(retried[0], retried[1]);
    assert.equal(f.state.prompts[id].workflowPending, false);
    assert.equal(f.uploads.length, target === 'workflow-completion' ? 2 : uploads);
    assert.equal(f.sent.size, target === 'workflow-completion' ? 3 : target === 'workflow-fallback' ? 2 : 4);
  }
});

test('rate-limit rejection retries only the failed upload with backoff and a finite retry budget', async () => {
  for (const recover of [true, false]) {
    let rejected = true;
    const f = fixture({failUpload: name => {
      if (name === names[1] && rejected) throw Object.assign(new Error('rate limited'), {httpStatus: 429, retryAfterMs: 60000});
    }});
    await f.relay.tick(); assert.equal(f.uploads.length, 2);
    f.restart(); await f.relay.tick(); assert.equal(f.uploads.length, 2);
    f.advance(60000); if (recover) rejected = false;
    await f.relay.tick();
    if (!recover) {f.advance(60000); await f.relay.tick();}
    assert.equal(f.delivery().status, recover ? 'delivered' : 'failed');
    assert.equal(f.state.prompts[id].workflowPending, false);
    assert.equal(f.uploads.filter(item => item.name === names[0]).length, 1);
    assert.equal(f.uploads.filter(item => item.name === names[1]).length, recover ? 2 : 3);
    const attempts = f.attempts.length;
    f.restart(); f.advance(60000); await f.relay.tick(); assert.equal(f.attempts.length, attempts);
  }
});

test('a real HTTP 429 with an invalid Retry-After header preserves the JSON upload retry delay', async t => {
  const f = fixture();
  const uploads = [];
  const server = http.createServer(async (req, res) => {
    for await (const _chunk of req) {} // Consume each upload or message before responding.
    let result;
    if (req.url.startsWith('/_matrix/media/v3/upload?')) {
      const name = new URL(req.url, 'http://fixture').searchParams.get('filename');
      uploads.push(name);
      if (uploads.length === 1) {
        res.writeHead(429, {'retry-after': 'invalid', 'content-type': 'application/json'});
        res.end('{"retry_after_ms":60000}'); return;
      }
      result = {content_uri: `mxc://server/${name}`};
    } else if (req.url.startsWith('/_matrix/client/v3/sync?')) result = {next_batch: 'next'};
    else if (req.url.endsWith('/state')) result = [];
    else result = {event_id: '$fixture'};
    res.writeHead(200, {'content-type': 'application/json'}); res.end(JSON.stringify(result));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => {server.closeAllConnections(); server.close(resolve);}));
  f.relay.matrix = jsonClient(`http://127.0.0.1:${server.address().port}`, 'fixture-token', '/_matrix/client/v3');

  await f.relay.tick();
  assert.deepEqual(uploads, names);
  assert.equal(f.delivery().files[0].uploadStatus, 'pending');
  assert.equal(f.delivery().files[0].uploadAttempts, 1);
  f.restart();
  f.advance(30000); await f.relay.tick();
  assert.deepEqual(uploads, names);
  f.advance(29999); await f.relay.tick();
  assert.deepEqual(uploads, names);
  f.advance(1); await f.relay.tick();
  assert.deepEqual(uploads, [...names, names[0]]);
  assert.equal(f.delivery().files[0].uploadAttempts, 2);
  assert.equal(f.delivery().status, 'delivered');
  assert.equal(f.state.prompts[id].workflowPending, false);
});

test('missing plans are explicit delivery failures and unknown outputs are never attached', async () => {
  const f = fixture({run: {status: 'DONE', task_id: 'TASK-12', run_id: runId,
    outputs: {'concept-plan.md': 'Available concept', 'grounded-plan.md': '', 'runner.log': 'RAW_UNSANITIZED', '/source/raw.md': 'RAW_UNSANITIZED'}}});
  await f.relay.tick();
  assert.equal(f.delivery().status, 'failed');
  assert.equal(f.uploads.length, 1);
  assert.ok(f.delivery().fallback.body.includes('Not returned by gateway: grounded-plan.md'));
  assert.ok(!JSON.stringify(f.state).includes('RAW_UNSANITIZED'));
  assert.ok(!JSON.stringify(f.attempts).includes('RAW_UNSANITIZED'));
});

test('failed runs send only a short code-based notification, even with outputs and verbose errors', async () => {
  for (const error of ['INTERRUPTED_REVIEW_REQUIRED', 'Verbose internal traceback\n' + 'private '.repeat(1000)]) {
    const f = fixture({run: {status: 'FAILED', task_id: 'TASK-12', run_id: runId, outputs, error}});
    await f.relay.tick(); f.restart(); await f.relay.tick();
    assert.equal(f.sent.size, 1); assert.equal(f.uploads.length, 0);
    const body = f.attempts[0].data.body;
    assert.ok(body.includes('Outcome: FAILED'));
    assert.ok(body.includes(error === 'INTERRUPTED_REVIEW_REQUIRED' ? error : 'PLANNING_PIPELINE_FAILED'));
    assert.ok(body.length < 250); assert.ok(!body.includes('private'));
    assert.deepEqual(f.delivery().files, []);
  }
});

test('encrypted rooms prevent plan uploads and file messages', async () => {
  const f = fixture({encrypted: true}); await f.relay.tick();
  assert.equal(f.uploads.length, 0); assert.equal(f.attempts.length, 0);
  assert.equal(f.state.prompts[id].workflowPending, true);
  assert.equal(f.durable.prompts[id].workflowDelivery.notice.error, 'MATRIX_SEND_UNCONFIRMED');
});

for (const partialFailure of [false, true]) test(`real gateway redaction and existing Matrix token survive ${partialFailure ? 'a partial upload failure and fallback' : 'complete HTTP attachment delivery'}`, async t => {
  const directory = mkdtempSync(`${tmpdir()}/workflow-gateway-`);
  t.after(() => rmSync(directory, {recursive: true}));
  const env = {GATEWAY_TOKEN: 'a'.repeat(32), APPROVER_TOKEN: 'b'.repeat(32), FLOWFORGE_TOKEN: 'upstream-secret-credential'};
  const raw = '# Plan\nUTF-8: żółw 🐢\n' + env.FLOWFORGE_TOKEN + '\npassword=hunter2\nBearer private-bearer\n-----BEGIN PRIVATE KEY-----\nprivate key\n-----END PRIVATE KEY-----\nEnd of plan.\n';
  const calls = [];
  const {server} = createGateway({env, state: directory,
    policy: {services: {}, projects: {}, workflows: {'task-analysis': {permission: 'CONFIRM'}}},
    execute: async (tool, args) => {
      calls.push({tool, args});
      return tool === 'flowforge.run' ? {success: true, run_id: runId} :
        {status: 'DONE', task_id: 'TASK-12', run_id: runId, outputs: Object.fromEntries(names.map(name => [name, raw]))};
    },
  });
  const uploaded = [], messages = [];
  const matrixServer = http.createServer(async (req, res) => {
    assert.equal(req.headers.authorization, 'Bearer existing-matrix-token');
    const chunks = []; for await (const chunk of req) chunks.push(chunk);
    let result;
    if (req.url.startsWith('/_matrix/media/v3/upload?')) {
      assert.equal(req.method, 'POST');
      assert.equal(req.headers['content-type'], 'text/markdown; charset=utf-8');
      uploaded.push(Buffer.concat(chunks));
      if (partialFailure && req.url.includes(names[1])) {
        res.writeHead(413, {'content-type': 'application/json'});
        res.end(JSON.stringify({errcode: 'M_TOO_LARGE', error: 'private upstream error'})); return;
      }
      result = {content_uri: `mxc://server/${uploaded.length}`};
    } else if (req.url.startsWith('/_matrix/client/v3/sync?')) result = {next_batch: 'next'};
    else if (req.url.endsWith('/state')) result = [];
    else {assert.equal(req.method, 'PUT'); messages.push(JSON.parse(Buffer.concat(chunks))); result = {event_id: `$${messages.length}`};}
    res.writeHead(200, {'content-type': 'application/json'}); res.end(JSON.stringify(result));
  });
  await Promise.all([server, matrixServer].map(server => new Promise(resolve => server.listen(0, '127.0.0.1', resolve))));
  t.after(async () => {await Promise.all([server, matrixServer].map(server => new Promise(resolve => server.close(resolve))));});
  const base = `http://127.0.0.1:${server.address().port}`;
  const contextClient = async (path, data) => {
    const response = await fetch(base + path, {method: 'POST', headers: {authorization: `Bearer ${env.GATEWAY_TOKEN}`,
      'content-type': 'application/json', 'x-session-id': 'fixture', 'x-user-request': 'Plan this task'}, body: JSON.stringify(data)});
    return response.json();
  };
  const gateway = jsonClient(base, env.APPROVER_TOKEN);
  const {approvalId} = await contextClient('/flowforge/run', {workflow: 'task-analysis', input: {project: 'mentory', task_id: 'TASK-12', task_sha256: 'c'.repeat(64)}});
  await gateway('POST', `/approvals/${approvalId}`, {approve: true, operator: '@owner:server'});
  await gateway('POST', `/approvals/${approvalId}/execute`, {});
  const state = {since: 'initial', prompts: {[approvalId]: {finished: true, workflowPending: true}}};
  const relay = new ApprovalRelay({room, users: [], state, save: () => {}, gateway,
    matrix: jsonClient(`http://127.0.0.1:${matrixServer.address().port}`, 'existing-matrix-token', '/_matrix/client/v3')});
  await relay.tick(); await relay.tick();
  const expected = '# Plan\nUTF-8: żółw 🐢\n[REDACTED]\npassword=[REDACTED]\nBearer [REDACTED]\n[REDACTED]\nEnd of plan.\n';
  assert.deepEqual(uploaded, names.map(() => Buffer.from(expected, 'utf8')));
  assert.equal(messages.length, 3);
  assert.equal(state.prompts[approvalId].workflowDelivery.status, partialFailure ? 'failed' : 'delivered');
  if (partialFailure) {
    assert.ok(messages[2].body.includes(expected));
    assert.equal(state.prompts[approvalId].workflowDelivery.files[1].uploadError, 'MATRIX_UPLOAD_HTTP_413');
  }
  for (const secret of [env.FLOWFORGE_TOKEN, 'hunter2', 'private-bearer', 'private key']) {
    assert.ok(!JSON.stringify(state).includes(secret));
    assert.ok(!uploaded.some(bytes => bytes.includes(Buffer.from(secret))));
    assert.ok(!JSON.stringify(messages).includes(secret));
  }
  assert.ok(!JSON.stringify(state).includes('private upstream error'));
  assert.deepEqual(calls.map(call => call.tool), ['flowforge.run', 'flowforge.getRun']);
});
