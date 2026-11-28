import {
  mkdirSync,
  readFileSync,
  writeFileSync,
  renameSync,
  openSync,
  fsyncSync,
  closeSync,
} from 'node:fs';
import { pathToFileURL } from 'node:url';
import { check } from './common.mjs';
import { jsonClient } from './approval-relay-http.mjs';
import { ApprovalRelay } from './matrix-approvals.mjs';
import { workflowDelivery, workflowFallback, planNames } from './matrix-approval-messages.mjs';
import { telegramClient } from './telegram-api.mjs';
import { telegramApprovalRequest } from './telegram-approval-messages.mjs';

const uuid = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}';
const choicePattern = new RegExp(`^(approve|reject):(${uuid})$`);
const commandPattern = new RegExp(`^[!/]?(approve|reject) (${uuid})$`);

export function validateTelegramState(state) {
  check(
    state?.version === 1 &&
      state.prompts &&
      typeof state.prompts === 'object' &&
      !Array.isArray(state.prompts) &&
      (state.offset === undefined || (Number.isSafeInteger(state.offset) && state.offset >= 0)),
    'INVALID_TELEGRAM_RELAY_STATE',
  );
  for (const [id, prompt] of Object.entries(state.prompts)) {
    check(
      new RegExp(`^${uuid}$`).test(id) &&
        prompt &&
        Number.isFinite(prompt.preparedAt) &&
        Number.isFinite(prompt.expiresAt),
      'INVALID_TELEGRAM_RELAY_STATE',
    );
    for (const field of ['executionAttempted', 'finished', 'workflowPending']) {
      check(
        prompt[field] === undefined || typeof prompt[field] === 'boolean',
        'INVALID_TELEGRAM_RELAY_STATE',
      );
    }
    check(
      prompt.eventId === undefined || (Number.isSafeInteger(prompt.eventId) && prompt.eventId > 0),
      'INVALID_TELEGRAM_RELAY_STATE',
    );
    if (prompt.decision) {
      check(
        prompt.decision.id === id &&
          typeof prompt.decision.approve === 'boolean' &&
          prompt.decision.operator === `telegram:${state.chat}` &&
          prompt.decision.telegramChatId === state.chat &&
          prompt.decision.telegramPromptMessageId === String(prompt.eventId) &&
          /^[0-9]+$/.test(prompt.decision.telegramUpdateId),
        'INVALID_TELEGRAM_RELAY_STATE',
      );
    }
    for (const delivery of Object.values(prompt.deliveries || {})) {
      check(
        delivery &&
          ['pending', 'sending', 'sent', 'uncertain', 'failed'].includes(delivery.status) &&
          ['sendMessage', 'sendDocument'].includes(delivery.method) &&
          delivery.payload?.chat_id === state.chat &&
          Number.isInteger(delivery.attempts) &&
          delivery.attempts >= 0 &&
          delivery.attempts <= 3,
        'INVALID_TELEGRAM_RELAY_STATE',
      );
      if (delivery.status === 'sent') {
        check(
          Number.isSafeInteger(delivery.messageId) && delivery.messageId > 0,
          'INVALID_TELEGRAM_RELAY_STATE',
        );
      }
    }
  }
  return state;
}

export function telegramDecision(update, chat, users, prompts, now) {
  if (!Number.isSafeInteger(update.update_id) || update.update_id < 0) {
    return null;
  }
  const callback = update.callback_query;
  if (callback && (typeof callback.id !== 'string' || !callback.id || callback.id.length > 512)) {
    return null;
  }
  const message = callback?.message || update.message;
  const from = callback?.from || message?.from;
  if (
    !message ||
    !from ||
    from.is_bot !== false ||
    message.edit_date ||
    message.chat?.type !== 'private' ||
    String(message.chat.id) !== chat ||
    String(from.id) !== chat ||
    !users.includes(String(from.id))
  ) {
    return null;
  }
  const match = callback
    ? callback.data?.match(choicePattern)
    : message.text?.match(commandPattern);
  if (!match) {
    return null;
  }
  const prompt = prompts[match[2]];
  const messageId = callback ? message.message_id : message.reply_to_message?.message_id;
  if (
    !prompt?.eventId ||
    messageId !== prompt.eventId ||
    prompt.finished ||
    prompt.decision ||
    prompt.expiresAt <= now ||
    !Number.isFinite(prompt.expiresAt)
  ) {
    return null;
  }
  if (
    !callback &&
    (!Number.isFinite(message.date) ||
      message.date * 1000 < prompt.preparedAt - 1000 ||
      message.date * 1000 > now + 60000 ||
      now - message.date * 1000 > 600000)
  ) {
    return null;
  }
  return {
    id: match[2],
    approve: match[1] === 'approve',
    operator: `telegram:${from.id}`,
    telegramUpdateId: String(update.update_id),
    telegramChatId: chat,
    telegramPromptMessageId: String(prompt.eventId),
  };
}

// Reuse the existing stored-action reconciliation/finish logic, while replacing
// Matrix transport and its transaction-ID retry assumptions entirely.
export class TelegramApprovalRelay extends ApprovalRelay {
  constructor({ telegram, chat, ...options }) {
    super(options);
    Object.assign(this, { telegram, chat });
  }

  async deliver(id, key, method, payload) {
    const prompt = this.state.prompts[id];
    prompt.deliveries ||= {};
    const delivery = (prompt.deliveries[key] ||= {
      status: 'pending',
      method,
      payload,
      attempts: 0,
    });
    if (delivery.status === 'sending') {
      delivery.status = 'uncertain';
      this.save(this.state);
    }
    if (delivery.status === 'sent') {
      return delivery.messageId;
    }
    check(delivery.status === 'pending', 'TELEGRAM_DELIVERY_REVIEW_REQUIRED');
    check(!(delivery.retryAt > this.now()), 'TELEGRAM_RATE_LIMITED');
    delivery.status = 'sending';
    delivery.attempts++;
    this.save(this.state);
    let result;
    try {
      result = await this.telegram(delivery.method, delivery.payload);
      check(
        Number.isSafeInteger(result?.message_id) &&
          result.chat?.type === 'private' &&
          String(result.chat.id) === this.chat,
        'INVALID_TELEGRAM_SEND_RESULT',
      );
    } catch (error) {
      delivery.status = error.retryAfterMs
        ? delivery.attempts < 3
          ? 'pending'
          : 'failed'
        : 'uncertain';
      delivery.error = error.retryAfterMs ? 'TELEGRAM_RATE_LIMITED' : 'TELEGRAM_SEND_UNCONFIRMED';
      if (delivery.status === 'pending') {
        delivery.retryAt = this.now() + error.retryAfterMs;
      }
      this.save(this.state);
      // Never attach upstream errors: they can contain credentials in URLs.
      // eslint-disable-next-line preserve-caught-error
      throw new Error('TELEGRAM_DELIVERY_INCOMPLETE');
    }
    delivery.messageId = result.message_id;
    delivery.status = 'sent';
    delete delivery.error;
    this.save(this.state);
    return delivery.messageId;
  }

  async notify(id, suffix, message) {
    const body = typeof message === 'string' ? message : message.body;
    const characters = Array.from(body);
    let messageId;
    for (let offset = 0; offset < characters.length; offset += 3800) {
      messageId = await this.deliver(id, `${suffix}-${offset}`, 'sendMessage', {
        chat_id: this.chat,
        text: characters.slice(offset, offset + 3800).join(''),
      });
    }
    return { event_id: messageId };
  }

  async workflowResult(id, prompt) {
    if (!prompt.workflowDelivery) {
      const { data: run } = await this.gateway('GET', `/approvals/${id}/workflow`);
      if (run.status === 'RUNNING') {
        return;
      }
      check(['DONE', 'FAILED'].includes(run.status), 'INVALID_WORKFLOW_STATUS');
      prompt.workflowDelivery = workflowDelivery(run);
      this.save(this.state);
    }
    const delivery = prompt.workflowDelivery;
    await this.notify(id, 'workflow-notice', delivery.notice);
    for (const file of delivery.files) {
      if (!file.eventId) {
        await this.processOperation(id, 'telegram_document', async () => {
          file.eventId = await this.deliver(id, `file-${file.name}`, 'sendDocument', {
            chat_id: this.chat,
            document: { name: file.name, text: file.text },
          });
          this.save(this.state);
        });
      }
    }
    const complete =
      delivery.outcome === 'FAILED' ||
      planNames.every((name) => delivery.files.some((file) => file.name === name && file.eventId));
    delivery.status = complete ? 'delivered' : 'failed';
    try {
      if (!complete) {
        delivery.fallback ||= workflowFallback(delivery);
        this.save(this.state);
        await this.notify(id, 'workflow-fallback', delivery.fallback);
      }
    } finally {
      // Retain failure records but stop polling when all remaining sends need review.
      prompt.workflowPending =
        !complete && Object.values(prompt.deliveries).some((item) => item.status === 'pending');
      this.save(this.state);
    }
  }

  async tick() {
    if (this.state.offset === undefined) {
      // Fresh install: discard pre-install decisions. On restart use the durable cursor.
      const latest = await this.telegram('getUpdates', {
        offset: -1,
        limit: 1,
        timeout: 0,
        allowed_updates: ['message', 'callback_query'],
      });
      check(Array.isArray(latest), 'INVALID_TELEGRAM_UPDATES');
      check(
        latest.every((update) => Number.isSafeInteger(update.update_id) && update.update_id >= 0),
        'INVALID_TELEGRAM_UPDATES',
      );
      this.state.offset = latest.length ? latest.at(-1).update_id + 1 : 0;
      this.save(this.state);
    }
    const { requests } = await this.gateway('GET', '/approvals');
    for (const request of requests) {
      await this.processOperation(request.id, 'telegram_prompt', async () => {
        let prompt = this.state.prompts[request.id];
        if (!prompt) {
          prompt = this.state.prompts[request.id] = {
            preparedAt: this.now(),
            expiresAt: request.expiresAt,
          };
          this.save(this.state);
        }
        if (prompt.eventId || prompt.finished) {
          return;
        }
        const presentation = telegramApprovalRequest(request);
        if (Array.from(presentation.body).length > 4000) {
          await this.notify(
            request.id,
            'oversize',
            `Approval ${request.id} is too large to review in Telegram. No action will execute. Review or reject it through the operator API.`,
          );
          prompt.finished = true;
          this.save(this.state);
          return;
        }
        prompt.eventId = await this.deliver(request.id, 'prompt', 'sendMessage', {
          chat_id: this.chat,
          text: presentation.text,
          parse_mode: 'HTML',
          link_preview_options: { is_disabled: true },
          reply_markup: {
            inline_keyboard: [
              [
                { text: presentation.approveLabel, callback_data: `approve:${request.id}` },
                { text: '❌ Reject', callback_data: `reject:${request.id}` },
              ],
            ],
          },
        });
        this.save(this.state);
      });
    }
    const updates = await this.telegram('getUpdates', {
      offset: this.state.offset,
      limit: 100,
      timeout: 0,
      allowed_updates: ['message', 'callback_query'],
    });
    check(Array.isArray(updates), 'INVALID_TELEGRAM_UPDATES');
    for (const update of updates) {
      check(
        Number.isSafeInteger(update.update_id) && update.update_id >= 0,
        'INVALID_TELEGRAM_UPDATE',
      );
      if (update.update_id < this.state.offset) {
        continue;
      }
      const decision = telegramDecision(
        update,
        this.chat,
        this.users,
        this.state.prompts,
        this.now(),
      );
      if (decision) {
        this.state.prompts[decision.id].decision = decision;
      }
      // Decision and cursor are saved together before acknowledging updates or executing.
      this.state.offset = update.update_id + 1;
      this.save(this.state);
      if (decision && update.callback_query) {
        // UI acknowledgment follows durable decision storage; it never authorizes execution.
        await this.processOperation(decision.id, 'telegram_callback_ack', () =>
          this.telegram('answerCallbackQuery', {
            callback_query_id: update.callback_query.id,
            text: 'Decision recorded',
          }),
        );
      }
    }
    for (const [id, prompt] of Object.entries(this.state.prompts)) {
      if (prompt.workflowPending) {
        await this.processOperation(id, 'telegram_workflow', () => this.workflowResult(id, prompt));
      } else if (prompt.decision && !prompt.finished) {
        await this.processOperation(id, 'telegram_reconcile', () => this.reconcile(id, prompt));
      } else if (!prompt.finished && prompt.expiresAt <= this.now()) {
        await this.processOperation(id, 'telegram_expiry', () =>
          this.finish(id, prompt, { status: 'EXPIRED', expiresAt: prompt.expiresAt }),
        );
      }
    }
    const done = Object.entries(this.state.prompts).filter(
      ([, p]) =>
        p.finished &&
        !p.workflowPending &&
        Object.values(p.deliveries || {}).every((d) => d.status === 'sent'),
    );
    for (const [id] of done.slice(0, Math.max(0, done.length - 200))) {
      delete this.state.prompts[id];
    }
    this.save(this.state);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const env = process.env;
  const users = (env.TELEGRAM_ALLOWED_USERS || '').split(',').map((x) => x.trim());
  const chat = env.TELEGRAM_HOME_CHAT_ID;
  check(
    env.APPROVER_TOKEN?.length >= 32 &&
      /^[1-9][0-9]{0,15}$/.test(chat || '') &&
      users.every((x) => /^[1-9][0-9]{0,15}$/.test(x)) &&
      users.includes(chat),
    'INVALID_TELEGRAM_RELAY_CONFIG',
  );
  const telegram = telegramClient(env.TELEGRAM_APPROVAL_BOT_TOKEN);
  const directory = '/state';
  mkdirSync(directory, { recursive: true, mode: 0o700 });
  const file = `${directory}/telegram-approvals.json`;
  let state;
  try {
    state = validateTelegramState(JSON.parse(readFileSync(file, 'utf8')));
  } catch (error) {
    if (error.code !== 'ENOENT') {
      // State parser errors can include private retained message content.
      // eslint-disable-next-line preserve-caught-error
      throw new Error('INVALID_TELEGRAM_RELAY_STATE');
    }
    state = { version: 1, prompts: {} };
  }
  const save = (value) => {
    try {
      writeFileSync(`${file}.tmp`, JSON.stringify(value), { mode: 0o600, flush: true });
      renameSync(`${file}.tmp`, file);
      const fd = openSync(directory, 'r');
      try {
        fsyncSync(fd);
      } finally {
        closeSync(fd);
      }
    } catch {
      // Stop before another poll can acknowledge an unpersisted decision/cursor.
      process.stderr.write('TELEGRAM_RELAY_STATE_PERSISTENCE_FAILED\n');
      process.exit(1);
    }
  };
  // Do not delete a webhook or discard its queue automatically.
  const webhook = await telegram('getWebhookInfo');
  check(webhook.url === '', 'TELEGRAM_WEBHOOK_MUST_BE_DISABLED');
  const bot = await telegram('getMe');
  check(bot.is_bot && !users.includes(String(bot.id)), 'INVALID_TELEGRAM_APPROVAL_BOT');
  check(
    ((state.chat === undefined && Object.keys(state.prompts).length === 0) ||
      state.chat === chat) &&
      (state.botId === undefined || state.botId === bot.id),
    'TELEGRAM_RELAY_IDENTITY_CHANGED',
  );
  Object.assign(state, { chat, botId: bot.id });
  save(state);
  const relay = new TelegramApprovalRelay({
    telegram,
    chat,
    users,
    state,
    save,
    gateway: jsonClient(env.GATEWAY_URL, env.APPROVER_TOKEN),
  });
  while (true) {
    try {
      await relay.tick();
    } catch {
      process.stdout.write('{"event":"telegram_approval_relay_retry","status":"failed"}\n');
    }
    await new Promise((resolve) => setTimeout(resolve, 3000));
  }
}
