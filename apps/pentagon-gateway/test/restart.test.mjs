import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { restartService, RESTART_TIMEOUT_MS, VERIFICATION_WINDOW_MS } from '../src/restart.mjs';
import { createBroker, dockerRequest } from '../src/broker.mjs';
import { createGateway } from '../src/server.mjs';
import { ApprovalRelay } from '../src/matrix-approvals.mjs';

const env = {GATEWAY_TOKEN: 'a'.repeat(32), APPROVER_TOKEN: 'b'.repeat(32), BROKER_TOKEN: 'c'.repeat(32)};
const policy = {services: {app: {container: 'test-app', restart: 'CONFIRM'}}, workflows: {}, projects: {}};
const info = health => ({State: {Status: 'running', Running: true, Health: {Status: health}},
  Config: {Healthcheck: {Test: ['CMD', 'check']}, Env: ['PASSWORD=private-value']}});
const bytes = value => Buffer.from(JSON.stringify(value));

function backend(samples, {restartError, inspectDelay = 0} = {}) {
  let elapsed = 0, index = 0;
  const calls = [];
  const timing = {now: () => elapsed, sleep: async ms => {elapsed += ms;}};
  const request = async (path, method, options) => {
    calls.push({path, method, ...options, at: elapsed});
    if (method === 'POST') {
      elapsed += RESTART_TIMEOUT_MS;
      if (restartError) throw restartError;
      return Buffer.alloc(0);
    }
    elapsed += inspectDelay;
    const sample = samples[Math.min(index++, samples.length - 1)];
    if (sample instanceof Error) throw sample;
    return typeof sample === 'string' ? Buffer.from(sample) : bytes(sample);
  };
  return {request, timing, calls};
}

test('restart polls starting containers until Docker reports running and healthy', async () => {
  const fake = backend([info('starting'), info('starting'), info('healthy')]);
  const result = await restartService('app', '/containers/test-app', fake.request, fake.timing);
  assert.equal(result.restart.status, 'acknowledged');
  assert.equal(result.restarted, true);
  assert.deepEqual(result.verification, {source: 'docker', windowMs: 10000, elapsedMs: 1000,
    attempts: 3, status: 'healthy', observation: {status: 'running', running: true, health: 'healthy'}});
  assert.deepEqual(fake.calls.map(c => [c.path, c.method]), [
    ['/containers/test-app/restart?t=10', 'POST'],
    ...Array.from({length: 3}, () => ['/containers/test-app/json', 'GET']),
  ]);
  assert.ok(!JSON.stringify(result).includes('private-value'));
});

test('absent and explicitly disabled health checks are reported without claiming healthy', async t => {
  for (const config of [{}, {Healthcheck: null}, {Healthcheck: {Test: ['NONE']}}]) {
    await t.test(JSON.stringify(config), async () => {
      const fake = backend([{State: {Status: 'running', Running: true}, Config: config}]);
      const result = await restartService('app', '/containers/test-app', fake.request, fake.timing);
      assert.equal(result.verification.status, 'running_no_healthcheck');
      assert.equal(result.verification.attempts, 1);
      assert.equal(fake.calls.filter(c => c.method === 'POST').length, 1);
    });
  }
});

test('unhealthy and stopped states are distinct terminal observations', async t => {
  for (const [sample, status] of [[info('unhealthy'), 'unhealthy'],
    [{State: {Status: 'exited', Running: false}}, 'stopped'],
    [{State: {Status: 'paused', Running: true}}, 'stopped']]) {
    await t.test(status + sample.State.Status, async () => {
      const fake = backend([sample]);
      const result = await restartService('app', '/containers/test-app', fake.request, fake.timing);
      assert.equal(result.restart.status, 'acknowledged');
      assert.equal(result.verification.status, status);
      assert.equal(fake.calls.length, 2);
    });
  }
});

test('starting expires within the nested budgets and every read fits the remaining window', async () => {
  const fake = backend([info('starting')], {inspectDelay: 100});
  const result = await restartService('app', '/containers/test-app', fake.request, fake.timing);
  assert.equal(result.verification.status, 'starting_timeout');
  assert.equal(result.verification.elapsedMs, VERIFICATION_WINDOW_MS);
  assert.equal(result.verification.observation.health, 'starting');
  assert.ok(result.verification.attempts > 1);
  assert.equal(fake.calls.filter(c => c.method === 'POST').length, 1);
  for (const call of fake.calls.filter(c => c.method === 'GET')) {
    assert.ok(call.timeoutMs > 0 && call.timeoutMs <= 2000);
    assert.ok(call.timeoutMs <= RESTART_TIMEOUT_MS + VERIFICATION_WINDOW_MS - call.at);
  }
  assert.ok(fake.timing.now() <= RESTART_TIMEOUT_MS + VERIFICATION_WINDOW_MS);
  assert.ok(RESTART_TIMEOUT_MS + VERIFICATION_WINDOW_MS < 30000);
});

test('verification errors, malformed state and late reads never repeat the acknowledged restart', async t => {
  for (const samples of [[new Error('socket failure with secret')], ['invalid json'], [{}],
    [{State: {Status: 'running', Running: true}, Config: []}],
    [{State: {Status: 'running', Running: true}, Config: info().Config}],
    [info('starting'), new Error('inspect timed out')]]) {
    await t.test(JSON.stringify(samples), async () => {
      const fake = backend(samples);
      const result = await restartService('app', '/containers/test-app', fake.request, fake.timing);
      assert.equal(result.restarted, true);
      assert.equal(result.verification.status, 'unavailable');
      assert.equal(fake.calls.filter(c => c.method === 'POST').length, 1);
      assert.ok(!JSON.stringify(result).includes('secret'));
    });
  }
  const late = backend([info('healthy')], {inspectDelay: VERIFICATION_WINDOW_MS + 1});
  assert.equal((await restartService('app', '/containers/test-app', late.request, late.timing)).verification.status, 'unavailable');
});

test('lost restart acknowledgment is uncertain, with no verification or retry', async () => {
  const fake = backend([], {restartError: new Error('acknowledgment lost')});
  assert.deepEqual(await restartService('app', '/containers/test-app', fake.request, fake.timing), {
    service: 'app', restarted: null, restart: {status: 'uncertain'}, verification: {status: 'not_attempted', source: 'docker'},
  });
  assert.equal(fake.calls.length, 1);
});

async function listen(t, server) {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  return `http://127.0.0.1:${server.address().port}`;
}

test('approved gateway/broker/relay flow stores and reports verification, never replays', async t => {
  for (const [samples, restartError, status, phrase] of [
    [[info('starting'), info('healthy')], null, 'healthy', 'running and Docker reports healthy'],
    [[{State: {Status: 'running', Running: true}, Config: {}}], null, 'running_no_healthcheck', 'no health check is configured'],
    [[info('unhealthy')], null, 'unhealthy', 'running but unhealthy'],
    [[{State: {Status: 'exited', Running: false}}], null, 'stopped', 'stopped'],
    [[info('starting')], null, 'starting_timeout', 'verification deadline expired'],
    [[new Error('inspect unavailable')], null, 'unavailable', 'verification is unavailable'],
    [[], new Error('restart response lost'), 'not_attempted', 'restart outcome is uncertain'],
  ]) {
    await t.test(status, async t => {
      const fake = backend(samples, {restartError});
      const brokerUrl = await listen(t, createBroker(env, policy, fake.request, fake.timing));
      const state = mkdtempSync(`${tmpdir()}/restart-flow-`);
      t.after(() => rmSync(state, {recursive: true, force: true}));
      const configuredEnv = {...env, BROKER_URL: brokerUrl};
      const gateway = createGateway({env: configuredEnv, policy, state});
      const url = await listen(t, gateway.server);
      const client = async (method, path, data, admin = true) => {
        const res = await fetch(url + path, {method, headers: {authorization: `Bearer ${admin ? env.APPROVER_TOKEN : env.GATEWAY_TOKEN}`,
          'content-type': 'application/json', 'x-session-id': 'test', 'x-user-request': 'Restart app'},
        body: data === undefined ? undefined : JSON.stringify(data)});
        return {status: res.status, data: await res.json()};
      };
      const pending = await client('POST', '/homelab/services/app/restart', {}, false);
      const id = pending.data.approvalId;
      assert.equal(fake.calls.length, 0);
      await client('POST', `/approvals/${id}`, {approve: true, operator: 'tester'});
      const results = await Promise.all([1, 2].map(() => client('POST', `/approvals/${id}/execute`, {})));
      assert.deepEqual(results.map(r => r.status).sort(), [200, 403]);
      const record = (await client('GET', `/approvals/${id}`)).data;
      assert.equal(record.outcome.data.verification.status, status);
      assert.equal(record.status, restartError ? 'UNCERTAIN' : 'DONE');
      assert.equal(record.outcome.success, !restartError);
      const diskRecord = JSON.parse(readFileSync(`${state}/approvals/${id}.json`));
      assert.deepEqual(diskRecord.outcome, record.outcome);
      const fresh = createGateway({env: configuredEnv, policy, state});
      await assert.rejects(fresh.invoke('homelab.restartService', record.arguments, record.context, id), /INVALID_APPROVAL/);
      const messages = [];
      const relayState = {since: 'cursor', prompts: {[id]: {decision: {approve: true}, executionAttempted: true}}};
      const relay = new ApprovalRelay({room: '!test:local', users: ['tester'], state: relayState, save: () => {},
        gateway: async (method, path, data) => (await client(method, path, data)).data,
        matrix: async (method, path, data) => {
          if (path.startsWith('/sync?')) return {next_batch: 'next'};
          if (method === 'GET') return [];
          messages.push(data.body); return {event_id: '$result'};
        }});
      await relay.tick(); await relay.tick();
      assert.equal(messages.length, 1);
      assert.ok(messages[0].includes(phrase), messages[0]);
      if (!restartError) assert.ok(messages[0].includes('application recovery and external reachability were not checked'));
      assert.equal(fake.calls.filter(c => c.method === 'POST').length, 1);
    });
  }
});

test('a lost broker HTTP response becomes durable uncertainty and cannot consume approval again', async t => {
  let writes = 0;
  const brokerUrl = await listen(t, http.createServer((req, res) => {writes++; res.destroy();}));
  const state = mkdtempSync(`${tmpdir()}/restart-lost-response-`);
  t.after(() => rmSync(state, {recursive: true, force: true}));
  const {invoke} = createGateway({env: {...env, BROKER_URL: brokerUrl}, policy, state});
  const context = {sessionId: 'test', userRequest: 'Restart app'};
  const pending = await invoke('homelab.restartService', {service: 'app'}, context);
  // Decision transport is already covered above; seed the durable approved record here.
  const path = `${state}/approvals/${pending.approvalId}.json`;
  const record = JSON.parse(readFileSync(path)); record.status = 'APPROVED';
  writeFileSync(path, JSON.stringify(record));
  const result = await invoke('homelab.restartService', record.arguments, context, record.id);
  assert.equal(result.success, false);
  assert.equal(result.error, 'RESTART_UNCERTAIN');
  assert.equal(result.data.restart.status, 'uncertain');
  assert.equal(JSON.parse(readFileSync(path)).status, 'UNCERTAIN');
  await assert.rejects(invoke('homelab.restartService', record.arguments, context, record.id), /INVALID_APPROVAL/);
  assert.equal(writes, 1);
});

test('Docker absolute timeout covers missing headers and a trickling body over a fake Unix socket', async t => {
  for (const trickle of [false, true]) {
    await t.test(trickle ? 'trickling body' : 'no headers', async t => {
      const directory = mkdtempSync(`${tmpdir()}/fake-docker-`), socketPath = `${directory}/docker.sock`;
      const server = http.createServer((_req, res) => {
        if (trickle) {
          res.writeHead(200);
          const timer = setInterval(() => res.write(' '), 5);
          res.on('close', () => clearInterval(timer));
        }
      });
      await new Promise(resolve => server.listen(socketPath, resolve));
      t.after(async () => {await new Promise(resolve => server.close(resolve)); rmSync(directory, {recursive: true, force: true});});
      const start = performance.now();
      await assert.rejects(dockerRequest('/containers/fake/json', 'GET', {socketPath, timeoutMs: 80}), {code: 'DOCKER_TIMEOUT'});
      assert.ok(performance.now() - start < 1000);
    });
  }
});
