#!/usr/bin/env python3
"""Encrypt the existing Portainer key without writing another plaintext copy."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess


def main():
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=base.parent / 'apps/portainer/.env')
    parser.add_argument('--output', type=Path, default=base / 'vars/portainer.vault.yml')
    parser.add_argument('--vault-password-file', type=Path)
    args = parser.parse_args()

    lines = [line.strip() for line in args.source.read_text().splitlines()
             if line.strip() and not line.lstrip().startswith('#')]
    if len(lines) != 1 or not lines[0].startswith('PORTAINER_HOMEPAGE_WIDGET_KEY='):
        parser.error('Expected exactly one PORTAINER_HOMEPAGE_WIDGET_KEY assignment.')
    key = lines[0].split('=', 1)[1].strip()
    if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
        key = key[1:-1]
    if not re.fullmatch(r'[A-Za-z0-9_.~+/=-]+', key) or key == 'REPLACE_WITH_EXISTING_KEY':
        parser.error('The existing widget key is empty or has an unsupported format.')

    command = ['ansible-vault', 'encrypt', '--output', '-']
    if args.vault_password_file:
        command += ['--vault-password-file', str(args.vault_password_file.resolve())]
    else:
        command += ['--ask-vault-pass']
    environment = dict(os.environ, ANSIBLE_CONFIG=str(base / 'ansible.cfg'))
    # Exclusive creation prevents overwriting an existing Vault, including symlinks.
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb') as destination:
            subprocess.run(
                command,
                input=json.dumps({'vault_portainer_homepage_widget_key': key}).encode(),
                stdout=destination,
                env=environment,
                check=True,
            )
        if not args.output.read_bytes().startswith(b'$ANSIBLE_VAULT;'):
            raise RuntimeError('The encryption command did not produce an Ansible Vault.')
    except BaseException:
        args.output.unlink(missing_ok=True)
        raise
    print(f'Encrypted Portainer variables saved to {args.output}; source unchanged.')


if __name__ == '__main__':
    main()
