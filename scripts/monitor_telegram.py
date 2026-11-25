"""Outbound-only monitoring summaries; never forward check details to Telegram."""
import datetime
import html
import json
import math
import os
import random
import re
import stat
import urllib.error
import urllib.request
import uuid
from zoneinfo import ZoneInfo

MAX_PENDING = 100
MAX_ATTEMPTS = 3
LABELS = {'disk': 'Disk space', 'backup': 'Backups',
          'backup:matrix-database': 'Database backup', 'backup:recovery': 'Recovery verification',
          'docker': 'Container engine', 'delivery-test': 'TEST delivery'}
STATUSES = {'queued', 'sending', 'uncertain', 'blocked'}
SEVERITIES = (('CRITICAL', '🚨', 'Critical'), ('WARNING', '⚠️', 'Warning'),
              ('RECOVERED', '✅', 'Recovered'))
CATEGORY_ICONS = {'Disk space': '💾', 'Backups': '🗄️', 'Database backup': '🗃️',
                  'Recovery verification': '🛟', 'Container engine': '🐳',
                  'Containers': '🐳', 'Service endpoints': '🌐',
                  'Health check': '🩺', 'TEST delivery': '🧪'}


class QueueFull(RuntimeError):
    pass


def validate_config(config):
    if not isinstance(config, dict) or type(config.get('enabled')) is not bool:
        raise ValueError('Invalid Telegram configuration')
    if not config['enabled']:
        return
    for key in ('bot_id', 'chat_id'):
        if (not isinstance(config.get(key), str) or not re.fullmatch(r'[1-9][0-9]{0,15}', config[key])
                or int(config[key]) >= 2 ** 52):
            raise ValueError('Telegram requires one numeric bot and private recipient')
    if not isinstance(config.get('credentials_file'), str) or not config['credentials_file']:
        raise ValueError('Telegram credentials file is required')


def load_credentials(path, bot_id):
    # O_NOFOLLOW also rejects a symlink at the credential boundary.
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor) as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.geteuid():
            raise PermissionError('Telegram credentials must be private and owned by the runner')
        raw = source.read(4097)
    if len(raw) > 4096:
        raise ValueError('Telegram credential file is too large')
    if path.suffix == '.env':
        token = env_token(raw)
    else:
        # Retain the original JSON credential contract for existing installations.
        credentials = json.loads(raw)
        token = credentials.get('bot_token') if isinstance(credentials, dict) else None
    if not isinstance(token, str) or not re.fullmatch(re.escape(bot_id) + r':[A-Za-z0-9_-]{20,100}', token):
        raise ValueError('Telegram token does not match the configured bot')
    return token


def env_token(raw):
    """Read one literal assignment without sourcing or expanding shell content."""
    token = None
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition('=')
        if not separator or key.strip() != 'TELEGRAM_BOT_TOKEN' or token is not None:
            raise ValueError('Expected one TELEGRAM_BOT_TOKEN assignment')
        value = value.strip()
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError('Invalid quoted Telegram token')
            value = value[1:-1]
        token = value
    return token


def summary(messages):
    """Project into fixed labels, ignoring all free text, URLs, names and errors."""
    counts = {}
    for message in messages:
        match = re.match(r'^(CRITICAL|WARNING|RECOVERED) \[([^\]\n]+)\] ', message)
        if not match:
            raise ValueError('Invalid alert transition')
        level, key = match.groups()
        label = LABELS.get(key, 'Containers' if key.startswith('container:') else
                           'Service endpoints' if key.startswith('http:') else 'Health check')
        pair = (level, label)
        counts[pair] = counts.get(pair, 0) + 1
    return '\n'.join(f'{level}: {label} ({count})' for (level, label), count in sorted(counts.items()))


def message_text(item):
    """Render only validated categories; keep the stored summary format unchanged."""
    if not valid_summary(item['summary']):
        raise ValueError('Invalid Telegram summary')
    stamp = datetime.datetime.fromtimestamp(item['created_at'], ZoneInfo('Europe/Warsaw'))
    title = '🧪 <b>Homelab monitor · Test</b>' if 'TEST delivery' in item['summary'] else '🏠 <b>Homelab monitor</b>'
    parts = [title, '🕒 <i>' + html.escape(stamp.strftime('%d %b %Y · %H:%M %Z')) + '</i>']
    rows = [re.fullmatch(r'(CRITICAL|WARNING|RECOVERED): (.+) \(([0-9]+)\)', line).groups()
            for line in item['summary'].splitlines()]
    for level, icon, label in SEVERITIES:
        entries = [(category, int(count)) for severity, category, count in rows if severity == level]
        if not entries:
            continue
        total = sum(count for _, count in entries)
        heading = f'{icon} <b>{label} · {total} ' + ('check' if total == 1 else 'checks') + '</b>'
        lines = [CATEGORY_ICONS[category] + ' ' + html.escape(category)
                 + (f' × {count}' if count > 1 else '') for category, count in entries]
        parts.extend(['', heading, '<blockquote>' + '\n'.join(lines) + '</blockquote>'])
    parts.extend(['', '📋 <i>Details in Matrix or the local journal.</i>',
                  '<tg-spoiler>Reference: ' + html.escape(item['id']) + '</tg-spoiler>'])
    text = '\n'.join(parts)
    if len(text.encode('utf-16-le')) // 2 > 4096:
        raise ValueError('Telegram message is too large')
    return text


def load_state(path, config):
    try:
        state = json.loads(path.read_text())
    except FileNotFoundError:
        return {'version': 1, 'bot_id': config['bot_id'], 'chat_id': config['chat_id'],
                'checks': {}, 'pending': []}
    if (not isinstance(state, dict) or type(state.get('version')) is not int or state['version'] != 1
            or state.get('bot_id') != config['bot_id'] or state.get('chat_id') != config['chat_id']
            or not isinstance(state.get('checks'), dict) or not isinstance(state.get('pending'), list)
            or len(state['pending']) > MAX_PENDING):
        raise ValueError('Invalid or mismatched Telegram state; review required')
    for check in state['checks'].values():
        if (not isinstance(check, dict) or check.get('level') not in ('ok', 'warning', 'critical')
                or type(check.get('last_notified')) not in (int, float)
                or not math.isfinite(check['last_notified']) or check['last_notified'] < 0):
            raise ValueError('Invalid Telegram check state')
    for item in state['pending']:
        if (not isinstance(item, dict) or not isinstance(item.get('id'), str)
                or not re.fullmatch(r'[0-9a-f]{32}', item['id'])
                or item.get('status') not in STATUSES
                or type(item.get('attempts')) is not int or not 0 <= item['attempts'] <= MAX_ATTEMPTS
                or type(item.get('retry_at')) not in (int, float)
                or not math.isfinite(item['retry_at']) or item['retry_at'] < 0
                or type(item.get('created_at')) not in (int, float)
                or not 0 <= item['created_at'] <= 253402300799
                or not isinstance(item.get('summary'), str) or not valid_summary(item['summary'])):
            raise ValueError('Invalid Telegram delivery state')
        if item['status'] == 'sending':
            item['status'] = 'uncertain'
    return state


def valid_summary(value):
    # Loaded queue content must satisfy the same output boundary as new content.
    labels = '|'.join(re.escape(label) for label in (*LABELS.values(), 'Containers', 'Service endpoints', 'Health check'))
    return 0 < len(value) <= 2000 and all(
        re.fullmatch(rf'(CRITICAL|WARNING|RECOVERED): ({labels}) \([1-9][0-9]*\)', line)
        for line in value.splitlines())


def enqueue(state, messages, checks, now):
    if messages:
        if len(state['pending']) >= MAX_PENDING:
            raise QueueFull('Telegram queue full; Matrix remains available')
        projected = summary(messages)
        if not valid_summary(projected):
            raise ValueError('Invalid Telegram summary')
        state['pending'].append({'id': uuid.uuid4().hex, 'summary': projected, 'created_at': now,
                                 'status': 'queued', 'attempts': 0, 'retry_at': 0})
    # Retain only level/timing per source key; free-text messages are unnecessary.
    state['checks'] = {key: {'level': check['level'], 'last_notified': check['last_notified']}
                       for key, check in checks.items()}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def send(token, chat_id, text):
    """Return confirmed/rejected/uncertain evidence, never raw provider errors."""
    request = urllib.request.Request('https://api.telegram.org/bot' + token + '/sendMessage',
        data=json.dumps({'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML',
                         'link_preview_options': {'is_disabled': True}, 'protect_content': True}).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    http_status = 200
    try:
        try:
            response = urllib.request.build_opener(NoRedirect()).open(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
            http_status = error.code
        with response:
            raw = response.read(65537)
        if len(raw) > 65536:
            return 'uncertain', 0
        body = json.loads(raw)
        if not isinstance(body, dict):
            return 'uncertain', 0
        if http_status == 200 and body.get('ok') is True:
            result = body.get('result', {})
            chat = result.get('chat', {})
            if (type(result.get('message_id')) is int and result['message_id'] > 0
                    and type(chat.get('id')) is int and str(chat['id']) == chat_id
                    and chat.get('type') == 'private'):
                return 'confirmed', 0
        if body.get('ok') is False and type(body.get('error_code')) is int:
            code = body['error_code']
            if code == 429 and http_status in (200, 429):
                delay = body.get('parameters', {}).get('retry_after')
                if type(delay) is int and 1 <= delay <= 604800:
                    return 'rate_limited', delay
            if 400 <= code < 500 and code not in (408, 429):
                return 'blocked', 0
    except Exception:
        # The URL contains the token. Neither exception nor response is logged.
        pass
    return 'uncertain', 0


def deliver(state, path, token, now, save):
    # One request per scheduled run. Held items do not block later health changes.
    item = next((item for item in state['pending'] if item['status'] == 'queued'), None)
    if item is None or item['retry_at'] > now:
        return
    if item['attempts'] >= MAX_ATTEMPTS:
        item['status'] = 'blocked'
        save(path, state)
        return
    item['status'] = 'sending'
    item['attempts'] += 1
    save(path, state)  # If this fails, dispatch is forbidden.
    outcome, delay = send(token, state['chat_id'], message_text(item))
    if outcome == 'confirmed':
        state['pending'].remove(item)
    elif outcome == 'rate_limited' and item['attempts'] < MAX_ATTEMPTS:
        item['status'] = 'queued'
        item['retry_at'] = now + max(delay, 30 * 2 ** item['attempts']) + random.uniform(0, 30)
    else:
        item['status'] = 'blocked' if outcome in ('blocked', 'rate_limited') else 'uncertain'
    save(path, state)
