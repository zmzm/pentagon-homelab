import { bounded } from './common.mjs';

export function jsonClient(base, token, prefix = '') {
  return async (method, path, payload, {contentType = 'application/json'} = {}) => {
    const response = await fetch(base + (path.startsWith('/_matrix/media/') ? '' : prefix) + path, {method, headers: {authorization: `Bearer ${token}`, 'content-type': contentType, 'user-agent': 'Pentagon-Approval-Relay/1.0'}, body: payload === undefined ? undefined : Buffer.isBuffer(payload) ? payload : JSON.stringify(payload), redirect: 'error', signal: AbortSignal.timeout(35000)});
    if (!response.ok) {
      // Expose status/retry timing only, never upstream error text or credentials.
      const headerDelayMs = Number(response.headers.get('retry-after')) * 1000;
      let retryAfterMs = Number.isFinite(headerDelayMs) ? headerDelayMs : 0;
      try {
        const error = JSON.parse((await bounded(response.body, 16384)).toString());
        if (Number.isFinite(error.retry_after_ms)) retryAfterMs = Math.max(retryAfterMs, error.retry_after_ms);
      } catch {}
      throw Object.assign(new Error('APPROVAL_RELAY_HTTP_FAILED'), {httpStatus: response.status,
        retryAfterMs: Math.min(3600000, Math.max(0, retryAfterMs))});
    }
    const raw = await bounded(response.body, 1048576);
    return JSON.parse(raw.toString());
  };
}
