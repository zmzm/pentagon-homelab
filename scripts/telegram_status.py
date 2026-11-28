#!/usr/bin/env python3
"""Private monitoring commands with a separate durable cursor and reply queue."""
import argparse
import datetime
import fcntl
import html
import json
from pathlib import Path
import time
import urllib.request
from zoneinfo import ZoneInfo

from monitor import ROOT, collect, save_state
import monitor_telegram as telegram

MAX_REPLIES = 100
COMMANDS = [{'command': 'status', 'description': 'Services, RAM, disk and backup health'}]
METHODS = {'getUpdates', 'getWebhookInfo', 'setMyCommands', 'getMyCommands',
           'setChatMenuButton', 'getChatMenuButton'}


def request(token, method, payload):
    if method not in METHODS:
        raise ValueError('Unsupported status-bot method')
    try:
        req = urllib.request.Request('https://api.telegram.org/bot' + token + '/' + method,
            data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.build_opener(telegram.NoRedirect()).open(req, timeout=10) as response:
            raw = response.read(1048577)
        if len(raw) > 1048576:
            raise ValueError('Oversize response')
        value = json.loads(raw)
        if value.get('ok') is not True:
            raise ValueError('Request rejected')
        return value['result']
    except Exception:
        # Telegram embeds the credential in URLs and can echo private payloads.
        raise RuntimeError('Telegram status API request failed') from None


def configure_menu(token, chat_id):
    scope = {'type': 'chat', 'chat_id': chat_id}
    if request(token, 'setMyCommands', {'scope': scope, 'commands': COMMANDS}) is not True:
        raise RuntimeError('Telegram command registration failed')
    if request(token, 'setChatMenuButton', {
            'chat_id': chat_id, 'menu_button': {'type': 'commands'}}) is not True:
        raise RuntimeError('Telegram menu registration failed')
    if (request(token, 'getMyCommands', {'scope': scope}) != COMMANDS
            or request(token, 'getChatMenuButton', {'chat_id': chat_id}) != {'type': 'commands'}):
        raise RuntimeError('Telegram menu verification failed')


def is_status_command(update, chat_id, now):
    message = update.get('message')
    if not isinstance(message, dict):
        return False
    sender = message.get('from', {})
    chat = message.get('chat', {})
    stamp = message.get('date')
    if not isinstance(sender, dict) or not isinstance(chat, dict):
        return False
    return (sender.get('is_bot') is False and str(sender.get('id')) == chat_id
            and chat.get('type') == 'private' and str(chat.get('id')) == chat_id
            and not any(key in message for key in
                        ('edit_date', 'forward_origin', 'forward_from', 'forward_date',
                         'forward_from_chat', 'forward_sender_name', 'sender_chat', 'via_bot'))
            and type(stamp) is int and now - 600 <= stamp <= now + 60
            and isinstance(message.get('text'), str)
            and message['text'].strip().lower() in ('/status', '!status', 'status'))


def memory_line(path=Path('/proc/meminfo')):
    try:
        values = {parts[0].rstrip(':'): int(parts[1])
                  for line in path.read_text().splitlines() if len(parts := line.split()) >= 2}
        total, available = values['MemTotal'], values['MemAvailable']
        if not 0 <= available <= total or total <= 0:
            raise ValueError('Invalid memory observation')
        used = total - available
        return f'🧠 RAM: {used / 1048576:.1f} / {total / 1048576:.1f} GiB used ({used / total:.0%})'
    except (OSError, KeyError, ValueError):
        return '🧠 RAM: unavailable'


def units(text):
    return len(text.encode('utf-16-le')) // 2


def status_text(results, now, memory):
    stamp = datetime.datetime.fromtimestamp(now, ZoneInfo('Europe/Warsaw')).strftime('%d %b %Y %H:%M:%S %Z')
    healthy = sum(result['level'] == 'ok' for result in results.values())
    lines = [f'📊 <b>Current server status</b> — {stamp}',
             f'{healthy}/{len(results)} checks healthy', html.escape(memory), '']
    icons = {'ok': '✅', 'warning': '⚠️', 'critical': '🚨'}
    for key, result in results.items():
        line = f'{icons.get(result["level"], "❔")} {key}: {result["message"]}'
        rendered = html.escape(line[:220] + ('…' if len(line) > 220 else ''))
        if units('\n'.join(lines + [rendered])) > 3700:
            lines.append('… Additional checks omitted; inspect the local journal for details.')
            break
        lines.append(rendered)
    return '\n'.join(lines)


def load_state(path, settings):
    try:
        state = json.loads(path.read_text())
    except FileNotFoundError:
        return {'version': 1, 'bot_id': settings['bot_id'], 'chat_id': settings['chat_id'],
                'offset': None, 'pending': []}
    if (state.get('version') != 1 or state.get('bot_id') != settings['bot_id']
            or state.get('chat_id') != settings['chat_id']
            or (state.get('offset') is not None
                and (type(state['offset']) is not int or state['offset'] < 0))
            or not isinstance(state.get('pending'), list) or len(state['pending']) > MAX_REPLIES):
        raise ValueError('Invalid or mismatched Telegram status state')
    for item in state['pending']:
        if (not isinstance(item, dict) or type(item.get('id')) is not int or item['id'] < 0
                or item.get('status') not in ('queued', 'sending', 'uncertain', 'blocked')
                or type(item.get('attempts')) is not int or not 0 <= item['attempts'] <= 3
                or type(item.get('retry_at')) not in (int, float)
                or not 0 <= item['retry_at'] < 1e12
                or not isinstance(item.get('text'), str) or not 0 < units(item['text']) <= 3800):
            raise ValueError('Invalid Telegram status reply')
        if item['status'] == 'sending':
            item['status'] = 'uncertain'
    return state


def deliver(state, path, token, now, save=save_state):
    item = next((item for item in state['pending']
                 if item['status'] == 'queued' and item['retry_at'] <= now), None)
    if item is None:
        return
    if item['attempts'] >= 3:
        item['status'] = 'blocked'
        save(path, state)
        return
    item['status'] = 'sending'
    item['attempts'] += 1
    save(path, state)
    outcome, delay = telegram.send(token, state['chat_id'], item['text'])
    if outcome == 'confirmed':
        state['pending'].remove(item)
    elif outcome == 'rate_limited' and item['attempts'] < 3:
        item['status'] = 'queued'
        item['retry_at'] = now + max(delay, 30 * 2 ** item['attempts'])
    else:
        item['status'] = 'blocked' if outcome in ('blocked', 'rate_limited') else 'uncertain'
    save(path, state)


def poll(config, settings, token, path):
    state = load_state(path, settings)
    # Persist recovered uncertainty before polling or dispatching another reply.
    save_state(path, state)
    if len(state['pending']) >= MAX_REPLIES:
        # Drain eligible work without acknowledging more incoming commands.
        deliver(state, path, token, time.time())
        print('Telegram status queue at capacity; incoming cursor retained', flush=True)
        return 1
    webhook = request(token, 'getWebhookInfo', {})
    if webhook.get('url') != '':
        raise ValueError('Disable the monitoring bot webhook before polling')
    bootstrap = state['offset'] is None
    updates = request(token, 'getUpdates', {'offset': -1 if bootstrap else state['offset'],
        'limit': 1 if bootstrap else 100, 'timeout': 0, 'allowed_updates': ['message']})
    if (not isinstance(updates, list) or len(updates) > 100
            or any(not isinstance(u, dict) or type(u.get('update_id')) is not int
                   or u['update_id'] < 0 for u in updates)
            or [u['update_id'] for u in updates] != sorted({u['update_id'] for u in updates})):
        raise ValueError('Invalid Telegram updates')
    now = time.time()
    commands = [u for u in updates if not bootstrap and u['update_id'] >= state['offset']
                and is_status_command(u, settings['chat_id'], now)]
    if commands:
        if len(state['pending']) >= MAX_REPLIES:
            raise ValueError('Telegram status queue requires review')
        # Coalesce a burst into one fresh report; commands never execute shell text.
        text = status_text(collect(config, now), now, memory_line())
        state['pending'].append({'id': commands[-1]['update_id'], 'text': text,
                                 'status': 'queued', 'attempts': 0, 'retry_at': 0})
    state['offset'] = max(state['offset'] or 0,
                          updates[-1]['update_id'] + 1 if updates else 0)
    # Freeze report and cursor together before acknowledging updates or sending.
    save_state(path, state)
    deliver(state, path, token, now)
    held = sum(item['status'] in ('uncertain', 'blocked') for item in state['pending'])
    print(f'Telegram status: {len(commands)} commands; {len(state["pending"])} pending; {held} require review', flush=True)
    return int(bool(state['pending']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configure-menu', action='store_true')
    args = parser.parse_args()
    config = json.loads((ROOT / 'monitoring/config.json').read_text())
    settings = telegram.resolve_config(config['notification']['telegram'], ROOT)
    if not settings['enabled']:
        raise ValueError('Telegram monitoring must be enabled')
    token = telegram.load_credentials(ROOT / settings['credentials_file'], settings['bot_id'])
    directory = Path('/var/lib/homelab-monitor')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (directory / 'telegram-status.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.configure_menu:
            configure_menu(token, settings['chat_id'])
            print('Telegram private-chat command menu configured and verified', flush=True)
            return 0
        return poll(config, settings, token, directory / 'telegram-status.json')


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f'Telegram status failed ({type(error).__name__}); inspect private state', flush=True)
        raise SystemExit(1)
