import { check } from './common.mjs';

// 15s restart + 10s verification < 30s gateway upstream < 35s relay/MCP < 40s tool.
export const RESTART_TIMEOUT_MS = 15000;
export const VERIFICATION_WINDOW_MS = 10000;
const INSPECT_TIMEOUT_MS = 2000;
const POLL_INTERVAL_MS = 500;
const clock = {now: () => performance.now(), sleep: ms => new Promise(resolve => setTimeout(resolve, ms))};

export function uncertainRestart(service) {
  return {service, restarted: null, restart: {status: 'uncertain'},
    verification: {status: 'not_attempted', source: 'docker'}};
}

function observation(info) {
  const state = info?.State;
  check(state && typeof state.Running === 'boolean' &&
    ['created', 'running', 'paused', 'restarting', 'removing', 'exited', 'dead'].includes(state.Status));
  const observed = {status: state.Status, running: state.Running};
  // Return only these state fields, never inspect configuration or health-check output.
  if (!state.Running || state.Status !== 'running') return {status: 'stopped', observation: observed};
  check(info.Config && typeof info.Config === 'object' && !Array.isArray(info.Config));
  const healthcheck = info.Config.Healthcheck;
  if (healthcheck == null || (Array.isArray(healthcheck.Test) &&
      (healthcheck.Test.length === 0 || healthcheck.Test[0] === 'NONE'))) {
    return {status: 'running_no_healthcheck', observation: observed};
  }
  check(Array.isArray(healthcheck.Test) && ['CMD', 'CMD-SHELL'].includes(healthcheck.Test[0]));
  check(['healthy', 'unhealthy', 'starting'].includes(state.Health?.Status));
  observed.health = state.Health.Status;
  return {status: state.Health.Status, observation: observed};
}

async function verify(prefix, request, {now, sleep}) {
  const start = now(), deadline = start + VERIFICATION_WINDOW_MS;
  let attempts = 0, last;
  const result = fields => ({source: 'docker', windowMs: VERIFICATION_WINDOW_MS,
    elapsedMs: Math.max(0, Math.round(now() - start)), attempts, ...fields});
  while (now() < deadline) {
    attempts++;
    let current;
    try {
      const raw = await request(`${prefix}/json`, 'GET', {timeoutMs: Math.min(INSPECT_TIMEOUT_MS, deadline - now())});
      current = observation(JSON.parse(raw.toString()));
    } catch {
      return result({status: 'unavailable'});
    }
    // A response received after the deadline cannot establish recovery within the window.
    if (now() > deadline) return result({status: 'unavailable'});
    last = current;
    if (current.status !== 'starting') return result(current);
    await sleep(Math.min(POLL_INTERVAL_MS, Math.max(0, deadline - now())));
  }
  return result({status: 'starting_timeout', observation: last.observation});
}

export async function restartService(service, prefix, request, timing = clock) {
  try {
    // Exactly one write. A lost acknowledgment must never lead to a retry or verification.
    await request(`${prefix}/restart?t=10`, 'POST', {timeoutMs: RESTART_TIMEOUT_MS});
  } catch {
    return uncertainRestart(service);
  }
  let verification;
  try { verification = await verify(prefix, request, timing); }
  catch { verification = {status: 'unavailable', source: 'docker'}; }
  return {service, restarted: true, restart: {status: 'acknowledged'}, verification};
}
