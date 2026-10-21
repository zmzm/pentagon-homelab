#!/usr/bin/env python3
"""Restore a Matrix dump into an isolated temporary PostgreSQL container."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def run(command, **kwargs):
    return subprocess.run(command, check=True, timeout=180, capture_output=True, **kwargs)


def verify(dump, application_check=None, postgres_password=None):
    image = run(['docker', 'inspect', 'matrix-postgres', '--format', '{{.Image}}'], text=True).stdout.strip()
    name = 'matrix-restore-test-' + uuid.uuid4().hex[:12]
    created = False
    try:
        authentication = ['--env', 'POSTGRES_HOST_AUTH_METHOD=trust']
        environment = os.environ.copy()
        if postgres_password is not None:
            authentication = ['--env', 'POSTGRES_PASSWORD']
            environment['POSTGRES_PASSWORD'] = postgres_password
        run(['docker', 'run', '--detach', '--name', name, '--network', 'none',
             '--label', 'com.centurylinklabs.watchtower.enable=false',
             '--memory', '768m', '--cpus', '1',
             '--tmpfs', '/var/lib/postgresql/data:rw,size=512m',
             '--env', 'POSTGRES_USER=synapse', '--env', 'POSTGRES_DB=synapse',
             '--env', 'POSTGRES_INITDB_ARGS=--locale=C --encoding=UTF8',
             *authentication, image], env=environment)
        created = True
        for attempt in range(60):
            ready = subprocess.run(['docker', 'exec', name, 'pg_isready', '-U', 'synapse', '-d', 'synapse'],
                                   capture_output=True, timeout=10)
            process = subprocess.run(['docker', 'exec', name, 'cat', '/proc/1/comm'],
                                     capture_output=True, text=True, timeout=10)
            if ready.returncode == 0 and process.stdout.strip() == 'postgres':
                break
            time.sleep(1)
        else:
            raise RuntimeError('Temporary database did not become ready')
        with dump.open('rb') as archive:
            run(['docker', 'exec', '-i', name, 'pg_restore', '-U', 'synapse', '-d', 'synapse',
                 '--single-transaction', '--no-owner', '--no-privileges'], stdin=archive)
        sql = """SELECT json_build_object(
            'tables', (SELECT count(*) FROM pg_tables WHERE schemaname='public'),
            'users', (SELECT count(*) FROM users),
            'rooms', (SELECT count(*) FROM rooms),
            'events', (SELECT count(*) FROM events),
            'schema_version', (SELECT version FROM schema_version LIMIT 1));"""
        stats = json.loads(run(['docker', 'exec', name, 'psql', '-U', 'synapse', '-d', 'synapse',
                               '-v', 'ON_ERROR_STOP=1', '-Atc', sql], text=True).stdout)
        if stats['tables'] < 100 or min(stats['users'], stats['rooms'], stats['events']) < 1:
            raise RuntimeError('Restored database is missing expected Matrix data')
        print('PASS: isolated PostgreSQL restore and Matrix data checks: ' + json.dumps(stats), flush=True)
        if application_check is not None:
            application_check(name)
        return stats
    finally:
        if created:
            run(['docker', 'rm', '--force', '--volumes', name])
            print('Temporary database container and storage removed.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dump', type=Path, default=ROOT / 'data/matrix/database-backup/synapse.dump')
    args = parser.parse_args()
    if not args.dump.is_file() or args.dump.stat().st_size == 0:
        raise RuntimeError('Missing or empty dump')
    verify(args.dump)


if __name__ == '__main__':
    main()
