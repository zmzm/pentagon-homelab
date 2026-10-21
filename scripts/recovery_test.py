#!/usr/bin/env python3
"""Run the isolated recovery test and publish a private, atomic health result."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
STATE = Path('/var/lib/homelab-recovery')


def save_status(directory, status):
    temporary = directory / 'status.json.partial'
    with temporary.open('w') as stream:
        json.dump(status, stream)
        stream.write('\n')
    temporary.chmod(0o600)
    temporary.replace(directory / 'status.json')


def run_verifier():
    specification = importlib.util.spec_from_file_location('verify_backup', ROOT / 'scripts/verify-backup.py')
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    module.main(['--matrix-workflows', '--vaultwarden-app'])


def interrupted(signum, frame):
    # Raising allows the verifier's finally blocks to remove Docker resources.
    raise InterruptedError('Recovery verification interrupted')


def verify_and_record(directory, verifier=run_verifier):
    try:
        previous = json.loads((directory / 'status.json').read_text())
    except (FileNotFoundError, ValueError):
        previous = {}
    status = {'status': 'running', 'started_at': time.time(),
              'last_success_at': previous.get('last_success_at')}
    save_status(directory, status)
    success = False
    try:
        verifier()
        success = True
    except BaseException as error:
        # Exception messages/command output may contain restored secrets.
        status['error_type'] = type(error).__name__
    finally:
        status['completed_at'] = time.time()
        status['status'] = 'success' if success else 'failed'
        if success:
            status['last_success_at'] = status['completed_at']
        save_status(directory, status)
    return success


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run with sudo.')
    os.umask(0o077)
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE / 'verify.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('A scheduled recovery verification is already running.', flush=True)
            return 1
        signal.signal(signal.SIGTERM, interrupted)
        # Redirect file descriptors too: Restic inherits stdout/stderr directly.
        # Keep only one private log; routine success produces no chat notification.
        sys.stdout.flush()
        sys.stderr.flush()
        stdout, stderr = os.dup(1), os.dup(2)
        try:
            with (STATE / 'latest.log').open('w') as log:
                os.dup2(log.fileno(), 1)
                os.dup2(log.fileno(), 2)
                success = verify_and_record(STATE)
                sys.stdout.flush()
                sys.stderr.flush()
        finally:
            os.dup2(stdout, 1)
            os.dup2(stderr, 2)
            os.close(stdout)
            os.close(stderr)
        print('Recovery verification ' + ('passed.' if success else 'failed; inspect the private recovery log.'), flush=True)
        return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
