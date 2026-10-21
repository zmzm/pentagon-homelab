"""Exercise a disposable account on isolated recovered Vaultwarden; no real user login."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import socket
import urllib.parse
import urllib.request
import uuid
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def main():
    if os.environ.get('HOMELAB_RECOVERY_TEST') != '1' or {name for _, name in socket.if_nameindex()} != {'lo'}:
        raise RuntimeError('Synthetic writes require an explicitly isolated recovery network')
    base = 'http://127.0.0.1:80'
    encode = lambda data: base64.b64encode(data).decode()
    email, password = 'recovery-' + uuid.uuid4().hex + '@recovery.invalid', secrets.token_bytes(32)
    master = hashlib.pbkdf2_hmac('sha256', password, email.encode(), 600000, 32)
    auth_hash = encode(hashlib.pbkdf2_hmac('sha256', master, password, 1, 32))
    vault_key = secrets.token_bytes(64)
    stretched = b''.join(hmac.new(master, purpose + b'\x01', hashlib.sha256).digest() for purpose in (b'enc', b'mac'))

    def encrypt(plaintext, key=vault_key):
        iv = secrets.token_bytes(16)
        pad = padding.PKCS7(128).padder()
        padded = pad.update(plaintext) + pad.finalize()
        cipher = Cipher(algorithms.AES(key[:32]), modes.CBC(iv)).encryptor()
        ciphertext = cipher.update(padded) + cipher.finalize()
        mac = hmac.new(key[32:], iv + ciphertext, hashlib.sha256).digest()
        return '2.' + '|'.join(map(encode, (iv, ciphertext, mac)))

    def decrypt(value):
        iv, ciphertext, mac = map(base64.b64decode, value.removeprefix('2.').split('|'))
        assert hmac.compare_digest(mac, hmac.new(vault_key[32:], iv + ciphertext, hashlib.sha256).digest())
        cipher = Cipher(algorithms.AES(vault_key[:32]), modes.CBC(iv)).decryptor()
        padded = cipher.update(ciphertext) + cipher.finalize()
        unpad = padding.PKCS7(128).unpadder()
        return unpad.update(padded) + unpad.finalize()

    def request(method, path, payload=None, token=None, form=None):
        headers = {'User-Agent': 'homelab-isolated-recovery', 'device-type': '9'}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode(); headers['Content-Type'] = 'application/json'
        if form is not None:
            data = urllib.parse.urlencode(form).encode(); headers['Content-Type'] = 'application/x-www-form-urlencoded'
        if token:
            headers['Authorization'] = 'Bearer ' + token
        with urllib.request.urlopen(urllib.request.Request(base + path, data=data, headers=headers, method=method), timeout=20) as response:
            result = response.read()
            return json.loads(result) if 'application/json' in response.headers.get('Content-Type', '') else result

    assert request('GET', '/alive')
    assert b'<html' in request('GET', '/').lower()
    request('POST', '/identity/accounts/register', {'email': email, 'masterPasswordHash': auth_hash,
            'key': encrypt(vault_key, stretched), 'kdf': 0, 'kdfIterations': 600000})
    login = request('POST', '/identity/connect/token', form={
        'grant_type': 'password', 'client_id': 'web', 'scope': 'api offline_access',
        'username': email, 'password': auth_hash, 'deviceIdentifier': str(uuid.uuid4()),
        'deviceName': 'isolated-recovery-test', 'deviceType': '9'})
    token = login['access_token']
    assert request('GET', '/api/accounts/profile', token=token)['email'] == email
    plaintext = b'Synthetic recovery secret ' + secrets.token_bytes(32)
    cipher = request('POST', '/api/ciphers', {'type': 1, 'name': encrypt(b'Recovery fixture'),
                     'login': {'username': encrypt(b'test'), 'password': encrypt(plaintext), 'uris': []},
                     'favorite': False, 'reprompt': 0}, token=token)
    retrieved = request('GET', '/api/ciphers/' + cipher['id'], token=token)
    assert decrypt(retrieved['login']['password']) == plaintext
    assert any(value['id'] == cipher['id'] for value in request('GET', '/api/sync', token=token)['ciphers'])
    print('PASS: isolated recovered Vaultwarden UI, disposable-account login and encrypted item write/read/sync.')


if __name__ == '__main__':
    main()
