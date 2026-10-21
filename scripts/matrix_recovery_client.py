"""Synthetic Matrix workflow; must run inside an isolated recovery container."""
import hashlib
import hmac
import json
import os
import secrets
import socket
import urllib.parse
import urllib.request
import uuid
import yaml


def main():
    if os.environ.get('HOMELAB_RECOVERY_TEST') != '1' or {name for _, name in socket.if_nameindex()} != {'lo'}:
        raise RuntimeError('Synthetic writes require an explicitly isolated recovery container')
    config = yaml.safe_load(open('/data/homeserver.yaml'))
    base = 'http://127.0.0.1:8008'

    def request(method, path, payload=None, token=None, raw=None):
        headers = {}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            headers['Content-Type'] = 'application/json'
        if raw is not None:
            data = raw
            headers['Content-Type'] = 'application/octet-stream'
        req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=15) as response:
            body = response.read()
            return json.loads(body) if 'application/json' in response.headers.get('Content-Type', '') else body

    def account():
        name, password = 'recovery_' + uuid.uuid4().hex, secrets.token_urlsafe(32)
        nonce = request('GET', '/_synapse/admin/v1/register')['nonce']
        mac = hmac.new(config['registration_shared_secret'].encode(),
                       '\0'.join([nonce, name, password, 'notadmin']).encode(), hashlib.sha1).hexdigest()
        request('POST', '/_synapse/admin/v1/register',
                {'nonce': nonce, 'username': name, 'password': password, 'admin': False, 'mac': mac})
        login = request('POST', '/_matrix/client/v3/login',
                        {'type': 'm.login.password', 'identifier': {'type': 'm.id.user', 'user': name}, 'password': password})
        return login['user_id'], login['access_token']

    first, token = account()
    second, other_token = account()
    room = request('POST', '/_matrix/client/v3/createRoom',
                   {'visibility': 'private', 'preset': 'private_chat', 'invite': [second],
                    'creation_content': {'m.federate': False}}, token)['room_id']
    quote = lambda value: urllib.parse.quote(value, safe='')
    request('POST', '/_matrix/client/v3/join/' + quote(room), {}, other_token)
    message = 'Isolated homelab recovery verification ' + uuid.uuid4().hex
    event = request('PUT', '/_matrix/client/v3/rooms/' + quote(room) + '/send/m.room.message/' + uuid.uuid4().hex,
                    {'msgtype': 'm.text', 'body': message}, token)['event_id']
    received = request('GET', '/_matrix/client/v3/rooms/' + quote(room) + '/event/' + quote(event), token=other_token)
    assert received['content']['body'] == message
    media = b'Isolated recovery media ' + secrets.token_bytes(64)
    uri = request('POST', '/_matrix/media/v3/upload', token=token, raw=media)['content_uri']
    server, media_id = uri.removeprefix('mxc://').split('/', 1)
    assert server == config['server_name']
    assert request('GET', '/_matrix/client/v1/media/download/' + quote(server) + '/' + quote(media_id), token=other_token) == media
    print('PASS: isolated disposable-account Matrix login, local messaging and authenticated media upload/download.')


if __name__ == '__main__':
    main()
