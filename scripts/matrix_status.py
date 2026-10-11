#!/usr/bin/env python3
"""Poll the alerts room for authorized status commands; no resident process."""
import datetime
import hashlib
import json
from pathlib import Path
import time
import urllib.parse

from monitor import ROOT, collect, deliver_pending, matrix_request, save_state


def is_status_command(event, allowed_users):
    content = event.get('content', {})
    return (event.get('type') == 'm.room.message'
            and event.get('sender') in allowed_users
            and content.get('msgtype') == 'm.text'
            and 'm.relates_to' not in content
            and content.get('body', '').strip().lower() in ('!status', 'status', '/status'))


def status_body(results, now):
    healthy = sum(result['level'] == 'ok' for result in results.values())
    stamp = datetime.datetime.fromtimestamp(now, datetime.timezone.utc).isoformat()
    lines = [f'📊 Current server status — {stamp}',
             f'{healthy}/{len(results)} checks healthy', '']
    for key, result in results.items():
        lines.append(f'{result["level"].upper()} [{key}] {result["message"]}')
    return '\n'.join(lines)


def poll(config, credentials, state_path):
    try:
        state = json.loads(state_path.read_text())
    except FileNotFoundError:
        state = {'pending': []}
    # Retry saved replies before advancing the incoming cursor.
    deliver_pending(state, state_path, credentials)
    allowed = config['notification']['allowed_users']
    filters = {'room': {'rooms': [credentials['room_id']],
        'timeline': {'types': ['m.room.message'], 'senders': allowed, 'limit': 100},
        'state': {'types': []}, 'ephemeral': {'types': []}, 'account_data': {'types': []}},
        'presence': {'types': []}, 'account_data': {'types': []}}
    query = {'timeout': '0', 'set_presence': 'offline', 'filter': json.dumps(filters)}
    if state.get('since'):
        query['since'] = state['since']
    response = matrix_request(credentials, 'GET', '/sync?' + urllib.parse.urlencode(query))
    timeline = response.get('rooms', {}).get('join', {}).get(credentials['room_id'], {}).get('timeline', {})
    # Initial sync establishes the cursor; historical messages are not commands.
    commands = [event for event in timeline.get('events', [])
                if state.get('since') and is_status_command(event, allowed)]
    if commands:
        now = time.time()
        body = status_body(collect(config, now), now)
        for event in commands:
            transaction = 'status-' + hashlib.sha256(event['event_id'].encode()).hexdigest()
            state['pending'].append({'transaction_id': transaction, 'body': body})
    state['since'] = response['next_batch']
    save_state(state_path, state)
    deliver_pending(state, state_path, credentials)
    print(f'Status listener: {len(commands)} requests answered', flush=True)


def main():
    config = json.loads((ROOT / 'monitoring/config.json').read_text())
    path = ROOT / config['notification']['credentials_file']
    if path.stat().st_mode & 0o077:
        raise PermissionError('Credentials must be private')
    credentials = json.loads(path.read_text())
    state_path = Path('/var/lib/homelab-monitor/status.json')
    state_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    poll(config, credentials, state_path)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Status listener failed ({type(error).__name__}); retry on next run', flush=True)
        raise SystemExit(1)
