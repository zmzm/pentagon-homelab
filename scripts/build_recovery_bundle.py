#!/usr/bin/env python3
"""Build a new public-source archive and encrypted, verified latest-snapshot repository."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import uuid

ROOT = Path(__file__).resolve().parents[1]


def private_source_name(path):
    return (path.name in ('inventory.ssh.yml', 'id_rsa', 'id_ed25519', 'known_hosts', 'authorized_keys')
            or path.name.endswith('.vault.yml') or path.name.endswith('.env')
            or (path.name.startswith('.env') and not path.name.endswith('.example'))
            or path.suffix in ('.key', '.pem', '.p12', '.pfx', '.crt', '.csr'))


def source_files(root=ROOT):
    output = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=root)
    files = []
    for raw in output.split(b'\0'):
        if not raw:
            continue
        name = os.fsdecode(raw)
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or path.parts[0] in ('data', 'backups', '.git', '.codex', '.agents'):
            raise RuntimeError('Unsafe source archive member')
        if private_source_name(path):
            raise RuntimeError('Private runtime material appeared in the source file list')
        source = root / path
        if source.is_symlink() or not source.is_file() or source.resolve() != source.absolute():
            raise RuntimeError('Source archives require existing regular files without symlink traversal')
        files.append(name)
    return sorted(files)


def build(output):
    if os.geteuid() != 0:
        raise RuntimeError('Run with sudo to access backup repository credentials')
    output = Path(output).absolute()
    if output.resolve() != output:
        raise RuntimeError('Staging path must not traverse symlinks')
    if output.is_relative_to(ROOT) or ROOT.is_relative_to(output):
        raise RuntimeError('Build recovery bundles outside the backed-up checkout to avoid recursive backups')
    os.umask(0o077)
    # mkdir without exist_ok makes overwriting any prior directory impossible.
    output.mkdir(mode=0o700)
    try:
        files = source_files()
        with tarfile.open(output / 'project.tar', 'w', dereference=True) as archive:
            for name in files:
                archive.add(ROOT / name, arcname=name, recursive=False)
        config = json.loads((ROOT / 'data/backrest/config/config.json').read_text())
        source = next(item for item in config['repos'] if item['id'] == 'home-lab')
        if source['uri'] != '/repos/restic' or source.get('commandPrefix'):
            raise RuntimeError('Review changed source repository settings')
        environment = {key: value for key, value in os.environ.items() if not key.startswith('RESTIC_')}
        environment.update(RESTIC_PASSWORD=source['password'], RESTIC_FROM_PASSWORD=source['password'])
        original = ROOT / 'backups/restic'
        def restic(repository, *arguments):
            return subprocess.run(['restic', '--no-cache', '--repo', str(repository), *arguments],
                                  env=environment, capture_output=True, text=True, check=True)
        snapshots = json.loads(restic(original, 'snapshots', '--json', '--tag', 'plan:pentagon-backup').stdout)
        snapshot = max(snapshots, key=lambda item: item['time'])
        required = snapshot.get('summary', {}).get('total_bytes_processed')
        if not required or shutil.disk_usage(output).free < required + 512 * 1024**2:
            raise RuntimeError('Not enough staging space or snapshot size unavailable')
        repository = output / 'restic'
        restic(repository, 'init')
        restic(repository, 'copy', '--from-repo', str(original), snapshot['id'])
        restic(repository, 'check', '--read-data')
        copied = json.loads(restic(repository, 'snapshots', '--json').stdout)
        if len(copied) != 1 or copied[0]['time'] != snapshot['time']:
            raise RuntimeError('Staged repository does not contain the selected snapshot')
        manifest = {'bundle_id': uuid.uuid4().hex, 'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                    'source_snapshot': snapshot['id'], 'staged_snapshot': copied[0]['id'],
                    'snapshot_time': snapshot['time'], 'files': {}}
        for path in sorted(output.rglob('*')):
            if path.is_file():
                with path.open('rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                manifest['files'][str(path.relative_to(output))] = {'sha256': digest, 'size': path.stat().st_size}
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        if os.environ.get('SUDO_UID'):
            uid, gid = int(os.environ['SUDO_UID']), int(os.environ['SUDO_GID'])
            for path in [output, *output.rglob('*')]:
                os.chown(path, uid, gid)
        print('PASS: source archive excludes private/runtime files; selected encrypted snapshot copied and fully checked.')
        print('Recovery bundle:', output)
        return manifest
    except BaseException:
        shutil.rmtree(output)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='A new directory; existing paths are refused')
    args = parser.parse_args()
    build(args.output)


if __name__ == '__main__':
    main()
