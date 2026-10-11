#!/usr/bin/env python3
"""Copy local Backrest snapshots to the identified USB drive without pruning.

sudo python3 scripts/backup_usb.py --initialize --verify  # first use
sudo python3 scripts/backup_usb.py                       # subsequent copies
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
USB_UUID = 'E31C-6360'


def usb_repository():
    result = subprocess.run(['lsblk', '--json', '--output', 'UUID,FSTYPE,MOUNTPOINTS'],
                            check=True, capture_output=True, text=True)
    def devices(nodes):
        for node in nodes:
            yield node
            yield from devices(node.get('children', []))
    matches = [n for n in devices(json.loads(result.stdout)['blockdevices'])
               if n.get('uuid') == USB_UUID]
    if len(matches) != 1:
        raise RuntimeError('Expected USB drive is absent or its UUID is ambiguous.')
    device = matches[0]
    mounts = [Path(p) for p in device.get('mountpoints', []) if p]
    if len(mounts) != 1 or not mounts[0].is_mount():
        raise RuntimeError('Expected USB drive must be mounted before copying.')
    if device.get('fstype') != 'exfat':
        raise RuntimeError('USB filesystem changed; review the destination first.')
    folder = mounts[0] / 'homelab-backups'
    destination = folder / 'restic'
    if folder.is_symlink() or destination.is_symlink():
        raise RuntimeError('Refusing symlinked backup destination.')
    return destination


def local_credentials():
    if os.geteuid() != 0:
        raise SystemExit('Run with sudo to read the existing Backrest password.')
    config = json.loads((ROOT / 'data/backrest/config/config.json').read_text())
    repo = next(r for r in config['repos'] if r['id'] == 'home-lab')
    if repo['uri'] != '/repos/restic' or repo.get('commandPrefix'):
        raise RuntimeError('Local repository configuration changed; review before copying.')
    env = {k: v for k, v in os.environ.items() if not k.startswith('RESTIC_')}
    env['RESTIC_PASSWORD'] = repo['password']
    env['RESTIC_FROM_PASSWORD'] = repo['password']
    return ROOT / 'backups/restic', env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--initialize', action='store_true')
    parser.add_argument('--verify', action='store_true', help='Read and check all USB repository data')
    args = parser.parse_args()
    source, env = local_credentials()
    destination = usb_repository()
    print('USB repository:', destination, flush=True)
    command = ['restic', '--no-cache', '--repo', str(destination)]
    def restic(*options, capture=False):
        return subprocess.run(command + list(options), env=env, check=True,
                              capture_output=capture, text=True)
    if not (destination / 'config').is_file():
        if not args.initialize:
            raise RuntimeError('USB repository missing; initialization must be explicit.')
        if destination.exists() and any(destination.iterdir()):
            raise RuntimeError('Refusing to initialize a nonempty folder.')
        destination.mkdir(parents=True, exist_ok=True)
        restic('init', '--from-repo', str(source), '--copy-chunker-params')
    # A conservative free-space check; restic deduplicates already copied data.
    largest_pack = max((p.stat().st_size for p in (source / 'data').rglob('*')
                        if p.is_file()), default=0)
    if shutil.disk_usage(destination).free < max(largest_pack * 2, 512 * 1024 * 1024):
        raise RuntimeError('Less than the minimum safe free space remains on USB.')
    restic('copy', '--from-repo', str(source))
    if args.verify:
        restic('check', '--read-data')
    snapshots = json.loads(restic('snapshots', '--json', capture=True).stdout)
    print('USB snapshots:', len(snapshots), flush=True)
    for snapshot in sorted(snapshots, key=lambda s: s['time']):
        print(snapshot['short_id'], snapshot['time'], flush=True)
    subprocess.run(['sync', '-f', str(destination)], check=True)
    print('Copy finished and filesystem flushed. No snapshots pruned.', flush=True)


if __name__ == '__main__':
    main()
