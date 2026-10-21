"""Build managed service configuration without rotating restored identities/secrets."""
import copy
import json
from pathlib import Path, PurePosixPath
import uuid
import yaml

MATRIX_SECRETS = ('registration_shared_secret', 'macaroon_secret_key', 'form_secret')


def matrix_configuration(settings, previous, secrets=None, password=None):
    config = copy.deepcopy(settings)
    for key in ('signing_key_path', 'log_config', 'media_store_path'):
        relative = PurePosixPath(config[key]).relative_to('/data')
        if not relative.parts or '..' in relative.parts:
            raise ValueError('Synapse recovery paths must remain inside restored /data')
    args = config.get('database', {}).get('args', {})
    if (config.get('database', {}).get('name') != 'psycopg2' or
            args != {'user': 'synapse', 'database': 'synapse', 'host': 'postgres', 'port': 5432}):
        raise ValueError('Database backend/connection migration requires a separate operation')
    secrets = secrets or {}
    if previous:
        unknown = set(previous) - set(settings) - set(MATRIX_SECRETS)
        if unknown:
            raise ValueError('Unmanaged Synapse settings must be reviewed before rendering')
        for key in ('server_name', 'signing_key_path'):
            if previous[key] != config[key]:
                raise ValueError('Refuse to change restored Matrix identity or signing-key path')
        if {k: v for k, v in previous['database']['args'].items() if k != 'password'} != args:
            raise ValueError('Refuse to change restored database connection settings')
    for key in MATRIX_SECRETS:
        value = secrets.get(key, (previous or {}).get(key))
        if not isinstance(value, str) or not value:
            raise ValueError('Restore or supply every Synapse secret')
        if previous and previous[key] != value:
            raise ValueError('Synapse secret rotation requires a separate operation')
        config[key] = value
    old_password = ((previous or {}).get('database', {}).get('args', {}).get('password'))
    password = password if password is not None else old_password
    if not isinstance(password, str) or not password or (old_password and password != old_password):
        raise ValueError('Restore matching database credentials; password rotation is not supported')
    config['database']['args']['password'] = password
    return config


def tunnel_configuration(settings, previous, folder):
    paths = list(Path(folder).glob('*.json'))
    if len(paths) != 1 or paths[0].is_symlink() or not paths[0].is_file():
        raise ValueError('Restore exactly one regular named-tunnel credential JSON')
    credentials = json.loads(paths[0].read_text())
    tunnel = str(uuid.UUID(credentials['TunnelID']))
    import base64
    if (not credentials.get('AccountTag') or
            len(base64.b64decode(credentials['TunnelSecret'], validate=True)) != 32):
        raise ValueError('Invalid restored tunnel credentials')
    config = copy.deepcopy(settings)
    config.update(tunnel=tunnel, **{'credentials-file': '/etc/cloudflared/' + paths[0].name})
    if previous:
        if set(previous) - set(config):
            raise ValueError('Unmanaged tunnel settings must be reviewed before rendering')
        if str(previous['tunnel']) != tunnel or previous['credentials-file'] != config['credentials-file']:
            raise ValueError('Refuse to change restored tunnel identity or credentials path')
    rules = config['ingress']
    if rules[-1] != {'service': 'http_status:404'}:
        raise ValueError('A final 404 ingress rule is required')
    return config


def main():
    import sys
    request = json.load(sys.stdin)
    path = Path(request['path'])
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError('Configuration path must be a regular file')
    previous = yaml.safe_load(path.read_text()) if path.exists() else None
    if request['service'] == 'matrix':
        config = matrix_configuration(request['settings'], previous,
                                      request.get('secrets'), request.get('password'))
        for key in ('signing_key_path', 'log_config', 'media_store_path'):
            relative = PurePosixPath(config[key]).relative_to('/data')
            restored = path.parent.joinpath(*relative.parts)
            if restored.is_symlink() or not restored.resolve().is_relative_to(path.parent.resolve()):
                raise ValueError('Restore regular local Synapse recovery paths')
            if key == 'media_store_path':
                if not restored.is_dir():
                    raise ValueError('Restore the Synapse media directory before rendering')
            elif not restored.is_file() or not restored.stat().st_size:
                raise ValueError('Restore Synapse signing/logging files before rendering')
    elif request['service'] == 'cloudflared':
        config = tunnel_configuration(request['settings'], previous, path.parent)
    else:
        raise ValueError('Unsupported managed configuration service')
    print(json.dumps({'yaml': yaml.safe_dump(config, sort_keys=False), 'changed': config != previous}))


if __name__ == '__main__':
    main()
