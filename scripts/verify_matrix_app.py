#!/usr/bin/env python3
"""Start restored Synapse against a restored dump with loopback-only networking."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

import yaml

from verify_matrix_db import run, verify as verify_database
from recovery_safety import require_private_restore


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(restored, workflows=False):
    restored = require_private_restore(restored)
    data = restored / 'data/matrix/synapse'
    config_path = data / 'homeserver.yaml'
    config = yaml.safe_load(config_path.read_text())
    compose = json.loads(run(['docker', 'compose', '--project-directory',
                              str(restored / 'apps/matrix'), 'config', '--format', 'json'],
                             text=True).stdout)
    password = compose['services']['postgres']['environment']['POSTGRES_PASSWORD']
    if not password or config['database']['args']['password'] != password:
        raise RuntimeError('Restored Matrix environment and database password differ.')
    key = data / Path(config['signing_key_path']).name
    if key.is_symlink() or not key.is_file():
        raise RuntimeError('Missing restored signing key.')
    key_digest = digest(key)
    media_count = sum(1 for path in (data / 'media_store').rglob('*') if path.is_file())
    image = run(['docker', 'inspect', 'matrix-synapse', '--format', '{{.Image}}'], text=True).stdout.strip()
    name = 'synapse-restore-test-' + uuid.uuid4().hex[:12]
    config['database']['args']['host'] = '127.0.0.1'
    config['database']['args']['port'] = 5432
    config['report_stats'] = False
    # Log only inside disposable storage; keep all identity and media data restored.
    config['log_config'] = '/data/restore-test.log.config'
    log_config = data / 'restore-test.log.config'
    log_config.write_text(yaml.safe_dump({
        'version': 1, 'handlers': {'console': {'class': 'logging.StreamHandler'}},
        'root': {'level': 'WARNING', 'handlers': ['console']}}))
    config_path.write_text(yaml.safe_dump(config))
    for path in (config_path, log_config):
        os.chown(path, 991, 991)
        path.chmod(0o600)

    def application_check(database):
        try:
            run(['docker', 'run', '--detach', '--name', name,
                 '--network', 'container:' + database,
                 '--label', 'com.centurylinklabs.watchtower.enable=false',
                 '--memory', '1536m', '--cpus', '1', '--user', '991:991',
                 '--mount', f'type=bind,src={data},dst=/data',
                 '--entrypoint', 'python', image, '-m', 'synapse.app.homeserver',
                 '--config-path', '/data/homeserver.yaml'])
            db_info, app_info = json.loads(run(['docker', 'inspect', database, name], text=True).stdout)
            if (db_info['HostConfig']['NetworkMode'] != 'none'
                    or app_info['HostConfig']['NetworkMode'] != 'container:' + db_info['Id']
                    or db_info['HostConfig']['PortBindings']
                    or app_info['HostConfig']['PortBindings']):
                raise RuntimeError('Recovery containers failed network isolation checks.')
            probe = '''import json, socket, urllib.request
from signedjson.key import read_signing_keys
from unpaddedbase64 import encode_base64
assert {name for _, name in socket.if_nameindex()} == {'lo'}
def get(path):
    with urllib.request.urlopen('http://127.0.0.1:8008' + path, timeout=3) as response:
        return response.read()
assert get('/health').strip() == b'OK'
assert json.loads(get('/_matrix/client/versions'))['versions']
keys = json.loads(get('/_matrix/key/v2/server'))
with open(KEY_PATH) as stream:
    signing = read_signing_keys(stream)[0]
expected = encode_base64(signing.verify_key.encode())
assert keys['verify_keys'][signing.alg + ':' + signing.version]['key'] == expected
assert keys['server_name'] == SERVER_NAME
print(json.dumps({'server_name': keys['server_name'], 'signing_key_matches': True}))
'''
            probe = ('KEY_PATH = ' + repr(config['signing_key_path']) + '\nSERVER_NAME = '
                     + repr(config['server_name']) + '\n' + probe)
            for attempt in range(90):
                result = subprocess.run(['docker', 'exec', name, 'python', '-c', probe],
                                        capture_output=True, text=True, timeout=15)
                if result.returncode == 0:
                    break
                state = json.loads(run(['docker', 'inspect', name], text=True).stdout)[0]['State']
                if not state['Running']:
                    raise RuntimeError('Restored Synapse exited before becoming healthy.')
                time.sleep(1)
            else:
                raise RuntimeError('Restored Synapse did not pass health/API/signing-key checks.')
            if workflows:
                result = run(['docker', 'exec', '-i', '--env', 'HOMELAB_RECOVERY_TEST=1', name, 'python', '-B', '-'],
                             input=(Path(__file__).resolve().parent / 'matrix_recovery_client.py').read_bytes())
                print(result.stdout.decode().strip(), flush=True)
            if digest(key) != key_digest:
                raise RuntimeError('Restored signing key changed during startup.')
            print('PASS: restored Synapse health, client API, server identity and signing key; '
                  f'{media_count} restored media files present; loopback-only network.', flush=True)
        finally:
            # Removal is deliberately checked before the outer restore deletes storage.
            run(['docker', 'rm', '--force', '--volumes', name])
            print('Temporary Synapse container removed.', flush=True)

    return verify_database(restored / 'data/matrix/database-backup/synapse.dump',
                           application_check=application_check, postgres_password=password)
