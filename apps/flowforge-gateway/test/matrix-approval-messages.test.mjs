import test from 'node:test';
import assert from 'node:assert/strict';
import { workflowDelivery, workflowFallback, restartResultText } from '../src/matrix-approval-messages.mjs';

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
