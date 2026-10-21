#!/usr/bin/env python3
"""Restore the newest Backrest snapshot into private temporary storage and verify it.

Run from any directory with sudo. Credentials stay in the child process environment.
Optional Matrix checks test database recovery or isolated Synapse startup.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    if os.geteuid() != 0:
        raise SystemExit('Run with sudo to read Backrest credentials and restore ownership.')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--usb', action='store_true', help='Test the identified USB repository')
    parser.add_argument('--matrix-db', action='store_true', help='Also restore the saved PostgreSQL dump into an isolated container')
    parser.add_argument('--matrix-app', action='store_true', help='Also start restored Synapse with no external network or published ports')
    parser.add_argument('--matrix-workflows', action='store_true', help='Also test disposable-account login, messaging and media in isolated restored Synapse')
    parser.add_argument('--vaultwarden-app', action='store_true', help='Also start isolated restored Vaultwarden and test a synthetic account and encrypted item')
    args = parser.parse_args(argv)
    config = json.loads((ROOT / 'data/backrest/config/config.json').read_text())
    repo = next(r for r in config['repos'] if r['id'] == 'home-lab')
    if repo['uri'] != '/repos/restic' or repo.get('commandPrefix'):
        raise SystemExit('Repository settings changed; review this script before running.')
    env = {k: v for k, v in os.environ.items() if not k.startswith('RESTIC_')}
    env['RESTIC_PASSWORD'] = repo['password']
    repository = ROOT / 'backups/restic'
    if args.usb:
        from backup_usb import usb_repository
        repository = usb_repository()
    print('Testing repository:', repository, flush=True)
    command = ['restic', '--no-cache', '--repo', str(repository)]

    def restic(*args, capture=False):
        return subprocess.run(command + list(args), env=env, check=True,
                              text=True, capture_output=capture)

    snapshots = json.loads(restic('snapshots', '--json', '--tag', 'plan:pentagon-backup',
                                 capture=True).stdout)
    snapshot = max(snapshots, key=lambda s: s['time'])
    size = snapshot.get('summary', {}).get('total_bytes_processed')
    if not size or shutil.disk_usage('/tmp').free < size + 512 * 1024 * 1024:
        raise SystemExit('Insufficient temporary space or snapshot size unavailable.')
    print('Snapshot:', snapshot['short_id'], snapshot['time'], flush=True)
    # TemporaryDirectory is mode 0700. Restored secrets remain private and are deleted
    # on success or failure; the production data directory is never a restore target.
    with tempfile.TemporaryDirectory(prefix='homelab-restore-', dir='/tmp') as target:
        restic('restore', snapshot['id'], '--target', target, '--verify')
        restored = Path(target) / 'userdata/homelab'
        required = [
            'apps/matrix/docker-compose.yml', 'apps/matrix/.env',
            'data/matrix/synapse/homeserver.yaml',
            'data/matrix/synapse/pentagonlab.org.signing.key',
            'data/matrix/postgres/PG_VERSION',
            'data/vaultwarden/data/db.sqlite3',
            'data/cloudflared/config.yml', 'data/backrest/config/config.json',
        ]
        for name in required:
            path = restored / name
            if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
                raise RuntimeError('Missing, empty, or symlinked recovery file: ' + name)
        backup_config = json.loads((restored / 'data/backrest/config/config.json').read_text())
        if not any(r.get('password') for r in backup_config.get('repos', [])):
            raise RuntimeError('Restored Backrest config has no repository password.')
        credentials = list((restored / 'data/cloudflared').glob('*.json'))
        if not credentials:
            raise RuntimeError('Missing restored Cloudflare Tunnel credentials.')
        db = restored / 'data/vaultwarden/data/db.sqlite3'
        # Writable connection permits recovery from the restored WAL; only temporary
        # restored files can be modified. No production DB is opened.
        with sqlite3.connect(db) as connection:
            result = connection.execute('PRAGMA integrity_check').fetchall()
            if result != [('ok',)]:
                raise RuntimeError('Restored Vaultwarden database failed integrity check.')
        print('PASS: full restore verified; required recovery files present; '
              'Vaultwarden SQLite integrity OK.', flush=True)
        if args.vaultwarden_app:
            from verify_vaultwarden_app import verify
            verify(restored)
        if args.matrix_app or args.matrix_workflows:
            from verify_matrix_app import verify
            verify(restored, workflows=args.matrix_workflows)
            print('LIMIT: replacement-host provisioning, real-user encrypted content and external backup recovery are not tested.', flush=True)
        elif args.matrix_db:
            from verify_matrix_db import verify
            verify(restored / 'data/matrix/database-backup/synapse.dump')
            print('LIMIT: full Synapse application startup and external backup recovery are not tested.', flush=True)
        else:
            print('LIMIT: PostgreSQL startup and full application recovery are not tested. '
                  'Use --matrix-db to also test the database dump.', flush=True)
    print('Temporary restored data removed.', flush=True)


if __name__ == '__main__':
    main()
