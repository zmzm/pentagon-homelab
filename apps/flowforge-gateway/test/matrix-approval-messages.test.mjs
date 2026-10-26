import test from 'node:test';
import assert from 'node:assert/strict';
import { workflowDelivery, workflowFallback, restartResultText, compactApprovalResult, approvalRequest } from '../src/matrix-approval-messages.mjs';

const proposal = (tool, args) => ({id: '12345678-1234-1234-1234-123456789abc', tool, arguments: args,
  context: {userRequest: 'Please run this action.'}, expiresAt: Date.parse('2026-10-25T14:38:05.289Z')});

test('request messages lead with the action and effect while all scope details stay expanded', () => {
  const request = proposal('homelab.restartService', {service: 'vaultwarden'});
  const message = approvalRequest(request, 'text-emoji-v1');
  assert.ok(message.body.startsWith('🔐 Restart vaultwarden?\n\nMay I restart this service?'));
  assert.ok(message.body.includes('briefly stop while it restarts'));
  assert.ok(message.body.includes('application access is not checked'));
  assert.ok(message.body.includes('25 Oct 2026, 15:38 (Warsaw time)'));
  assert.ok(message.body.includes('2026-10-25T14:38:05.289Z'));
  assert.ok(message.body.includes(`Reference: ${request.id}`));
  assert.ok(message.body.includes(`!approve ${request.id}\n!reject ${request.id}`));
  const visible = message.formatted_body.split('<details>')[0];
  for (const text of [request.tool, 'service', 'vaultwarden', request.context.userRequest, '✅ Approve', '❌ Reject']) {
    assert.ok(visible.includes(text));
  }
  assert.ok(!message.body.includes('"arguments":'));
});

test('planning approval explains the run and model use while retaining every nested argument', () => {
  const request = proposal('flowforge.run', {workflow: 'task-analysis', input: {
    project: 'mentory', task_id: 'TASK-12', task_sha256: 'a'.repeat(64), context: 'Context\nwith another line',
  }});
  const message = approvalRequest(request, 'text-emoji-v1');
  assert.ok(message.body.startsWith('🔐 Create plans for TASK-12?'));
  for (const text of ['configured model', 'usage costs', 'source repository stays read-only',
    'workflow', 'task-analysis', 'input', 'project', 'mentory', 'task_id', 'TASK-12', 'task_sha256', 'a'.repeat(64),
    'context', 'Context\nwith another line']) assert.ok(message.body.includes(text));
});

test('generic request fields preserve empty values, container and scalar types without claiming safe effects', () => {
  const args = JSON.parse('{"list":[false,0,"0",null,"",[],{}],"nested":{"__proto__":"literal key","effect":"<script>never HTML</script>"}}');
  const message = approvalRequest(proposal('unknown.action', args), 'text-emoji-v1');
  for (const text of ['effects are not summarized', 'list', 'List:', 'No (false)', '0', '“0”', 'None (null)',
    '“”', 'Empty list ([])', 'Empty object ({})', 'nested', '__proto__', 'literal key', '<script>never HTML</script>']) {
    assert.ok(message.body.includes(text));
  }
  assert.ok(!message.formatted_body.includes('<script>'));
  assert.ok(message.formatted_body.includes('&lt;script&gt;never HTML&lt;/script&gt;'));
  assert.ok(!message.body.includes('No services will restart'));
});

test('dummy request reads as a confirmation request and preserves test-only details', () => {
  const message = approvalRequest(proposal('ui-test.noop', {test_only: true, effect: 'Post a demo confirmation only.'}), 'text-emoji-v1');
  assert.ok(message.body.startsWith('🔐 Try the approval controls?'));
  assert.ok(message.body.includes('May I post a confirmation message'));
  assert.ok(message.body.includes('no paid calls will be made'));
  assert.ok(message.body.includes('test_only'));
  assert.ok(message.body.includes('Yes (true)'));
  assert.ok(message.body.includes('Post a demo confirmation only.'));
});

test('workflow snapshot preserves its initial persisted fields and plan order', () => {
  const run = {status: 'DONE', task_id: 'TASK-12', run_id: 'run', outputs: {
    'grounded-plan.md': 'Grounded', 'runner.log': 'Private', 'concept-plan.md': 'Concept',
  }};
  const original = structuredClone(run);
  assert.deepEqual(workflowDelivery(run), {
    task: 'TASK-12', runId: 'run', outcome: 'DONE', status: 'pending',
    notice: {body: 'FlowForge planning completed: task TASK-12, run run. Outcome: DONE. Available plans: concept-plan.md, grounded-plan.md.'},
    files: [
      {name: 'concept-plan.md', text: 'Concept', uploadStatus: 'pending', uploadAttempts: 0},
      {name: 'grounded-plan.md', text: 'Grounded', uploadStatus: 'pending', uploadAttempts: 0},
    ],
  });
  assert.deepEqual(run, original);
});

test('missing outputs retain the exact empty snapshot and missing-plan fallback', () => {
  const delivery = workflowDelivery({status: 'DONE'});
  assert.deepEqual(delivery, {
    task: 'unknown', runId: 'unknown', outcome: 'DONE', status: 'pending',
    notice: {body: 'FlowForge planning completed: task unknown, run unknown. Outcome: DONE. Available plans: none.'},
    files: [],
  });
  assert.deepEqual(workflowFallback(delivery), {body:
    'FlowForge attachment delivery incomplete: task unknown, run unknown. Undelivered files: none.' +
    ' Not returned by gateway: concept-plan.md, grounded-plan.md.' +
    ' Bounded text fallback follows. Full available sanitized plans are retained in relay state; uncertain uploads require operator review.'});
});

test('workflow labels replace control characters before applying the existing character limit', () => {
  const delivery = workflowDelivery({status: 'DONE', task_id: 'task\r\n\t' + 'x'.repeat(100), run_id: 42});
  assert.equal(delivery.task, 'task   ' + 'x'.repeat(93));
  assert.equal(delivery.runId, '42');
  assert.equal(delivery.notice.body,
    `FlowForge planning completed: task ${'task   ' + 'x'.repeat(93)}, run 42. Outcome: DONE. Available plans: none.`);
});

test('failure notices preserve code filtering and omit outputs from the snapshot', () => {
  for (const error of ['INTERRUPTED_REVIEW_REQUIRED', 'A' + 'X'.repeat(79), undefined, '',
    'lowercase', '1INVALID', 'INVALID-CODE', 'A'.repeat(81), 'Private traceback\nsecret']) {
    const expected = error === 'INTERRUPTED_REVIEW_REQUIRED' || error === 'A' + 'X'.repeat(79)
      ? error : 'PLANNING_PIPELINE_FAILED';
    assert.deepEqual(workflowDelivery({status: 'FAILED', task_id: 'task', run_id: 'run', error,
      outputs: {'concept-plan.md': 'Private'}}), {
      task: 'task', runId: 'run', outcome: 'FAILED', status: 'pending',
      notice: {body: `FlowForge planning failed: task task, run run. Outcome: FAILED. Error: ${expected}.`},
      files: [],
    });
  }
});

test('fallback truncates each pending plan at 3000 UTF-8 bytes without splitting a code point', () => {
  for (const [text, excerpt, truncated] of [
    ['ż'.repeat(1499) + '🧭tail', 'ż'.repeat(1499), true],
    ['🧭'.repeat(750) + 'ż', '🧭'.repeat(750), true],
    ['ż'.repeat(1500), 'ż'.repeat(1500), false],
  ]) {
    const delivery = {task: 'task', runId: 'run', files: [
      {name: 'concept-plan.md', text}, {name: 'grounded-plan.md', text},
    ]};
    const original = structuredClone(delivery);
    const section = name => `\n\n${name}\n${excerpt}${truncated ? '\n[Truncated; full sanitized plan retained in relay state.]' : ''}`;
    assert.deepEqual(workflowFallback(delivery), {body:
      'FlowForge attachment delivery incomplete: task task, run run. Undelivered files: concept-plan.md, grounded-plan.md.' +
      ' Bounded text fallback follows. Full available sanitized plans are retained in relay state; uncertain uploads require operator review.' +
      section('concept-plan.md') + section('grounded-plan.md')});
    assert.deepEqual(delivery, original);
  }
});

test('uncertain restart messages take precedence over verification and allow an absent outcome', () => {
  for (const record of [
    {status: 'UNCERTAIN', arguments: {service: 'app'}},
    {status: 'DONE', arguments: {service: 'app'}, outcome: {data: {
      restart: {status: 'uncertain'}, verification: {status: 'healthy'},
    }}},
  ]) {
    assert.equal(restartResultText('approval-id', record),
      'Approval approval-id: app restart outcome is uncertain. Inspect safely; do not retry automatically.');
  }
});

test('unknown or missing restart verification retains the unavailable message', () => {
  for (const verification of [undefined, {status: 'unknown'}]) {
    assert.equal(restartResultText('approval-id', {arguments: {service: 'app'}, outcome: {data: {verification}}}),
      'Approval approval-id: Docker acknowledged the app restart. Container verification is unavailable. Docker state only; application recovery and external reachability were not checked.');
  }
});

test('compact restart results preserve verification limits and never mark unhealthy or uncertain restarts successful', () => {
  for (const status of ['healthy', 'running_no_healthcheck', 'unhealthy', 'stopped', 'starting_timeout', 'unavailable', 'unknown']) {
    const record = {tool: 'homelab.restartService', status: 'DONE', arguments: {service: 'app'},
      outcome: {data: {restart: {status: 'acknowledged'}, verification: {status}}}};
    const message = compactApprovalResult('id', record);
    assert.ok(message.body.startsWith('Restart acknowledged by Docker'));
    assert.ok(message.body.includes('application recovery and external reachability were not checked'));
    assert.ok(!message.body.includes('✅'));
    if (status === 'unhealthy') assert.ok(message.body.includes('running but unhealthy'));
    if (status === 'unknown') assert.ok(message.body.includes('verification is unavailable'));
    record.status = 'UNCERTAIN';
    const uncertain = compactApprovalResult('id', record);
    assert.ok(uncertain.body.startsWith('⚠️ Restart outcome uncertain'));
    assert.ok(uncertain.body.includes('do not retry automatically'));
    assert.ok(!uncertain.body.includes('Docker reports healthy'));
  }
});

test('compact planning notices retain identifiers, outcome and filenames without interpreting them as HTML', () => {
  const done = workflowDelivery({status: 'DONE', task_id: '<task>', run_id: 'run&1',
    outputs: {'concept-plan.md': 'Concept', 'grounded-plan.md': 'Grounded'}}, true);
  assert.ok(done.notice.body.includes('Task: <task>\nRun: run&1\nOutcome: DONE'));
  assert.ok(done.notice.body.includes('concept-plan.md, grounded-plan.md'));
  assert.ok(done.notice.formatted_body.includes('&lt;task&gt;'));
  assert.ok(done.notice.formatted_body.includes('run&amp;1'));
  assert.ok(!done.notice.body.includes('✅'));
  const failed = workflowDelivery({status: 'FAILED', error: '<script>secret</script>'}, true);
  assert.ok(failed.notice.body.includes('PLANNING_PIPELINE_FAILED'));
  assert.ok(!failed.notice.formatted_body.includes('secret'));
});
