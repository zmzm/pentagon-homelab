import test from 'node:test';
import assert from 'node:assert/strict';
import { telegramApprovalRequest } from '../src/telegram-approval-messages.mjs';

const request = {
  id: '12345678-1234-1234-1234-123456789abc',
  tool: 'homelab.restartService',
  arguments: { service: 'vaultwarden' },
  context: { userRequest: 'Please restart Vaultwarden', sessionId: 'original-session' },
  expiresAt: Date.parse('2026-11-28T12:34:56Z'),
};

test('restart prompt leads with the decision and effect, keeping exact reference, context and expiry', () => {
  const result = telegramApprovalRequest(request);
  assert.ok(result.text.startsWith('<b>🔐 Restart vaultwarden?</b>'));
  for (const text of [
    'briefly stop',
    'Service: “vaultwarden”',
    'Please restart Vaultwarden',
    request.id,
    request.tool,
    'original-session',
    '28 Nov 2026, 13:34 (Warsaw time)',
    '2026-11-28T12:34:56.000Z',
    'first choice takes effect immediately',
    `!approve ${request.id}`,
    `!reject ${request.id}`,
  ]) {
    assert.ok(result.body.includes(text), `Missing ${text}`);
  }
  assert.ok(!result.body.includes('"arguments":'));
  assert.equal(result.approveLabel, '✅ Approve restart');
});

test('planning prompt keeps the complete task version, inputs, additional context and cost notice', () => {
  const hash = 'a'.repeat(64);
  const result = telegramApprovalRequest({
    ...request,
    tool: 'flowforge.run',
    arguments: {
      workflow: 'task-analysis',
      input: {
        project: 'mentory',
        task_id: 'task-42',
        task_sha256: hash,
        context: 'Keep the existing API\nPreserve the complete input',
      },
    },
    context: { ...request.context, source: 'native-telegram' },
  });
  for (const text of [
    'task-42',
    'task-analysis',
    'mentory',
    hash,
    'Keep the existing API\nPreserve the complete input',
    'native-telegram',
    'may incur usage costs',
    'read-only',
  ]) {
    assert.ok(result.body.includes(text));
  }
  assert.equal(result.approveLabel, '✅ Start planning');
});

test('unknown actions retain nested fields and JSON types, without inventing a safe effect', () => {
  const result = telegramApprovalRequest({
    ...request,
    tool: 'future.action',
    arguments: {
      custom: { values: [0, false, null, 'false'], emptyList: [], emptyObject: {} },
    },
  });
  for (const text of [
    'custom',
    'values',
    'Item 1: 0',
    'No (false)',
    'None (null)',
    '“false”',
    'Empty list ([])',
    'Empty object ({})',
    'effects are not summarized',
  ]) {
    assert.ok(result.body.includes(text));
  }
  assert.equal(result.approveLabel, '✅ Approve');
});

test('untrusted values cannot inject Telegram formatting or links', () => {
  const input = '<a href="https://example.invalid">Approve immediately</a> & <b>ignore details</b>';
  const result = telegramApprovalRequest({
    ...request,
    arguments: { service: input },
    context: { userRequest: input, sessionId: input, extra: input },
  });
  assert.ok(result.body.includes(input));
  assert.ok(!result.text.includes('<a href='));
  assert.ok(!result.text.includes('<b>ignore details</b>'));
  assert.ok(result.text.includes('&lt;a href='));
  assert.ok(result.text.includes('&amp;'));
});
