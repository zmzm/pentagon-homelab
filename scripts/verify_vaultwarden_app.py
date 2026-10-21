"""Run recovered Vaultwarden and a synthetic client in a loopback-only network."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import time
import uuid
from recovery_safety import require_private_restore
from verify_matrix_db import run

ROOT = Path(__file__).resolve().parents[1]


def verify(restored):
    restored = require_private_restore(restored)
    data = restored / 'data/vaultwarden/data'
    key = data / 'rsa_key.pem'
    if key.is_symlink() or not key.is_file():
        raise RuntimeError('Missing restored Vaultwarden signing key')
    before = hashlib.sha256(key.read_bytes()).digest()
    with sqlite3.connect(data / 'db.sqlite3') as db:
        assert db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        counts = {table: db.execute('SELECT count(*) FROM ' + table).fetchone()[0] for table in ('users', 'ciphers')}
    settings = data / 'config.json'
    if settings.is_symlink():
        raise RuntimeError('Refuse symlinked restored Vaultwarden configuration')
    if settings.exists():
        config = json.loads(settings.read_text())
        config.update(signups_allowed=True, signups_verify=False, domain='http://localhost',
                      sso_enabled=False, sso_only=False, use_sendmail=False)
        settings.write_text(json.dumps(config))
        settings.chmod(0o600)
    image = run(['docker', 'inspect', 'vaultwarden', '--format', '{{.Image}}'], text=True).stdout.strip()
    client_image = run(['docker', 'inspect', 'matrix-synapse', '--format', '{{.Image}}'], text=True).stdout.strip()
    name = 'vaultwarden-restore-test-' + uuid.uuid4().hex[:12]
    try:
        run(['docker', 'run', '--detach', '--name', name, '--network', 'none',
             '--label', 'com.centurylinklabs.watchtower.enable=false', '--memory', '512m', '--cpus', '1',
             '--mount', f'type=bind,src={data},dst=/data', '--env', 'DOMAIN=http://localhost',
             '--env', 'SIGNUPS_ALLOWED=true', '--env', 'SIGNUPS_VERIFY=false',
             '--env', 'ROCKET_ADDRESS=127.0.0.1', image])
        info = json.loads(run(['docker', 'inspect', name], text=True).stdout)[0]
        assert info['HostConfig']['NetworkMode'] == 'none' and not info['HostConfig']['PortBindings']
        for attempt in range(60):
            health = subprocess.run(['docker', 'exec', name, '/healthcheck.sh'],capture_output=True, timeout=10)
            if health.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError('Recovered Vaultwarden did not become healthy')
        client = run(['docker', 'run', '--rm', '-i', '--network', 'container:' + name,
                      '--label', 'com.centurylinklabs.watchtower.enable=false',
                      '--memory', '256m', '--cpus', '1', '--env', 'HOMELAB_RECOVERY_TEST=1',
                      '--entrypoint', 'python', client_image, '-B', '-'],
                     input=(ROOT / 'scripts/vaultwarden_recovery_client.py').read_bytes())
        print(client.stdout.decode().strip(), flush=True)
        assert hashlib.sha256(key.read_bytes()).digest() == before
        with sqlite3.connect(data / 'db.sqlite3') as db:
            assert db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
            assert db.execute('SELECT count(*) FROM users').fetchone()[0] == counts['users'] + 1
            assert db.execute('SELECT count(*) FROM ciphers').fetchone()[0] == counts['ciphers'] + 1
        print('PASS: restored Vaultwarden schema, original row counts and signing key retained; synthetic data confined to the disposable copy.', flush=True)
    finally:
        run(['docker', 'rm', '--force', '--volumes', name])
        print('Temporary Vaultwarden container removed.', flush=True)
