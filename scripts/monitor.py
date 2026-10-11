#!/usr/bin/env python3
"""Short-lived homelab health checks. Emits state changes and reminders to journald."""
import argparse
import datetime
import html
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import urllib.parse
import uuid

ROOT = Path(__file__).resolve().parents[1]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def matrix_request(credentials, method, path, body=None):
    base = credentials['homeserver'].rstrip('/')
    url = urllib.parse.urlsplit(base)
    if url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in ('127.0.0.1', 'localhost', '::1')):
        raise ValueError('Matrix requires HTTPS or loopback HTTP')
    if url.username or url.password or url.query or url.fragment:
        raise ValueError('Invalid Matrix endpoint')
    request = urllib.request.Request(base + '/_matrix/client/v3' + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization': 'Bearer ' + credentials['access_token'],
                 'Content-Type': 'application/json'}, method=method)
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=10) as response:
        return json.load(response)


def send_matrix(credentials, item):
    room = urllib.parse.quote(credentials['room_id'], safe='')
    # Never send plaintext into a room that has since enabled encryption.
    try:
        matrix_request(credentials, 'GET', f'/rooms/{room}/state/m.room.encryption')
    except urllib.error.HTTPError as error:
        if error.code != 404 or json.load(error).get('errcode') != 'M_NOT_FOUND':
            raise
    else:
        raise RuntimeError('Alert room is encrypted')
    matrix_request(credentials, 'PUT', f'/rooms/{room}/send/m.room.message/{item["transaction_id"]}',
                   matrix_content(item['body']))


def matrix_content(body):
    """Keep readable fallback text and escape all content in rich messages."""
    styles = {'CRITICAL': ('🚨', '#E53935'), 'WARNING': ('⚠️', '#F9A825'),
              'RECOVERED': ('✅', '#43A047'), 'OK': ('✅', '#43A047')}
    plain, rich = [], []
    for line in body.splitlines():
        match = re.match(r'^(CRITICAL|WARNING|RECOVERED|OK) \[([^\]]+)\] (.*)$', line)
        if match:
            status, key, message = match.groups()
            emoji, color = styles[status]
            if key == 'disk':
                issue = '💾'
            elif key == 'backup' or key.startswith('backup:'):
                issue = '🗄️'
            elif key == 'docker' or key.startswith('container:'):
                issue = '🐳'
            elif 'matrix' in key.lower():
                issue = '💬'
            elif 'vaultwarden' in key.lower():
                issue = '🔐'
            else:
                issue = '🌐'
            label = f'{emoji} {status} · {issue} {key}'
            plain.append(label + '\n' + message)
            rich.append(f'<span data-mx-color="{color}"><strong>{html.escape(label)}</strong></span>'
                        + '<br>' + html.escape(message))
        else:
            plain.append(line)
            rich.append(html.escape(line))
    return {'msgtype': 'm.text', 'body': '\n'.join(plain),
            'format': 'org.matrix.custom.html', 'formatted_body': '<br>'.join(rich)}


def save_state(path, state):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as output:
        os.chmod(temporary, 0o600)
        json.dump(state, output, indent=2)
    temporary.replace(path)


def deliver_pending(state, path, credentials):
    while state['pending']:
        send_matrix(credentials, state['pending'][0])
        state['pending'].pop(0)
        save_state(path, state)


def run(command):
    return subprocess.run(command, capture_output=True, text=True, timeout=15)


def disk_status(config, usage):
    used = usage.used / usage.total * 100
    free = usage.free / 1024**3
    if used >= config['critical_percent'] or free < config['minimum_free_gib']:
        level = 'critical'
    elif used >= config['warning_percent']:
        level = 'warning'
    else:
        level = 'ok'
    return {'level': level, 'message': f"Disk {config['path']}: {used:.1f}% used, {free:.1f} GiB free"}


def backup_status(operations, config, now):
    backups = [op for op in operations if 'operationBackup' in op
               and not op['operationBackup'].get('dryRun', False)]
    finished = [op for op in backups if op.get('status') not in
                ('STATUS_PENDING', 'STATUS_INPROGRESS')]
    successes = [op for op in backups if op.get('status') == 'STATUS_SUCCESS']
    if not successes:
        return {'level': 'critical', 'message': 'No successful backup run found in Backrest history'}
    newest_success = max(successes, key=lambda op: int(op.get('unixTimeEndMs', 0)))
    age = now - int(newest_success.get('unixTimeEndMs', 0)) / 1000
    if age < -300:
        return {'level': 'critical', 'message': 'Latest backup timestamp is in the future; check server clock'}
    if age > config['maximum_age_hours'] * 3600:
        return {'level': 'critical', 'message': f'Latest successful backup is {age / 3600:.1f} hours old'}
    latest = max(finished, key=lambda op: int(op.get('unixTimeStartMs', 0)))
    status = latest.get('status')
    if status == 'STATUS_WARNING':
        return {'level': 'warning', 'message': 'Latest backup completed with warnings; inspect Backrest'}
    if status != 'STATUS_SUCCESS':
        return {'level': 'critical', 'message': f'Latest backup did not succeed ({status}); inspect Backrest'}
    return {'level': 'ok', 'message': f'Latest successful backup is {max(age, 0) / 3600:.1f} hours old'}


def database_dump_status(config, now):
    path = ROOT / config['path']
    if not path.is_file() or path.stat().st_size == 0:
        return {'level': 'critical', 'message': 'Matrix database dump is missing or empty'}
    age = now - path.stat().st_mtime
    if age < -300:
        return {'level': 'critical', 'message': 'Matrix database dump timestamp is in the future'}
    level = 'critical' if age > config['maximum_age_hours'] * 3600 else 'ok'
    return {'level': level, 'message': f'Matrix database dump is {max(age, 0) / 3600:.1f} hours old'}


def collect(config, now):
    results = {}
    def check(key, function):
        try:
            results[key] = function()
        except Exception as error:
            # Exception strings and response bodies can contain credentials or URLs.
            results[key] = {'level': 'critical', 'message': f'Check could not complete ({type(error).__name__})'}
    check('disk', lambda: disk_status(config['disk'], shutil.disk_usage(config['disk']['path'])))
    containers = {}
    try:
        template = '{"name":{{json .Name}},"state":{{json .State}},"networks":{{json .NetworkSettings.Networks}}}'
        process = run(['docker', 'inspect', '--format', template, *config['containers']])
        for line in process.stdout.splitlines():
            item = json.loads(line)
            containers[item['name'].lstrip('/')] = item
        if process.returncode and not containers:
            raise RuntimeError('Docker unavailable')
    except Exception as error:
        results['docker'] = {'level': 'critical', 'message': f'Docker inspection failed ({type(error).__name__})'}
    for name in config['containers']:
        item = containers.get(name)
        state = item.get('state', {}) if item else {}
        health = state.get('Health', {}).get('Status')
        if state.get('Status') != 'running':
            level, message = 'critical', f"Container {name}: {state.get('Status', 'missing or Docker unavailable')}"
        elif health in ('unhealthy', 'starting'):
            level, message = 'critical', f'Container {name}: health {health}'
        else:
            level, message = 'ok', f'Container {name}: running' + (f', {health}' if health else '')
        results['container:' + name] = {'level': level, 'message': message}
    for target in config['http']:
        def http_check(target=target):
            command = ['curl', '--silent', '--show-error', '--fail', '--max-time', '5']
            if target.get('resolve'):
                command += ['--resolve', target['resolve']]
            if target.get('ca_file'):
                command += ['--cacert', str(ROOT / target['ca_file'])]
            process = run(command + [target['url']])
            if process.returncode or (target.get('expected') and process.stdout.strip() != target['expected']):
                return {'level': 'critical', 'message': f"{target['id']} health endpoint failed"}
            return {'level': 'ok', 'message': f"{target['id']} health endpoint responded"}
        check('http:' + target['id'], http_check)
    def backrest_check():
        backup = config['backrest']
        ip = containers[backup['container']]['networks'][backup['network']]['IPAddress']
        request = urllib.request.Request(
            f'http://{ip}:9898/v1.Backrest/GetOperations',
            data=json.dumps({'selector': {'planId': backup['plan']}}).encode(),
            headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=5) as response:
            body = json.load(response)
        return backup_status(body['operations'], backup, now)
    check('backup', backrest_check)
    if config.get('database_dump'):
        check('backup:matrix-database', lambda: database_dump_status(config['database_dump'], now))
    return results


def transitions(previous, results, now, reminder_seconds):
    messages = []
    state = {}
    for key, result in results.items():
        old = previous.get(key, {})
        changed = old.get('level', 'ok') != result['level']
        reminder = result['level'] != 'ok' and now - old.get('last_notified', 0) >= reminder_seconds
        notified = old.get('last_notified', 0)
        if changed or reminder:
            kind = 'RECOVERED' if result['level'] == 'ok' else result['level'].upper()
            messages.append(f'{kind} [{key}] {result["message"]}')
            notified = now
        state[key] = {**result, 'last_notified': notified}
    return messages, state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Show current checks without changing saved alert state')
    parser.add_argument('--config', type=Path, default=ROOT / 'monitoring/config.json')
    parser.add_argument('--state-dir', type=Path, default=Path('/var/lib/homelab-monitor'))
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    notification = config['notification']
    if notification['type'] not in ('journal', 'matrix'):
        raise RuntimeError('Notification delivery is not configured for that type')
    now = time.time()
    results = collect(config, now)
    if args.check:
        print(json.dumps(results, indent=2))
        return int(any(r['level'] != 'ok' for r in results.values()))
    args.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    state_file = args.state_dir / 'state.json'
    try:
        saved = json.loads(state_file.read_text())
    except FileNotFoundError:
        saved = {}
    messages, checks = transitions(saved.get('checks', {}), results, now, config['reminder_hours'] * 3600)
    for message in messages:
        print(message, flush=True)
    unhealthy = sum(r['level'] != 'ok' for r in results.values())
    print(f'CHECK {len(results)} checks; {unhealthy} problems; {len(messages)} alert changes/reminders', flush=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    state = {'checked_at': stamp, 'checks': checks, 'pending': saved.get('pending', [])}
    if messages and notification['type'] == 'matrix':
        state['pending'].append({'transaction_id': uuid.uuid4().hex,
                                 'body': 'Homelab alerts — ' + stamp + '\n\n' + '\n'.join(messages)})
    # Persist the queue before sending. Transaction IDs make ambiguous retries safe.
    save_state(state_file, state)
    if notification['type'] == 'matrix':
        try:
            secret_file = ROOT / notification['credentials_file']
            if secret_file.stat().st_mode & 0o077:
                raise PermissionError('Matrix credentials must be private')
            credentials = json.loads(secret_file.read_text())
            deliver_pending(state, state_file, credentials)
        except Exception as error:
            print(f'Matrix delivery failed ({type(error).__name__}); {len(state["pending"])} batches queued for retry', flush=True)
            return 1
    # Unhealthy services are reported in alerts; nonzero service exit is reserved
    # for the checker itself failing, so systemd can distinguish those cases.
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
