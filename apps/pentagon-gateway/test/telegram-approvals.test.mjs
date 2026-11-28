import test from 'node:test';
import assert from 'node:assert/strict';
import { TelegramApprovalRelay, telegramDecision } from '../src/telegram-approvals.mjs';
import { telegramClient } from '../src/telegram-api.mjs';
import { validateTelegramState } from '../src/telegram-approvals.mjs';
import { createGateway } from '../src/server.mjs';
import { jsonClient } from '../src/approval-relay-http.mjs';
import { mkdtempSync, rmSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';

const id = '12345678-1234-1234-1234-123456789abc';
const chat = '123456';
const now = 1000000;
const prompt = { eventId: 10, preparedAt: now - 1000, expiresAt: now + 600000 };
const message = { message_id: 10, date: now / 1000, chat: { id: 123456, type: 'private' } };
const from = { id: 123456, is_bot: false };
const callback = {
  update_id: 4,
  callback_query: {
    id: 'callback',
    from,
    message,
    data: `approve:${id}`,
  },
};

test('only own private DM, exact prompt, allowed human and live approval can authorize', () => {
  const decide = (update) => telegramDecision(update, chat, [chat], { [id]: prompt }, now);
  assert.equal(decide(callback).approve, true);
  for (const override of [
    { from: { ...from, id: 654321 } },
    { from: { ...from, is_bot: true } },
    { message: { ...message, chat: { id: 123456, type: 'group' } } },
    { message: { ...message, chat: { id: 654321, type: 'private' } } },
    { message: { ...message, message_id: 11 } },
    { message: { ...message, edit_date: 1001 } },
    { data: `approve:${id} more` },
    { data: 'yes' },
    { message: undefined },
  ]) {
    assert.equal(
      decide({ ...callback, callback_query: { ...callback.callback_query, ...override } }),
      null,
    );
  }
  for (const p of [
    { ...prompt, decision: {} },
    { ...prompt, finished: true },
    { ...prompt, expiresAt: now },
    { ...prompt, eventId: undefined },
  ]) {
    assert.equal(telegramDecision(callback, chat, [chat], { [id]: p }, now), null);
  }
  assert.equal(telegramDecision(callback, chat, [], { [id]: prompt }, now), null);
});

test('text fallback requires a fresh unedited reply to the exact prompt; edits are ignored', () => {
  const reply = {
    ...message,
    message_id: 12,
    from,
    text: `!reject ${id}`,
    reply_to_message: { message_id: 10 },
  };
  const decide = (m) =>
    telegramDecision({ update_id: 4, message: m }, chat, [chat], { [id]: prompt }, now);
  assert.equal(decide(reply).approve, false);
  for (const patch of [
    { reply_to_message: undefined },
    { date: 0 },
    { date: now / 1000 + 61 },
    { edit_date: 1 },
    { text: 'yes' },
  ]) {
    assert.equal(decide({ ...reply, ...patch }), null);
  }
  assert.equal(
    telegramDecision({ update_id: 4, edited_message: reply }, chat, [chat], { [id]: prompt }, now),
    null,
  );
});

function fixture() {
  const state = { version: 1, offset: 1, prompts: {} };
  const record = {
    id,
    tool: 'homelab.restartService',
    arguments: { service: 'vaultwarden' },
    context: { sessionId: 'original', userRequest: 'Restart Vaultwarden' },
    status: 'PENDING',
    expiresAt: now + 600000,
  };
  let updates = [];
  const sends = [];
  const writes = [];
  const saves = [];
  let executeFailure = false;
  const gateway = async (method, path, data) => {
    if (path === '/approvals') {
      return { requests: record.status === 'PENDING' ? [record] : [] };
    }
    if (path.endsWith('/workflow')) {
      return {
        data: {
          status: 'DONE',
          run_id: 'run',
          task_id: 'task',
          outputs: {
            'concept-plan.md': '# Concept\nfull plan',
            'grounded-plan.md': '# Grounded\nfull plan',
          },
        },
      };
    }
    if (method === 'GET') {
      return structuredClone(record);
    }
    writes.push({ path, data });
    if (path.endsWith('/execute')) {
      assert.equal(saves.at(-1).prompts[id].executionAttempted, true);
      if (executeFailure) {
        throw new Error('lost response');
      }
      record.status = 'DONE';
      record.outcome = { success: true };
    } else {
      assert.equal(saves.at(-1).prompts[id].decision.telegramUpdateId, '4');
      record.status = data.approve ? 'APPROVED' : 'REJECTED';
    }
    return { success: true };
  };
  const telegram = async (method, payload) => {
    if (method === 'answerCallbackQuery') {
      return true;
    }
    if (method === 'getUpdates') {
      return updates;
    }
    assert.equal(Object.values(saves.at(-1).prompts[id].deliveries).at(-1).status, 'sending');
    sends.push({ method, payload });
    return { ...message, message_id: sends.length === 1 ? 10 : 20 + sends.length };
  };
  const save = (value) => saves.push(structuredClone(value));
  const options = {
    chat,
    users: [chat],
    gateway,
    state,
    save,
    telegram,
    now: () => now,
    log: () => {},
  };
  const relay = new TelegramApprovalRelay(options);
  return {
    relay,
    options,
    state,
    record,
    writes,
    sends,
    saves,
    updates: (value) => {
      updates = value;
    },
    loseExecution: () => {
      executeFailure = true;
    },
  };
}

test('stored-action lifecycle saves decision/cursor before execution, retains evidence and never executes twice', async () => {
  const f = fixture();
  await f.relay.tick();
  assert.ok(f.sends[0].payload.text.includes('vaultwarden'));
  assert.ok(f.sends[0].payload.text.includes('original'));
  assert.equal(f.sends[0].payload.parse_mode, 'HTML');
  assert.equal(f.sends[0].payload.reply_markup.inline_keyboard[0][0].text, '✅ Approve restart');
  f.updates([callback]);
  await f.relay.tick();
  assert.equal(f.state.offset, 5);
  assert.equal(f.state.prompts[id].finished, true);
  assert.equal(f.writes.filter((w) => w.path.endsWith('/execute')).length, 1);
  assert.equal(f.writes[0].data.telegramChatId, chat);
  await new TelegramApprovalRelay({ ...f.options, state: structuredClone(f.state) }).tick();
  assert.equal(f.writes.filter((w) => w.path.endsWith('/execute')).length, 1);
});

test('rejected approval never executes; first saved decision wins', async () => {
  const f = fixture();
  await f.relay.tick();
  f.updates([
    { ...callback, callback_query: { ...callback.callback_query, data: `reject:${id}` } },
    { ...callback, update_id: 5 },
  ]);
  await f.relay.tick();
  assert.equal(f.record.status, 'REJECTED');
  assert.equal(f.writes.filter((w) => w.path.endsWith('/execute')).length, 0);
});

test('ambiguous execution is not replayed after relay restart', async () => {
  const f = fixture();
  await f.relay.tick();
  f.loseExecution();
  f.updates([callback]);
  await f.relay.tick();
  await new TelegramApprovalRelay({ ...f.options, state: structuredClone(f.state) }).tick();
  assert.equal(f.writes.filter((w) => w.path.endsWith('/execute')).length, 1);
  assert.ok(f.sends.at(-1).payload.text.includes('uncertain'));
});

test('lost prompt or result sends retain uncertainty and do not resend or repeat execution', async () => {
  for (const stage of ['prompt', 'result']) {
    const f = fixture();
    if (stage === 'result') {
      await f.relay.tick();
      f.updates([callback]);
    }
    let attempts = 0;
    const options = {
      ...f.options,
      telegram: async (method) => {
        if (method === 'answerCallbackQuery') {
          return true;
        }
        if (method === 'getUpdates') {
          return stage === 'result' ? [callback] : [];
        }
        attempts++;
        throw new Error('ambiguous send');
      },
    };
    await new TelegramApprovalRelay(options).tick();
    await new TelegramApprovalRelay({ ...options, state: structuredClone(f.state) }).tick();
    assert.equal(attempts, 1);
    assert.equal(
      f.writes.filter((w) => w.path.endsWith('/execute')).length,
      stage === 'result' ? 1 : 0,
    );
  }
});

test('interrupted send claim is quarantined and save failure prevents dispatch', async () => {
  const f = fixture();
  f.state.prompts[id] = { ...prompt, deliveries: { prompt: { status: 'sending' } } };
  await assert.rejects(f.relay.deliver(id, 'prompt', 'sendMessage', {}));
  assert.equal(f.state.prompts[id].deliveries.prompt.status, 'uncertain');
  assert.equal(f.sends.length, 0);
  const relay = new TelegramApprovalRelay({
    ...f.options,
    save: () => {
      throw new Error('disk full');
    },
  });
  await assert.rejects(relay.deliver(id, 'new', 'sendMessage', {}));
  assert.equal(f.sends.length, 0);
});

test('pending prompts keep their frozen presentation across a renderer change', async () => {
  const f = fixture();
  const payload = {
    chat_id: chat,
    text: 'Previously prepared exact prompt',
    reply_markup: { inline_keyboard: [[{ text: 'Approve', callback_data: `approve:${id}` }]] },
  };
  f.state.prompts[id] = {
    preparedAt: now,
    expiresAt: now + 600000,
    deliveries: {
      prompt: { status: 'pending', attempts: 0, method: 'sendMessage', payload },
    },
  };
  await f.relay.tick();
  assert.deepEqual(f.sends[0].payload, payload);
});

test('oversize action is not truncated into an approvable prompt', async () => {
  const f = fixture();
  f.record.arguments.extra = 'x'.repeat(5000);
  await f.relay.tick();
  assert.equal(f.state.prompts[id].finished, true);
  assert.equal(f.sends[0].payload.reply_markup, undefined);
  assert.equal(f.state.prompts[id].eventId, undefined);
});

test('complete sanitized plans are sent as documents; lost upload is never retried', async () => {
  const f = fixture();
  f.state.prompts[id] = { ...prompt, finished: true, workflowPending: true };
  await f.relay.workflowResult(id, f.state.prompts[id]);
  assert.equal(f.sends.filter((s) => s.method === 'sendDocument').length, 2);
  assert.equal(f.sends[1].payload.document.text, '# Concept\nfull plan');
  assert.equal(f.state.prompts[id].workflowPending, false);
  const g = fixture();
  g.state.prompts[id] = { ...prompt, finished: true, workflowPending: true };
  let uploads = 0;
  const original = g.relay.telegram;
  g.relay.telegram = async (method, payload) => {
    if (method === 'sendDocument') {
      uploads++;
      throw new Error('upload unconfirmed');
    }
    return original(method, payload);
  };
  await g.relay.workflowResult(id, g.state.prompts[id]);
  await g.relay.workflowResult(id, g.state.prompts[id]);
  assert.equal(uploads, 2); // One attempt for each distinct file, no replay.
  assert.equal(g.state.prompts[id].workflowPending, false);
  assert.equal(g.state.prompts[id].workflowDelivery.status, 'failed');
  assert.ok(g.sends.at(-1).payload.text.includes('Bounded text fallback'));
});

test('Telegram transport strips token-bearing errors and bounds malformed/error bodies', async () => {
  const token = '123456:private-fixture';
  const client = telegramClient(token, async () => {
    throw new Error(`https://api.telegram.org/bot${token}/sendMessage`);
  });
  await assert.rejects(client('sendMessage'), (error) => !String(error).includes(token));
  const rateLimited = telegramClient(
    token,
    async () =>
      new Response(
        JSON.stringify({
          ok: false,
          error_code: 429,
          parameters: { retry_after: 4 },
        }),
        { status: 429 },
      ),
  );
  await assert.rejects(rateLimited('sendMessage'), (error) => error.retryAfterMs === 4000);
  const ambiguous = telegramClient(token, async () => new Response('{}', { status: 502 }));
  await assert.rejects(ambiguous('sendMessage'), (error) => error.retryAfterMs === undefined);
});

test('fresh bootstrap skips old decisions; rate-limit retries stop after three explicit rejections', async () => {
  const f = fixture();
  delete f.state.offset;
  const polls = [];
  const original = f.options.telegram;
  f.relay.telegram = async (method, payload) => {
    if (method === 'getUpdates') {
      polls.push(payload);
      return [callback];
    }
    return original(method, payload);
  };
  await f.relay.tick();
  assert.equal(polls[0].offset, -1);
  assert.equal(polls[1].offset, 5);
  assert.equal(f.writes.length, 0);
  let clock = now;
  let attempts = 0;
  const relay = new TelegramApprovalRelay({
    ...f.options,
    now: () => clock,
    telegram: async () => {
      attempts++;
      throw Object.assign(new Error('limited'), { retryAfterMs: 4000 });
    },
  });
  for (let n = 0; n < 3; n++) {
    await assert.rejects(relay.deliver(id, 'limited', 'sendMessage', { chat_id: chat, text: 'x' }));
    if (n === 0) {
      await assert.rejects(relay.deliver(id, 'limited', 'sendMessage', {}));
      assert.equal(attempts, 1);
    }
    clock += 4000;
  }
  await assert.rejects(relay.deliver(id, 'limited', 'sendMessage', {}));
  assert.equal(attempts, 3);
  assert.equal(f.state.prompts[id].deliveries.limited.status, 'failed');
});

test('unknown or damaged relay records are rejected instead of discarded', () => {
  assert.deepEqual(validateTelegramState({ version: 1, prompts: {} }), { version: 1, prompts: {} });
  for (const value of [
    null,
    { version: 2, prompts: {} },
    { version: 1, prompts: [] },
    { version: 1, prompts: {}, offset: -1 },
    { version: 1, prompts: { [id]: null } },
    { version: 1, prompts: { [id]: { ...prompt, executionAttempted: 'false' } } },
    { version: 1, prompts: { [id]: { ...prompt, deliveries: { prompt: { status: 'unknown' } } } } },
  ]) {
    assert.throws(() => validateTelegramState(value));
  }
});

test('real gateway HTTP and Telegram transport preserve the stored session, audit evidence and one execution', async (t) => {
  const directory = mkdtempSync(`${tmpdir()}/telegram-gateway-`);
  const env = { GATEWAY_TOKEN: 'a'.repeat(32), APPROVER_TOKEN: 'b'.repeat(32) };
  let executions = 0;
  const gateway = createGateway({
    env,
    state: directory,
    policy: {
      services: { vaultwarden: { container: 'vaultwarden', restart: 'CONFIRM' } },
      workflows: {},
      projects: {},
    },
    execute: async () => {
      executions++;
      return { restarted: true };
    },
  });
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  await new Promise((resolve) => gateway.server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise((resolve) => gateway.server.close(resolve)));
  const requested = await gateway.invoke(
    'homelab.restartService',
    { service: 'vaultwarden' },
    { sessionId: 'retained-session', userRequest: 'Restart Vaultwarden' },
  );
  let updates = [];
  const sent = [];
  const relay = new TelegramApprovalRelay({
    chat,
    users: [chat],
    state: { version: 1, offset: 1, prompts: {} },
    save: () => {},
    now: () => Date.now(),
    log: () => {},
    gateway: jsonClient(`http://127.0.0.1:${gateway.server.address().port}`, env.APPROVER_TOKEN),
    telegram: telegramClient('987654:fixture', async (url, options) => {
      const payload = JSON.parse(options.body);
      const result = url.endsWith('/getUpdates')
        ? updates
        : { ...message, message_id: 10 + sent.length };
      if (!url.endsWith('/getUpdates')) {
        sent.push(payload);
      }
      return new Response(JSON.stringify({ ok: true, result }));
    }),
  });
  await relay.tick();
  assert.ok(sent[0].text.includes('retained-session'));
  updates = [
    {
      ...callback,
      callback_query: { ...callback.callback_query, data: `approve:${requested.approvalId}` },
    },
  ];
  await relay.tick();
  await relay.tick();
  assert.equal(executions, 1);
  const audit = readFileSync(`${directory}/audit.jsonl`, 'utf8');
  assert.ok(audit.includes('"telegramUpdateId":"4"'));
  assert.ok(audit.includes('"sessionId":"retained-session"'));
});
