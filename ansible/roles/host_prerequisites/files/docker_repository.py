#!/usr/bin/env python3
"""Inspect Docker apt sources without editing them; refuse ambiguous configurations."""
import argparse
import json
from pathlib import Path
import re
import shlex

SUPPORTED = {'debian': {'bookworm', 'trixie'}, 'ubuntu': {'jammy', 'noble', 'resolute'}}


def entries(text, deb822):
    if not deb822:
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # Split options as one field before tokenizing the repository URI.
            match = re.fullmatch(r'deb\s+(?:\[([^\]]+)\]\s+)?(\S+)\s+(\S+)\s+(.+)', line)
            if match and 'download.docker.com' in match[2]:
                options = dict(option.split('=', 1) for option in shlex.split(match[1] or '') if '=' in option)
                if any(options.get(name, 'no').lower() in ('yes', 'true', '1')
                       for name in ('trusted', 'allow-insecure', 'allow-weak', 'allow-downgrade-to-insecure')):
                    raise ValueError('Docker source disables signature checks; review it before setup.')
                yield {'uri': match[2], 'suites': match[3].split(),
                       'components': shlex.split(match[4].split('#', 1)[0]),
                       'architectures': options.get('arch', '').split(','),
                       'key': options.get('signed-by', '')}
            elif 'download.docker.com' in line and not line.startswith('deb-src '):
                raise ValueError('Unrecognized Docker repository entry; review apt sources.')
        return
    for stanza in re.split(r'\n\s*\n', text):
        fields, current = {}, None
        for line in stanza.splitlines():
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            if line[0].isspace() and current:
                fields[current] += ' ' + line.strip()
            elif ':' in line:
                current, value = line.split(':', 1)
                current = current.lower()
                fields[current] = value.strip()
        if fields.get('enabled', 'yes').lower() == 'no':
            continue
        uris = fields.get('uris', '').split()
        if any('download.docker.com' in uri for uri in uris):
            if any(fields.get(name, 'no').lower() in ('yes', 'true', '1')
                   for name in ('trusted', 'allow-insecure', 'allow-weak', 'allow-downgrade-to-insecure')):
                raise ValueError('Docker source disables signature checks; review it before setup.')
            if fields.get('types', '').split() != ['deb'] or len(uris) != 1:
                raise ValueError('Review Docker repository types and URIs before migration.')
            yield {'uri': uris[0], 'suites': fields.get('suites', '').split(),
                   'components': fields.get('components', '').split(),
                   'architectures': fields.get('architectures', '').split(),
                   'key': fields.get('signed-by', '')}


def inspect(root, distribution, suite, architecture):
    if suite not in SUPPORTED.get(distribution, set()) or architecture not in ('amd64', 'arm64'):
        raise ValueError('Automatic Docker setup supports Debian 12/13 and Ubuntu 22.04/24.04/26.04 on ARM64/AMD64 only.')
    base = Path(root or '/')
    if not base.is_absolute():
        raise ValueError('Apt fixture root must be absolute.')
    sources = base / 'etc/apt/sources.list.d'
    for directory in (base / 'etc/apt', sources, base / 'etc/apt/keyrings'):
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            raise ValueError('Review symlinked or non-directory apt paths before setup.')
    files = [base / 'etc/apt/sources.list']
    files += sorted(path for path in sources.glob('*') if path.suffix in ('.sources', '.list'))
    found = []
    for path in files:
        if not path.exists():
            if path.is_symlink():
                raise ValueError('Review dangling apt source symlinks before setup.')
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError('Review non-regular apt source files before setup.')
        for entry in entries(path.read_text(), path.suffix == '.sources'):
            found.append((path, entry))
    uri = 'https://download.docker.com/linux/' + distribution
    if len(found) > 1:
        raise ValueError('Multiple Docker repository entries exist; review duplicates before setup.')
    result = {'uri': uri, 'suite': suite, 'architecture': architecture,
              'source_path': str(sources / 'docker.sources'),
              'key_path': str(base / 'etc/apt/keyrings/docker.asc'), 'existing': False}
    if found:
        path, entry = found[0]
        if (entry['uri'].rstrip('/') != uri or entry['suites'] != [suite]
                or entry['components'] != ['stable'] or entry['architectures'] != [architecture]):
            raise ValueError('Existing Docker repository differs from this OS/architecture; review it first.')
        key = Path(entry['key'])
        if not key.is_absolute() or key.is_symlink() or not key.is_file():
            raise ValueError('Existing Docker repository needs a regular absolute Signed-By key file.')
        if not key.stat().st_mode & 0o004:
            raise ValueError('Docker public signing key must be readable by apt downloads.')
        result.update(existing=True, source_path=str(path), key_path=str(key))
    elif Path(result['source_path']).exists() or Path(result['source_path']).is_symlink():
        raise ValueError('Refuse to overwrite an existing docker.sources file without an active matching repository.')
    elif Path(result['key_path']).is_symlink():
        raise ValueError('Refuse to replace a symlinked Docker key.')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='')
    parser.add_argument('--distribution', required=True)
    parser.add_argument('--suite', required=True)
    parser.add_argument('--architecture', required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.root, args.distribution, args.suite, args.architecture)))


if __name__ == '__main__':
    main()
