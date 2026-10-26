"""Publish an allowlisted display summary from private monitoring state."""
import argparse
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import tempfile

LEVELS = {'ok', 'warning', 'critical'}
AGE_PATTERNS = {
    'backup': r'Latest successful backup is ([0-9]+(?:\.[0-9]+)?) hours old',
    'backup:matrix-database': r'Matrix database dump is ([0-9]+(?:\.[0-9]+)?) hours old',
    'backup:recovery': r'Last successful recovery verification is ([0-9]+(?:\.[0-9]+)?) hours old',
}


def summary(state, config):
    if not isinstance(state, dict) or not isinstance(state.get('checks'), dict):
        raise ValueError('Invalid monitoring state')
    stamp = state.get('checked_at')
    checked = datetime.fromisoformat(stamp)
    if checked.tzinfo is None:
        raise ValueError('Monitoring timestamp requires a timezone')
    checks = state['checks']

    def level(key):
        result = checks.get(key)
        value = result.get('level') if isinstance(result, dict) else None
        return value if value in LEVELS else 'unknown'

    def names(values, limit):
        if not isinstance(values, list) or not 0 < len(values) <= limit:
            raise ValueError('Invalid monitoring scope')
        if any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,48}',v) for v in values):
            raise ValueError('Invalid service identifier')
        return values

    containers = names(config['containers'], 32)
    http = names([item['id'] for item in config['http']], 8)
    backups = {}
    for key, pattern in AGE_PATTERNS.items():
        entry = checks.get(key, {})
        message = entry.get('message', '') if isinstance(entry, dict) else ''
        match = re.fullmatch(pattern, message) if isinstance(message, str) else None
        age = float(match[1]) if match else None
        if age is not None and (not math.isfinite(age) or not 0 <= age < 1e6):
            age = None
        status = level(key)
        if status == 'ok' and age is None:
            # An initial recovery run is not evidence of a successful restore.
            status = 'unknown'
        backups[key] = {'level': status, 'age_hours': age}
    return {'schema': 1, 'available': True, 'checked_at': checked.timestamp(),
            'disk':level('disk'),
            'containers': {name:level('container:'+name) for name in containers},
            'http': {name:level('http:'+name) for name in http}, 'backups': backups}


def publish(destination, data):
    destination = Path(destination)
    destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=destination.parent, delete=False) as output:
            temporary = Path(output.name)
            os.fchmod(output.fileno(), 0o644)
            json.dump(data, output, separators=(',', ':'), allow_nan=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=Path('/var/lib/homelab-monitor/state.json'))
    parser.add_argument('--config', type=Path, default=Path('/home/pentagon-admin/Documents/homelab/monitoring/config.json'))
    parser.add_argument('--output', type=Path, default=Path('/var/lib/smalltv-dashboard/status.json'))
    args = parser.parse_args()
    try:
        with args.state.open('rb') as source:
            body = source.read(1048577)
        if len(body) > 1048576:
            raise ValueError('Monitoring state exceeds export limit')
        data = summary(json.loads(body), json.loads(args.config.read_text()))
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        data = {'schema':1, 'available':False}
    publish(args.output, data)


if __name__ == '__main__':
    main()
