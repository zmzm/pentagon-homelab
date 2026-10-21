#!/usr/bin/env python3
"""Encrypt the existing Matrix password without another plaintext file or rotation."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess


def main():
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=base.parent / 'apps/matrix/.env')
    parser.add_argument('--output', type=Path, default=base / 'vars/matrix.vault.yml')
    parser.add_argument('--vault-password-file', type=Path)
    args = parser.parse_args()

    if args.source.is_symlink() or not args.source.is_file():
        parser.error('Source must be a regular Matrix environment file, not a symlink.')
    lines = [line.strip() for line in args.source.read_text().splitlines()
             if line.strip() and not line.lstrip().startswith('#')]
    if len(lines) != 1 or not lines[0].startswith('MATRIX_POSTGRES_PASSWORD='):
        parser.error('Expected exactly one MATRIX_POSTGRES_PASSWORD assignment.')
    password = lines[0].split('=', 1)[1].strip()
    if len(password) >= 2 and password[0] == password[-1] and password[0] in "\"'":
        password = password[1:-1]
    if (not re.fullmatch(r'[A-Za-z0-9_.~+/=-]+', password)
            or password == 'REPLACE_WITH_EXISTING_PASSWORD'):
        parser.error('The saved password is empty or has an unsupported format.')

    command = ['ansible-vault', 'encrypt', '--output', '-']
    if args.vault_password_file:
        command += ['--vault-password-file', str(args.vault_password_file.resolve())]
    else:
        command += ['--ask-vault-pass']
    environment = dict(os.environ, ANSIBLE_CONFIG=str(base / 'ansible.cfg'))
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb') as destination:
            subprocess.run(command,
                           input=json.dumps({'vault_matrix_postgres_password': password}).encode(),
                           stdout=destination, env=environment, check=True)
        if not args.output.read_bytes().startswith(b'$ANSIBLE_VAULT;'):
            raise RuntimeError('Encryption did not produce an Ansible Vault.')
    except BaseException:
        args.output.unlink(missing_ok=True)
        raise
    print(f'Encrypted Matrix variables saved to {args.output}; source unchanged.')


if __name__ == '__main__':
    main()
