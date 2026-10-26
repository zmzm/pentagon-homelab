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
const restartStates = {
  healthy: 'Container is running and Docker reports healthy.',
  running_no_healthcheck: 'Container is running; no health check is configured.',
  unhealthy: 'Container is running but unhealthy.',
  stopped: 'Container is stopped or is not in the running state.',
  starting_timeout: 'Container was still starting when the verification deadline expired.',
  unavailable: 'Container verification is unavailable.',
};

// Dynamic text is always escaped, including JSON and sanitized plan excerpts.
// This is a small message renderer, not a general Markdown/HTML interpreter.
const html = value => String(value).replace(/[&<>"']/g, character => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
})[character]);

export function compactMessage(title, paragraphs = []) {
  return {
    body: [title, ...paragraphs].join('\n\n'),
    formatted_body: `<p><strong>${html(title)}</strong></p>` +
      paragraphs.map(text => `<p>${html(text).replace(/\n/g, '<br>')}</p>`).join(''),
  };
}

export function approvalControls(style) {
  if (style === 'text-emoji-v1') return [['approve', '✅ Approve'], ['reject', '❌ Reject']];
  if (style === 'text-v1') return [['approve', 'Approve'], ['reject', 'Reject']];
  if (style === undefined) return [['approve', '✅'], ['reject', '❌']];
  return []; // Unknown retained styles cannot authorize a reaction.
}

export function approvalPrompt(request, description, controlStyle) {
  const expiry = new Date(request.expiresAt).toISOString();
  const controls = (controlStyle === 'text-emoji-v1'
    ? 'Tap ✅ Approve to approve this exact action, or ❌ Reject to reject.'
    : controlStyle === 'text-v1'
    ? 'Tap Approve to approve this exact action, or Reject to reject.'
    : 'Tap ✅ to approve this exact action, or ❌ to reject.') +
    ' Your tap takes effect immediately; removing a reaction does not undo it.';
  const fallback = `Text fallback:\n!approve ${request.id}\n!reject ${request.id}`;
  return {
    body: `🔐 Approval required\n\n${description}\n\nExpires: ${expiry}\nApproval: ${request.id}\n\n${controls}\n\n${fallback}`,
    formatted_body: '<p><strong>🔐 Approval required</strong></p>' +
      `<pre><code>${html(description)}</code></pre>` +
      `<p>Expires: ${html(expiry)}<br>Approval: <code>${html(request.id)}</code></p>` +
      `<p>${html(controls)}</p><pre><code>${html(fallback)}</code></pre>`,
  };
}

function requestSummary(request) {
  const args = request.arguments;
  if (request.tool === 'homelab.restartService') return {
    title: `🔐 Restart ${args.service}?`,
    request: 'May I restart this service?',
    effect: 'The service will briefly stop while it restarts. I will report Docker’s state afterward; application access is not checked.',
  };
  if (request.tool === 'flowforge.run' && args.workflow === 'task-analysis') return {
    title: `🔐 Create plans for ${args.input.task_id}?`,
    request: 'May I start a planning run for this task?',
    effect: 'This uses the configured model and may incur usage costs. Only concept and grounded planning steps run; the source repository stays read-only. I will post the available plans here.',
  };
  if (request.tool === 'ui-test.noop') return {
    title: '🔐 Try the approval controls?',
    request: 'May I post a confirmation message to test these controls?',
    effect: 'This is a dummy test. No services will restart, no workflows will run, and no paid calls will be made.',
  };
  return {
    title: '🔐 May I run this action?',
    request: 'Please review the action below and choose whether to continue.',
    effect: 'Approving will run the exact action shown below. Its effects are not summarized for this tool; review all details before approving.',
  };
}

const fieldLabels = {
  service: 'Service', workflow: 'Workflow', input: 'Planning input', project: 'Project',
  task_id: 'Task', task_sha256: 'Task content hash', context: 'Additional context',
  test_only: 'Test only', effect: 'Effect',
};

// Keep every key, value and JSON type visible, without displaying a JSON log.
// Only reference/command metadata may be collapsed; action arguments stay open.
function argumentRows(value, depth = 0) {
  if (value !== null && typeof value === 'object' && Object.keys(value).length) {
    const array = Array.isArray(value);
    const rows = Object.entries(value).map(([key, child]) => {
      const name = array ? `Item ${Number(key) + 1}` :
        Object.hasOwn(fieldLabels, key) ? `${fieldLabels[key]} (${key})` : key;
      const rendered = argumentRows(child, depth + 1);
      return {
        body: `${'  '.repeat(depth)}• ${name}: ${rendered.body}`,
        formatted_body: `<li><strong>${html(name)}:</strong> ${rendered.formatted_body}</li>`,
      };
    });
    return {body: (array ? 'List:\n' : '\n') + rows.map(row => row.body).join('\n'),
      formatted_body: `<${array ? 'ol' : 'ul'}>${rows.map(row => row.formatted_body).join('')}</${array ? 'ol' : 'ul'}>`};
  }
  const text = typeof value === 'string' ? `“${value}”` :
    value === null ? 'None (null)' : value === true ? 'Yes (true)' : value === false ? 'No (false)' :
    Array.isArray(value) ? 'Empty list ([])' : typeof value === 'object' ? 'Empty object ({})' : String(value);
  return {body: text, formatted_body: html(text).replace(/\n/g, '<br>')};
}

export function approvalRequest(request, controlStyle) {
  const summary = requestSummary(request);
  const args = argumentRows(request.arguments);
  const keys = Object.fromEntries(approvalControls(controlStyle));
  const choice = `Choose ${keys.approve} to allow this exact action, or ${keys.reject} to cancel.`;
  const guard = 'Your first choice takes effect immediately. Removing a reaction will not undo it.';
  const expiry = new Date(request.expiresAt);
  const localExpiry = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/Warsaw', dateStyle: 'medium', timeStyle: 'short',
  }).format(expiry) + ' (Warsaw time)';
  const commands = `!approve ${request.id}\n!reject ${request.id}`;
  const reference = `Reference: ${request.id}\nExact expiry (UTC): ${expiry.toISOString()}`;
  return {
    body: `${summary.title}\n\n${summary.request}\n\nWhat will happen: ${summary.effect}\n\n` +
      `You asked:\n${request.context.userRequest}\n\nTool: ${request.tool}\nAction details: ${args.body}\n\n` +
      `${choice}\n${guard}\n\nExpires: ${localExpiry}\n\n${reference}\nIf the chips do not work, send:\n${commands}`,
    formatted_body: `<p><strong>${html(summary.title)}</strong></p><p>${html(summary.request)}</p>` +
      `<p><strong>What will happen:</strong> ${html(summary.effect)}</p>` +
      `<p><strong>You asked:</strong></p><blockquote>${html(request.context.userRequest).replace(/\n/g, '<br>')}</blockquote>` +
      `<p><strong>Tool:</strong> <code>${html(request.tool)}</code></p>` +
      `<p><strong>Action details:</strong></p>${args.formatted_body}` +
      `<p>${html(choice)}<br>${html(guard)}</p><p>Expires: ${html(localExpiry)}</p>` +
      '<details><summary>Reference and text commands</summary>' +
      `<p>${html(reference).replace(/\n/g, '<br>')}</p><p>If the chips do not work, send:</p>` +
      `<pre><code>${html(commands)}</code></pre></details>`,
  };
}

export function compactApprovalResult(id, record) {
  const reference = `Approval: ${id}`;
  if (record.status === 'REJECTED') return compactMessage('❌ Action rejected', ['No action was executed.', reference]);
  if (record.tool === 'homelab.restartService' &&
      (record.status === 'UNCERTAIN' || record.outcome?.data?.restart)) {
    const text = restartResultText(id, record).replace(`Approval ${id}: `, '');
    const uncertain = record.status === 'UNCERTAIN' || record.outcome?.data?.restart?.status === 'uncertain';
    if (uncertain) return compactMessage('⚠️ Restart outcome uncertain', [text, reference]);
    return compactMessage('Restart acknowledged by Docker', [
      `Service: ${record.arguments.service}`,
      restartStates[record.outcome.data.verification?.status] || restartStates.unavailable,
      'Docker state only; application recovery and external reachability were not checked.', reference,
    ]);
  }
  if (record.tool === 'flowforge.run' && record.outcome?.data?.run_id) {
    return compactMessage('⏳ Planning started', [
      `Run: ${record.outcome.data.run_id}`,
      'Only concept and grounded planning steps run; the source repository stays read-only. I will post the completed plans here.', reference,
    ]);
  }
  // Preserve the bounded outcome for tools without a dedicated presentation.
  if (['DONE', 'FAILED'].includes(record.status)) return compactMessage(
    record.status === 'DONE' ? '✅ Action completed' : '❌ Action failed',
    [JSON.stringify(record.outcome).slice(0, 10000), reference]);
  return null;
}

// Only the authenticated gateway response enters this snapshot. In particular, there
// is no FlowForge filesystem access or second model call in the delivery path.
export function workflowDelivery(run, compact = false) {
  const files = run.status === 'DONE' ? planNames.filter(name => typeof run.outputs?.[name] === 'string' && run.outputs[name].length)
    .map(name => ({name, text: run.outputs[name], uploadStatus: 'pending', uploadAttempts: 0})) : [];
  const task = label(run.task_id), runId = label(run.run_id);
  const error = /^[A-Z][A-Z0-9_]{0,79}$/.test(run.error) ? run.error : 'PLANNING_PIPELINE_FAILED';
  const body = run.status === 'DONE'
    ? `FlowForge planning completed: task ${task}, run ${runId}. Outcome: DONE. Available plans: ${files.map(file => file.name).join(', ') || 'none'}.`
    : `FlowForge planning failed: task ${task}, run ${runId}. Outcome: FAILED. Error: ${error}.`;
  const notice = compact ? compactMessage(run.status === 'DONE' ? 'Planning completed' : '❌ Planning failed', [
    `Task: ${task}\nRun: ${runId}\nOutcome: ${run.status}`,
    run.status === 'DONE' ? `Available plans: ${files.map(file => file.name).join(', ') || 'none'}.` : `Error: ${error}.`,
  ]) : {body};
  return {task, runId, outcome: run.status, status: 'pending', notice, files};
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
  const state = restartStates[data.verification?.status] || restartStates.unavailable;
  return `Approval ${id}: Docker acknowledged the ${service} restart. ${state} Docker state only; application recovery and external reachability were not checked.`;
}
