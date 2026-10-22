import { timingSafeEqual } from 'node:crypto';

export class Failure extends Error {
  constructor(code, status = 400) { super(code); this.code = code; this.status = status; }
}
export function check(ok, code = 'INVALID_INPUT', status = 400) {
  if (!ok) throw new Failure(code, status);
}
export function authenticate(req, token) {
  const actual = Buffer.from(req.headers.authorization || '');
  const expected = Buffer.from(`Bearer ${token}`);
  check(token?.length >= 32 && actual.length === expected.length && timingSafeEqual(actual, expected), 'UNAUTHORIZED', 401);
}
export function object(value, keys) {
  check(value && typeof value === 'object' && !Array.isArray(value));
  check(Object.keys(value).every(key => keys.includes(key)));
}
export function str(value, max = 4000) { check(typeof value === 'string' && value.length > 0 && value.length <= max); return value; }
export async function bounded(stream, max = 65536) {
  const chunks = []; let size = 0;
  for await (const chunk of stream) {
    size += Buffer.byteLength(chunk); check(size <= max, 'PAYLOAD_TOO_LARGE', 413); chunks.push(Buffer.from(chunk));
  }
  return Buffer.concat(chunks);
}
export async function body(req) {
  try { return JSON.parse((await bounded(req)).toString()); }
  catch (e) { if (e instanceof Failure) throw e; throw new Failure('INVALID_JSON'); }
}
export function redact(value, secrets = []) {
  if (Array.isArray(value)) return value.map(x => redact(x, secrets));
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k,v]) => [k, /password|secret|token|authorization|cookie|api.?key/i.test(k) ? '[REDACTED]' : redact(v, secrets)]));
  if (typeof value !== 'string') return value;
  let text = value;
  for (const secret of secrets.filter(s => typeof s === 'string' && s.length >= 8)) text = text.split(secret).join('[REDACTED]');
  return text.replace(/Bearer\s+[^\s"']+/gi, 'Bearer [REDACTED]')
    .replace(/((?:password|secret|token|api[_-]?key|authorization|cookie)\s*[=:]\s*)(?:"[^"]*"|'[^']*'|[^\s,;]+)/gi, '$1[REDACTED]')
    .replace(/-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----/g, '[REDACTED]');
}
export function send(res, status, value) {
  res.writeHead(status, {'content-type': 'application/json', 'cache-control': 'no-store'});
  res.end(JSON.stringify(value));
}
export async function remote(url, token, payload, method = 'POST') {
  let response;
  try {
    response = await fetch(url, {method, headers: {authorization: `Bearer ${token}`, 'content-type': 'application/json'}, body: method === 'GET' ? undefined : JSON.stringify(payload), signal: AbortSignal.timeout(30000), redirect: 'error'});
    const raw = await bounded(response.body, 131072);
    check(response.ok, 'UPSTREAM_FAILED', 502);
    return JSON.parse(raw.toString());
  } catch (e) { if (e instanceof Failure) throw e; throw new Failure('UPSTREAM_UNAVAILABLE', 502); }
}
