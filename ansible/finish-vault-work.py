#!/usr/bin/env python3
"""Finish local secret imports and verify Portainer repeatability with one local unlock."""
import getpass
import json
import os
from pathlib import Path
import subprocess
import tempfile
import datetime

BASE = Path(__file__).resolve().parent


def run(command, **kwargs):
    return subprocess.run(command, cwd=BASE, capture_output=True, text=True,
                          env=dict(os.environ, ANSIBLE_CONFIG=str(BASE / 'ansible.cfg')), **kwargs)


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run with sudo so Synapse secrets can be read privately.')
    os.umask(0o077)
    password = getpass.getpass('Existing Portainer Vault password (local only): ')
    if not password:
        raise SystemExit('An empty unlock password is not accepted.')
    results = {}
    with tempfile.TemporaryDirectory(prefix='homelab-vault-finish-', dir='/tmp') as temporary:
        unlock = Path(temporary) / 'unlock'
        unlock.write_text(password + '\n')
        unlock.chmod(0o600)
        password = None
        check = run(['ansible-vault', 'view', 'vars/portainer.vault.yml', '--vault-password-file', str(unlock)])
        if check.returncode:
            raise SystemExit('Could not unlock the existing Portainer Vault; no new Vault files were created.')
        check = None  # The decrypted content is never written or printed.
        for service in ('synapse', 'pihole-adapter'):
            path = BASE / 'vars' / (service + '.vault.yml')
            if not path.exists():
                result = run(['python3', '-B', 'import-service-vault.py', service, '--vault-password-file', str(unlock)])
                if result.returncode:
                    raise SystemExit('Encrypted import failed for ' + service + '; existing Vault files were preserved.')
            elif path.is_symlink():
                raise SystemExit('Refuse to use a symlinked service Vault.')
            check = run(['ansible-vault', 'view', str(path), '--vault-password-file', str(unlock)])
            if check.returncode:
                raise SystemExit('Could not unlock ' + service + ' Vault; existing files were preserved.')
            check = None
        for playbook, vault in [('matrix-config.yml', 'synapse'), ('pihole-adapter.yml', 'pihole-adapter'), ('portainer.yml', 'portainer')]:
            recaps = []
            for attempt in range(2):
                result = run(['ansible-playbook', '-i', str(BASE / 'inventory.ini'), playbook, '-e', '@vars/' + vault + '.vault.yml', '--vault-password-file', str(unlock)])
                if result.returncode:
                    log = BASE.parent / 'data/monitoring/vault-finish.log'
                    log.write_text(result.stdout + result.stderr)
                    log.chmod(0o600)
                    raise SystemExit('Deployment failed; inspect the private data/monitoring/vault-finish.log. Unlock file will be removed.')
                recap = next(line for line in reversed(result.stdout.splitlines()) if line.startswith('pentagon ') and 'failed=' in line)
                if attempt == 1 and 'changed=0 ' not in recap:
                    raise SystemExit('Repeatability check reported changes for ' + playbook + '; review before proceeding.')
                print(playbook + ': ' + recap, flush=True)
                recaps.append(recap)
            results[playbook] = recaps
    report = BASE.parent / 'data/monitoring/vault-finish.json'
    report.write_text(json.dumps({'status': 'success', 'completed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'results': results}, indent=2) + '\n')
    report.chmod(0o600)
    print('PASS: encrypted service imports and Portainer repeat verified; temporary unlock file removed.')


if __name__ == '__main__':
    main()
