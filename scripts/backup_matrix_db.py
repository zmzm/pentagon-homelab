#!/usr/bin/env python3
"""Atomically publish a consistent Matrix PostgreSQL dump for Backrest."""
import fcntl
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / 'data/matrix/database-backup'


def main():
    os.umask(0o077)
    DESTINATION.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (DESTINATION / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if shutil.disk_usage(DESTINATION).free < 2 * 1024**3:
            raise RuntimeError('Less than 2 GiB free')
        partial = DESTINATION / 'synapse.dump.partial'
        try:
            with partial.open('wb') as output:
                os.chmod(partial, 0o600)
                subprocess.run(['docker', 'exec', 'matrix-postgres', 'pg_dump',
                    '-U', 'synapse', '-d', 'synapse', '--format=custom',
                    '--lock-wait-timeout=30s'], stdout=output, stderr=subprocess.PIPE,
                    check=True, timeout=240)
                output.flush()
                os.fsync(output.fileno())
            if partial.stat().st_size == 0:
                raise RuntimeError('Empty database dump')
            with partial.open('rb') as archive:
                subprocess.run(['docker', 'exec', '-i', 'matrix-postgres', 'pg_restore', '--list'],
                    stdin=archive, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    check=True, timeout=30)
            partial.replace(DESTINATION / 'synapse.dump')
            descriptor = os.open(DESTINATION, os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            print('PASS: consistent Matrix database dump published; archive index readable.', flush=True)
        finally:
            partial.unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Matrix database backup failed ({type(error).__name__}); inspect service and disk health.', flush=True)
        raise SystemExit(1)
