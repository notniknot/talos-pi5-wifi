#!/usr/bin/env python3
"""Fetch exact upstream sources, apply the port, and stage public firmware."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd=None):
    subprocess.run(args, cwd=cwd, check=True)


def checked(data, digest, label):
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f'SHA256 mismatch: {label}')
    return data


def prepare(root):
    lock = json.loads((root / 'sources.lock.json').read_text())
    for name in ('pkgs', 'talos'):
        repo = root / name
        source = lock[name]
        if not repo.exists():
            repo.mkdir()
            run('git', 'init', '-q', str(repo))
            run('git', 'remote', 'add', 'origin', source['origin'], cwd=repo)
            run('git', 'fetch', '--depth=1', 'origin', source['commit'], cwd=repo)
            run('git', 'checkout', '--detach', 'FETCH_HEAD', cwd=repo)
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
        if head != source['commit']:
            raise SystemExit(f'{repo}: unexpected HEAD; preserve your changes and use a fresh checkout')
        patch = str(root / 'patches' / f'{name}.patch')
        check = subprocess.run(['git', 'apply', '--check', patch], cwd=repo, capture_output=True)
        if check.returncode == 0:
            run('git', 'apply', patch, cwd=repo)
        elif subprocess.run(['git', 'apply', '--reverse', '--check', patch], cwd=repo, capture_output=True).returncode:
            raise SystemExit(f'{repo}: patch does not apply cleanly (no files reset)')
    rootfs = root / 'talos/hack/rpi5-rootfs'
    firmware = rootfs / 'usr/lib/firmware/brcm'
    firmware.mkdir(parents=True, exist_ok=True)
    for item in lock['firmware']:
        dest = firmware / item['name']
        if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest() == item['sha256']:
            continue
        with urllib.request.urlopen(item['url'], timeout=60) as response:
            data = checked(response.read(), item['sha256'], item['url'])
        dest.write_bytes(data)
    shutil.copyfile(firmware / 'brcmfmac43455-sdio.txt', firmware / 'brcmfmac43455-sdio.raspberrypi,5-model-b.txt')
    notices = rootfs / 'usr/share/licenses/rpi5-firmware'
    notices.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / 'licenses/raspberrypi-firmware-copyright', notices / 'COPYRIGHT')
    for name, digest in lock['device_tree']['assets'].items():
        data = checked((root / 'assets/boot' / name).read_bytes(), digest, name)
        target = root / 'talos/hack/rpi5-boot' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    print('Pinned sources, patches, boot assets and Wi-Fi firmware prepared.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT, help='Alternate complete project checkout')
    prepare(parser.parse_args().root.resolve())
