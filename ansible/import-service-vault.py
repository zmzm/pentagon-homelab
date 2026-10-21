#!/usr/bin/env python3
"""Import existing service secrets into Vault; never write another plaintext copy."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import yaml

BASE = Path(__file__).resolve().parent


def values(service):
    if service == 'synapse':
        path = BASE.parent / 'data/matrix/synapse/homeserver.yaml'
        if path.is_symlink() or not path.is_file():
            raise RuntimeError('Synapse source must be a regular configuration file')
        config = yaml.safe_load(path.read_text())
        secret = {key: config[key] for key in ('registration_shared_secret', 'macaroon_secret_key', 'form_secret')}
        password = config['database']['args']['password']
        assert all(isinstance(value, str) and value for value in [*secret.values(), password])
        return {'vault_matrix_synapse_secrets': secret, 'vault_matrix_postgres_password': password}
    command = ['docker', 'compose', '--project-directory', str(BASE.parent / 'apps/pihole-adapter'), 'config', '--format', 'json']
    environment = {key:value for key,value in os.environ.items() if key not in ('PIHOLE_BASE_URL', 'PIHOLE_PASSWORD', 'REQUEST_TIMEOUT', 'SUMMARY_CACHE_TTL')}
    config = json.loads(subprocess.run(command, capture_output=True, text=True, check=True, env=environment).stdout)
    environment = config['services']['pihole-adapter']['environment']
    assert set(environment) == {'PIHOLE_BASE_URL', 'PIHOLE_PASSWORD', 'REQUEST_TIMEOUT', 'SUMMARY_CACHE_TTL'}
    assert all(isinstance(value, str) and value for value in environment.values())
    return {'vault_pihole_adapter_environment': environment}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('service', choices=['synapse', 'pihole-adapter'])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--vault-password-file', type=Path)
    args = parser.parse_args()
    output = args.output or BASE / 'vars' / (args.service + '.vault.yml')
    payload = values(args.service)
    command = ['ansible-vault', 'encrypt', '--output', '-']
    command += ['--vault-password-file', str(args.vault_password_file)] if args.vault_password_file else ['--ask-vault-pass']
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            subprocess.run(command, input=json.dumps(payload).encode(), stdout=stream,
                           env=dict(os.environ, ANSIBLE_CONFIG=str(BASE / 'ansible.cfg')), check=True)
        assert output.read_bytes().startswith(b'$ANSIBLE_VAULT;')
        if os.environ.get('SUDO_UID'):
            os.chown(output, int(os.environ['SUDO_UID']), int(os.environ['SUDO_GID']))
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    print('Encrypted service variables saved; source and runtime passwords unchanged.')


if __name__ == '__main__':
    main()
