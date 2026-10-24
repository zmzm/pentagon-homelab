function textPrefix(text, limit) {
  let current = '', bytes = 0;
  for (const character of text) {
    const size = Buffer.byteLength(character);
    if (bytes + size > limit) break;
    current += character; bytes += size;
  }
  return current;
}

export const planNames = ['concept-plan.md', 'grounded-plan.md'];
const label = value => String(value ?? 'unknown').replace(/[\r\n\t]/g, ' ').slice(0, 100);

// Only the authenticated gateway response enters this snapshot. In particular, there
// is no FlowForge filesystem access or second model call in the delivery path.
export function workflowDelivery(run) {
  const files = run.status === 'DONE' ? planNames.filter(name => typeof run.outputs?.[name] === 'string' && run.outputs[name].length)
    .map(name => ({name, text: run.outputs[name], uploadStatus: 'pending', uploadAttempts: 0})) : [];
  const task = label(run.task_id), runId = label(run.run_id);
  const error = /^[A-Z][A-Z0-9_]{0,79}$/.test(run.error) ? run.error : 'PLANNING_PIPELINE_FAILED';
  const body = run.status === 'DONE'
    ? `FlowForge planning completed: task ${task}, run ${runId}. Outcome: DONE. Available plans: ${files.map(file => file.name).join(', ') || 'none'}.`
    : `FlowForge planning failed: task ${task}, run ${runId}. Outcome: FAILED. Error: ${error}.`;
  return {task, runId, outcome: run.status, status: 'pending', notice: {body}, files};
}

export function workflowFallback(delivery) {
  const missing = planNames.filter(name => !delivery.files.some(file => file.name === name));
  const pending = delivery.files.filter(file => !file.eventId);
  let body = `FlowForge attachment delivery incomplete: task ${delivery.task}, run ${delivery.runId}. Undelivered files: ${pending.map(file => file.name).join(', ') || 'none'}.`;
  if (missing.length) body += ` Not returned by gateway: ${missing.join(', ')}.`;
  body += ' Bounded text fallback follows. Full available sanitized plans are retained in relay state; uncertain uploads require operator review.';
  for (const file of pending) {
    const excerpt = textPrefix(file.text, 3000);
    body += `\n\n${file.name}\n${excerpt}${excerpt.length < file.text.length ? '\n[Truncated; full sanitized plan retained in relay state.]' : ''}`;
  }
  return {body};
}

export function restartResultText(id, record) {
  const data = record.outcome?.data;
  const service = record.arguments.service;
  if (record.status === 'UNCERTAIN' || data?.restart?.status === 'uncertain') {
    return `Approval ${id}: ${service} restart outcome is uncertain. Inspect safely; do not retry automatically.`;
  }
  const states = {
    healthy: 'Container is running and Docker reports healthy.',
    running_no_healthcheck: 'Container is running; no health check is configured.',
    unhealthy: 'Container is running but unhealthy.',
    stopped: 'Container is stopped or is not in the running state.',
    starting_timeout: 'Container was still starting when the verification deadline expired.',
    unavailable: 'Container verification is unavailable.',
  };
  const state = states[data.verification?.status] || states.unavailable;
  return `Approval ${id}: Docker acknowledged the ${service} restart. ${state} Docker state only; application recovery and external reachability were not checked.`;
}
