#!/usr/bin/env python3
"""Create a private, unencrypted alerts room using an existing bot's .env token."""
import argparse
import json
import os
from pathlib import Path
import uuid

from monitor import ROOT, matrix_request, send_matrix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bot-env', type=Path, required=True)
    parser.add_argument('--recipient', required=True)
    parser.add_argument('--bot-user', required=True)
    args = parser.parse_args()
    os.umask(0o077)
    destination = ROOT / 'data/monitoring/matrix.json'
    if destination.exists():
        raise RuntimeError('Credentials already exist; refusing to create another room')
    values = {}
    for line in args.bot_env.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip().strip('\"\'')
    credentials = {'homeserver': 'http://127.0.0.1:8008',
                   'access_token': values['MATRIX_ACCESS_TOKEN']}
    if matrix_request(credentials, 'GET', '/account/whoami')['user_id'] != args.bot_user:
        raise RuntimeError('Token belongs to a different account')
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    room = matrix_request(credentials, 'POST', '/createRoom', {
        'visibility': 'private', 'preset': 'private_chat', 'name': 'Server alerts',
        'topic': 'Homelab health, backup alerts and recovery notifications. No end-to-end encryption.',
        'invite': [args.recipient]})
    credentials['room_id'] = room['room_id']
    # Save immediately so a failed welcome message cannot lose the new room.
    with destination.open('x') as output:
        json.dump(credentials, output, indent=2)
    send_matrix(credentials, {'transaction_id': uuid.uuid4().hex,
        'body': 'Server alerts are configured. Checks run every five minutes for disk space, containers, Matrix, Vaultwarden and backups. Problems and recoveries appear here; ongoing problems repeat every six hours. This private room has no end-to-end encryption.'})
    print('Alerts room created; invitation and welcome message sent to ' + args.recipient)


if __name__ == '__main__':
    main()
