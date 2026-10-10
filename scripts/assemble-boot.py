#!/usr/bin/env python3
"""Assemble a tryboot directory; never writes a disk or reboots a machine."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def assemble(private=False, diagnostics=False):
    lock = json.loads((ROOT / 'sources.lock.json').read_text())
    sbom = json.loads((ROOT / '_out/kernel-export/kernel.spdx.json').read_text())
    if lock['kernel_version'].removesuffix('-talos') not in {p.get('versionInfo') for p in sbom['packages']}:
        raise ValueError('Kernel artifact does not match the source lock')
    output = ROOT / '_out' / ('private-boot' if private else 'boot')
    if output.exists():
        raise FileExistsError(f'{output} already exists; move it aside before assembling another bundle')
    output.mkdir(mode=0o700 if private else 0o755)
    target = output / 'talos-test'
    target.mkdir()
    shutil.copyfile(ROOT / '_out/kernel-export/Image', target / 'Image')
    source = 'private-initramfs' if private else 'initramfs'
    shutil.copyfile(ROOT / '_out' / source / 'initramfs-arm64.xz', target / 'initramfs-arm64.xz')
    for name, digest in lock['device_tree']['assets'].items():
        data = (ROOT / 'assets/boot' / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f'Boot asset hash mismatch: {name}')
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    cmdline = (ROOT / 'boot/cmdline.txt').read_text().strip()
    if diagnostics:
        cmdline += ' talos.rpi5.diag=1'
    (target / 'cmdline.txt').write_text(cmdline + '\n')
    shutil.copyfile(ROOT / 'boot/tryboot.txt', output / 'tryboot.txt')
    files = sorted(p for p in output.rglob('*') if p.is_file())
    (output / 'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(output)}\n' for p in files))
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private', action='store_true', help='Use the private Wi-Fi initramfs; never publish this bundle')
    parser.add_argument('--diagnostics', action='store_true', help='Save early kernel logs; does not enable an automatic reboot')
    args = parser.parse_args()
    assemble(args.private, args.diagnostics)
