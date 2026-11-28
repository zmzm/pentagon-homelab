import { bounded, check } from './common.mjs';

// No raw fetch errors escape: Telegram puts the credential in the request URL.
export function telegramClient(token, fetcher = fetch) {
  check(/^[0-9]+:[A-Za-z0-9_-]+$/.test(token || ''), 'INVALID_TELEGRAM_TOKEN');
  return async (method, payload = {}) => {
    let response;
    let value;
    try {
      const document = payload.document;
      let body;
      if (document) {
        body = new FormData();
        body.set('chat_id', String(payload.chat_id));
        body.set('document', new Blob([document.text], { type: 'text/markdown' }), document.name);
      } else {
        body = JSON.stringify(payload);
      }
      response = await fetcher(`https://api.telegram.org/bot${token}/${method}`, {
        method: 'POST',
        headers: document ? {} : { 'content-type': 'application/json' },
        body,
        redirect: 'error',
        signal: AbortSignal.timeout(15000),
      });
      value = JSON.parse((await bounded(response.body, 1048576)).toString());
    } catch {
      throw new Error('TELEGRAM_OUTCOME_UNCONFIRMED');
    }
    if (!response.ok || value.ok !== true) {
      throw Object.assign(new Error('TELEGRAM_REQUEST_FAILED'), {
        // Only a well-formed Telegram rate-limit rejection is replayable.
        retryAfterMs:
          value.ok === false &&
          value.error_code === 429 &&
          Number.isFinite(value.parameters?.retry_after)
            ? Math.min(3600000, Math.max(3000, value.parameters.retry_after * 1000))
            : undefined,
      });
    }
    return value.result;
  };
}
