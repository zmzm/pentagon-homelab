#!/usr/bin/env python3
"""Send a labeled synthetic Telegram alert using isolated state (explicit live action)."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import time

import monitor
from monitor import telegram_notifications
from monitor_telegram import resolve_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True, help='Staged monitoring configuration')
    parser.add_argument('--state-dir', type=Path, required=True, help='Private isolated test directory')
    parser.add_argument('--phase', choices=('problem', 'recovery'), required=True)
    args = parser.parse_args()
    # Keep the synthetic check/reminder history away from the production queue.
    path = args.state_dir.resolve()
    if path == Path('/var/lib/homelab-monitor') or not path.name.startswith('telegram-test-'):
        raise ValueError('Use an isolated telegram-test-* state directory')
    config = json.loads(args.config.read_text())
    notification = resolve_config(config['notification']['telegram'], monitor.ROOT)
    if not notification['enabled']:
        raise ValueError('Enable Telegram in the staged configuration first')
    os.umask(0o077)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    level = 'critical' if args.phase == 'problem' else 'ok'
    with (path / 'monitor.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.phase == 'recovery' and not (path / 'telegram.json').exists():
            raise ValueError('Run the problem phase with this state directory first')
        return telegram_notifications(config, {'delivery-test': {'level': level, 'message': 'Synthetic test'}},
                                      path, time.time())


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f'Telegram test failed ({type(error).__name__}); inspect retained private test state', flush=True)
        raise SystemExit(1)
