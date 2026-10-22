#!/usr/bin/env python3
"""Create the private Hermes room using the existing local monitoring bot."""
import json
import os
import urllib.parse

from monitor import ROOT, matrix_request


def main():
    os.umask(0o077)
    recipient = '@vladjik:pentagonlab.org'
    destination = ROOT / 'data/hermes-room.json'
    credentials = json.loads((ROOT / 'data/monitoring/matrix.json').read_text())
    if credentials['homeserver'].rstrip('/') != 'http://127.0.0.1:8008':
        raise RuntimeError('Expected the local Synapse endpoint')
    creator = matrix_request(credentials, 'GET', '/account/whoami')['user_id']
    if creator != '@homelab:pentagonlab.org':
        raise RuntimeError('Expected the existing homelab bot')
    if destination.exists():
        record = json.loads(destination.read_text())
        if record['creator'] != creator or record['recipient'] != recipient:
            raise RuntimeError('Existing room record does not match this setup')
    else:
        room = matrix_request(credentials, 'POST', '/createRoom', {
            'visibility': 'private',
            'preset': 'private_chat',
            'name': 'Hermes',
            'topic': 'Personal agent conversations and PoC testing. No end-to-end encryption. Hermes is not connected yet.',
            'invite': [recipient],
            'creation_content': {'m.federate': False},
        })
        record = {'room_id': room['room_id'], 'creator': creator, 'recipient': recipient}
        # Save immediately after creation; never persist the monitoring credential here.
        with destination.open('x') as output:
            json.dump(record, output, indent=2)
            output.write('\n')
    room_id = urllib.parse.quote(record['room_id'], safe='')
    user_id = urllib.parse.quote(recipient, safe='')
    membership = matrix_request(credentials, 'GET', f'/rooms/{room_id}/state/m.room.member/{user_id}')['membership']
    if membership not in ('invite', 'join'):
        raise RuntimeError('Recipient is neither invited nor joined; manual review required')
    print(json.dumps({**record, 'membership': membership}))


if __name__ == '__main__':
    main()
