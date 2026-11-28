import { requestSummary, argumentRows } from './matrix-approval-messages.mjs';

const escape = (value) =>
  String(value).replace(
    /[&<>]/g,
    (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[character],
  );

export function telegramApprovalRequest(request) {
  const summary = requestSummary(request);
  const expiry = new Date(request.expiresAt);
  const localExpiry =
    new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Europe/Warsaw',
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(expiry) + ' (Warsaw time)';
  const sections = [];
  const add = (body, html = escape(body)) => sections.push({ body, html });
  add(summary.title, `<b>${escape(summary.title)}</b>`);
  add(summary.effect);
  add(
    `You asked\n${request.context.userRequest}`,
    `<b>You asked</b>\n<blockquote>${escape(request.context.userRequest)}</blockquote>`,
  );
  const details = argumentRows(request.arguments, 0, true).body.trim();
  add(`Action details\n${details}`, `<b>Action details</b>\n${escape(details)}`);
  add(`Expires: ${localExpiry}`, `<b>Expires:</b> ${escape(localExpiry)}`);
  add(
    'Approve runs this exact action once. Reject cancels it. Your first choice takes effect immediately.',
  );
  const reference = `Reference: ${request.id}\nTool: ${request.tool}\nConversation: ${request.context.sessionId}\nExact expiry (UTC): ${expiry.toISOString()}`;
  add(
    reference,
    `<b>Reference:</b> <code>${escape(request.id)}</code>\n` +
      `<b>Tool:</b> <code>${escape(request.tool)}</code>\n` +
      `<b>Conversation:</b> <code>${escape(request.context.sessionId)}</code>\n` +
      `<b>Exact expiry (UTC):</b> ${escape(expiry.toISOString())}`,
  );
  const extraContext = Object.fromEntries(
    Object.entries(request.context).filter(([key]) => !['sessionId', 'userRequest'].includes(key)),
  );
  if (Object.keys(extraContext).length) {
    const extra = argumentRows(extraContext, 0, true).body.trim();
    add(`Other request details\n${extra}`, `<b>Other request details</b>\n${escape(extra)}`);
  }
  const fallback = `If buttons fail, reply to this message with:\n!approve ${request.id}\nor !reject ${request.id}`;
  add(
    fallback,
    `If buttons fail, reply to this message with:\n<code>!approve ${escape(request.id)}</code>\nor <code>!reject ${escape(request.id)}</code>`,
  );
  return {
    body: sections.map((s) => s.body).join('\n\n'),
    text: sections.map((s) => s.html).join('\n\n'),
    approveLabel:
      request.tool === 'homelab.restartService'
        ? '✅ Approve restart'
        : request.tool === 'flowforge.run' && request.arguments.workflow === 'task-analysis'
          ? '✅ Start planning'
          : '✅ Approve',
  };
}
