import http from 'node:http';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { authenticate, body, bounded, check, Failure, object, send, redact } from './common.mjs';
import { operation, validatePolicy } from './operations.mjs';

export function dockerRequest(path, method = 'GET', socketPath = '/var/run/docker.sock') {
  return new Promise((resolve, reject) => {
    const req = http.request({socketPath, path, method, timeout: 15000}, async res => {
      try { const data = await bounded(res, 131072); check(res.statusCode < 300, res.statusCode === 404 ? 'CONTAINER_NOT_FOUND' : 'DOCKER_FAILED', 502); resolve(data); } catch (e) { reject(e); }
    });
    req.on('timeout', () => req.destroy(new Failure('DOCKER_TIMEOUT', 504)));
    req.on('error', reject); req.end();
  });
}
export function decodeLogs(data, tty) {
  if (tty) return data.toString('utf8');
  const chunks = []; let offset = 0;
  while (offset + 8 <= data.length) {
    const length = data.readUInt32BE(offset + 4); check(offset + 8 + length <= data.length, 'INVALID_DOCKER_LOGS', 502);
    chunks.push(data.subarray(offset + 8, offset + 8 + length)); offset += 8 + length;
  }
  check(offset === data.length, 'INVALID_DOCKER_LOGS', 502); return Buffer.concat(chunks).toString('utf8');
}
export function createBroker(env, policy, request = dockerRequest) {
  validatePolicy(policy); check(env.BROKER_TOKEN?.length >= 32, 'INVALID_AUTH_CONFIG');
  return http.createServer(async (req, res) => {
    try {
      authenticate(req, env.BROKER_TOKEN); check(req.url === '/execute' && req.method === 'POST', 'NOT_FOUND', 404);
      const input = await body(req); object(input, ['tool', 'arguments']);
      check(['homelab.inspectService', 'homelab.getLogs', 'homelab.restartService'].includes(input.tool), 'UNKNOWN_TOOL', 404); const permission = operation(input.tool, input.arguments, policy);
      check(permission !== 'DENY', 'POLICY_DENIED', 403);
      // Only the authenticated gateway is attached to this network and holds this credential.
      const name = encodeURIComponent(policy.services[input.arguments.service].container);
      const prefix = `/containers/${name}`;
      if (input.tool === 'homelab.restartService') {
        await request(`${prefix}/restart?t=10`, 'POST'); return send(res, 200, {restarted: true, service: input.arguments.service});
      }
      const info = JSON.parse((await request(`${prefix}/json`)).toString());
      if (input.tool === 'homelab.inspectService') {
        // Docker inspect contains environment secrets, labels and host mounts. Never return them.
        return send(res, 200, {service: input.arguments.service, status: info.State.Status, running: info.State.Running, restartCount: info.RestartCount, health: info.State.Health?.Status, exitCode: info.State.ExitCode, startedAt: info.State.StartedAt, finishedAt: info.State.FinishedAt});
      }
      const query = new URLSearchParams({stdout: '1', stderr: '1', timestamps: '1', tail: String(input.arguments.lines || 100)});
      if (input.arguments.since) query.set('since', String(Math.floor(Date.parse(input.arguments.since) / 1000)));
      const logs = decodeLogs(await request(`${prefix}/logs?${query}`), info.Config.Tty);
      const secrets = (info.Config.Env || []).map(item => item.split(/=(.*)/s)).filter(([key]) => /PASSWORD|TOKEN|SECRET|KEY|CREDENTIAL/i.test(key)).map(([,value]) => value);
      return send(res, 200, {service: input.arguments.service, logs: redact(logs, secrets)});
    } catch (err) { send(res, err instanceof Failure ? err.status : 502, {success: false, error: err instanceof Failure ? err.code : 'DOCKER_UNAVAILABLE'}); }
  });
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) createBroker(process.env, JSON.parse(readFileSync('/config/policy.json'))).listen(8081, '0.0.0.0');
