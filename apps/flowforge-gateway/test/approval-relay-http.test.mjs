import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { jsonClient } from '../src/approval-relay-http.mjs';
import { jsonClient as relayJsonClient } from '../src/matrix-approvals.mjs';

test('the relay retains the same named jsonClient export', () => {
  assert.equal(relayJsonClient, jsonClient);
});

async function fixture(t, respond) {
  const requests = [];
  const server = http.createServer(async (req, res) => {
    const chunks = []; for await (const chunk of req) chunks.push(chunk);
    const request = {method: req.method, path: req.url, headers: req.headers, body: Buffer.concat(chunks)};
    requests.push(request);
    respond(request, res);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => {server.closeAllConnections(); server.close(resolve);}));
  return {base: `http://127.0.0.1:${server.address().port}`, requests};
}

test('Matrix client paths use the prefix and JSON while media uploads bypass it with exact binary bytes', async t => {
  const f = await fixture(t, (_req, res) => res.end('{"received":true}'));
  const client = jsonClient(f.base, 'fixture-token', '/_matrix/client/v3');
  const payload = {msgtype: 'm.notice', body: 'UTF-8: żółw 🐢', nested: {approved: false}};
  const bytes = Buffer.from([0, 255, 128, 34, 10, 13]);
  assert.deepEqual(await client('PUT', '/rooms/room/send/m.room.message/txn', payload), {received: true});
  assert.deepEqual(await client('POST', '/_matrix/media/v3/upload?filename=plan.md', bytes,
    {contentType: 'text/markdown; charset=utf-8'}), {received: true});
  await client('GET', '/sync?timeout=0');
  await client('GET', '/_matrix/media-other');
  await jsonClient(f.base, 'gateway-token')('POST', '/approvals/id', {approve: true});

  assert.deepEqual(f.requests.map(req => [req.method, req.path]), [
    ['PUT', '/_matrix/client/v3/rooms/room/send/m.room.message/txn'],
    ['POST', '/_matrix/media/v3/upload?filename=plan.md'],
    ['GET', '/_matrix/client/v3/sync?timeout=0'],
    ['GET', '/_matrix/client/v3/_matrix/media-other'],
    ['POST', '/approvals/id'],
  ]);
  assert.deepEqual(f.requests[0].body, Buffer.from(JSON.stringify(payload)));
  assert.deepEqual(f.requests[1].body, bytes);
  assert.equal(f.requests[2].body.length, 0);
  assert.deepEqual(f.requests[4].body, Buffer.from('{"approve":true}'));
  for (const [index, req] of f.requests.entries()) {
    assert.equal(req.headers.authorization, `Bearer ${index === 4 ? 'gateway-token' : 'fixture-token'}`);
    assert.equal(req.headers['content-type'], index === 1 ? 'text/markdown; charset=utf-8' : 'application/json');
    assert.equal(req.headers['user-agent'], 'Pentagon-Approval-Relay/1.0');
  }
});

test('redirects are rejected without following or retrying the request', async t => {
  const target = await fixture(t, (_req, res) => res.end('{}'));
  const source = await fixture(t, (_req, res) => {
    res.writeHead(307, {location: target.base + '/redirect-target'}); res.end();
  });
  await assert.rejects(jsonClient(source.base, 'fixture-token')('POST', '/upload', Buffer.from('plan')), TypeError);
  assert.equal(source.requests.length, 1);
  assert.equal(target.requests.length, 0);
});

test('the 35-second deadline signal aborts a pending response without retrying', async t => {
  const controller = new AbortController();
  const reason = new DOMException('Fixture deadline', 'TimeoutError');
  const timeout = t.mock.method(AbortSignal, 'timeout', milliseconds => {
    assert.equal(milliseconds, 35000);
    return controller.signal;
  });
  const f = await fixture(t, () => controller.abort(reason));
  await assert.rejects(jsonClient(f.base, 'fixture-token')('GET', '/stalled'), error => error === reason);
  assert.equal(timeout.mock.callCount(), 1);
  assert.equal(f.requests.length, 1);
});

test('successful responses parse JSON through the one-MiB boundary and reject larger bodies', async t => {
  const limit = 1048576;
  const f = await fixture(t, (req, res) => res.end('"' + 'x'.repeat(limit - 2 + (req.path === '/oversized' ? 1 : 0)) + '"'));
  const client = jsonClient(f.base, 'fixture-token');
  assert.equal((await client('GET', '/at-limit')).length, limit - 2);
  await assert.rejects(client('GET', '/oversized'), {message: 'PAYLOAD_TOO_LARGE', code: 'PAYLOAD_TOO_LARGE', status: 413});
});

test('empty and malformed successful responses remain JSON parse failures', async t => {
  const f = await fixture(t, (req, res) => res.end(req.path === '/empty' ? '' : '{'));
  const client = jsonClient(f.base, 'fixture-token');
  for (const path of ['/empty', '/malformed']) await assert.rejects(client('GET', path), SyntaxError);
});

test('HTTP failures expose only the sanitized code, status, and bounded retry timing', async t => {
  const cases = [
    {name: 'missing delays', body: '{}', expected: 0},
    {name: 'private upstream fields omitted', status: 413,
      body: '{"error":"private-fixture-token request data","errcode":"PRIVATE_ERROR","retry_after_ms":1000}', expected: 1000},
    {name: 'server failure status retained', status: 503, header: '2', body: '{}', expected: 2000},
    {name: 'fractional seconds', header: '1.25', body: '{}', expected: 1250},
    {name: 'JSON delay without header', body: '{"retry_after_ms":2400}', expected: 2400},
    {name: 'JSON delay wins', header: '1', body: '{"retry_after_ms":2400}', expected: 2400},
    {name: 'header delay wins', header: '3', body: '{"retry_after_ms":2400}', expected: 3000},
    {name: 'negative delays clamp to zero', header: '-2', body: '{"retry_after_ms":-100}', expected: 0},
    {name: 'header cap', header: '3601', body: '{}', expected: 3600000},
    {name: 'JSON cap', body: '{"retry_after_ms":3600001}', expected: 3600000},
    {name: 'string JSON delay ignored', header: '2', body: '{"retry_after_ms":"3000"}', expected: 2000},
    {name: 'nonfinite JSON delay ignored', header: '2', body: '{"retry_after_ms":1e309}', expected: 2000},
    {name: 'null JSON body', header: '2', body: 'null', expected: 2000},
    {name: 'malformed body retains header', header: '2', body: '{private upstream error', expected: 2000},
    {name: 'empty body retains header', header: '2', body: '', expected: 2000},
    // Characterize existing behavior: a nonnumeric header suppresses even a valid JSON delay.
    {name: 'invalid header with JSON delay', header: 'invalid', body: '{"retry_after_ms":2400}', expected: 0},
    {name: 'HTTP-date header', header: 'Wed, 21 Oct 2015 07:28:00 GMT', body: '{}', expected: 0},
    {name: 'nonfinite header', header: 'Infinity', body: '{}', expected: 0},
    {name: 'error body at limit', header: '1', body: '{"retry_after_ms":2400}'.padEnd(16384), expected: 2400},
    {name: 'oversized error body retains header', header: '1', body: '{"retry_after_ms":2400}'.padEnd(16385), expected: 1000},
    {name: 'oversized error without header', body: 'x'.repeat(16385), expected: 0},
  ];
  let current;
  const f = await fixture(t, (_req, res) => {
    res.writeHead(current.status ?? 429, current.header === undefined ? {} : {'retry-after': current.header});
    res.end(current.body);
  });
  const client = jsonClient(f.base, 'private-fixture-token');
  for (const entry of cases) await t.test(entry.name, async () => {
    current = entry;
    await assert.rejects(client('POST', '/upload', {private: 'request data'}), error => {
      assert.equal(error.message, 'APPROVAL_RELAY_HTTP_FAILED');
      assert.deepEqual({...error}, {httpStatus: entry.status ?? 429, retryAfterMs: entry.expected});
      assert.equal(error.cause, undefined);
      assert.ok(!error.stack.includes('private'));
      return true;
    });
  });
  assert.equal(f.requests.length, cases.length);
});
