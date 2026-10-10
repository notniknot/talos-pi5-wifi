#!/usr/bin/env python3
"""Build the pinned port. Public outputs never embed a machine configuration."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / 'sources.lock.json').read_text())


def validate_version(version):
    if not re.fullmatch(re.escape(LOCK['upstream_version']) + r'-pi5\.[1-9][0-9]*', version):
        raise ValueError(f"Expected {LOCK['upstream_version']}-pi5.N (N >= 1)")
    return version


def run(args, cwd):
    subprocess.run([str(x) for x in args], cwd=cwd, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', choices=['kernel', 'wpa-supplicant', 'wireless-regdb', 'proto', 'generated', 'wifi-tests', 'boot-tests', 'image-tests', 'machined', 'initramfs', 'installer', 'talosctl-linux-arm64', 'talosctl-darwin-arm64', 'kernel-export', 'private-initramfs'])
    parser.add_argument('--version', default=LOCK['default_version'])
    parser.add_argument('--wifi-config', type=Path)
    args = parser.parse_args()
    version = validate_version(args.version)
    if args.wifi_config and args.target != 'private-initramfs':
        parser.error('--wifi-config is accepted only by private-initramfs')
    out = ROOT / '_out' / args.target
    out.mkdir(parents=True, exist_ok=True)
    buildx = shlex.split(os.environ.get('BUILDX', 'docker buildx'))
    if os.environ.get('BUILDER'):
        buildx += ['--builder', os.environ['BUILDER']]
    buildx += ['build']
    prefix = os.environ.get('PACKAGE_PREFIX', 'localhost:5000/talos-pi5-wifi')
    package_tag = os.environ.get('PACKAGE_TAG', version)
    image = lambda name: f'{prefix}/{name}:{package_tag}'
    epoch = subprocess.check_output(['git', 'show', '-s', '--format=%ct', LOCK['talos']['commit']], cwd=ROOT / 'talos', text=True).strip()
    if args.target in ['kernel', 'wpa-supplicant', 'wireless-regdb']:
        run(buildx + ['--file', 'Pkgfile', '--platform', 'linux/arm64', '--target', args.target, '--provenance=false', '--sbom=false', '--progress=plain', '--build-arg', f'SOURCE_DATE_EPOCH={epoch}', '--build-arg', 'GNU_MIRROR_URL=https://mirrors.kernel.org', '--tag', image(args.target), '--push', '.'], ROOT / 'pkgs')
        return
    if args.target == 'kernel-export':
        run(buildx + ['--platform', 'linux/arm64', '-f', 'boot/export-kernel.Dockerfile', '--build-arg', 'KERNEL_IMAGE=' + image('kernel'), '--output', f'type=local,dest={out}', '.'], ROOT)
        return
    target = {'proto': 'rpi5-proto', 'generated': 'rpi5-generated', 'wifi-tests': 'rpi5-wifi-tests', 'boot-tests': 'rpi5-boot-tests', 'image-tests': 'rpi5-image-tests', 'installer': 'rpi5-installer', 'private-initramfs': 'initramfs'}.get(args.target, args.target)
    extras = ['--build-arg', 'PKG_RPI5_WPA=' + image('wpa-supplicant'), '--build-arg', 'PKG_RPI5_REGDB=' + image('wireless-regdb')]
    if args.target == 'private-initramfs':
        if args.wifi_config is None:
            parser.error('private-initramfs requires --wifi-config; its output must never be published')
        config = args.wifi_config.resolve()
        data = config.read_bytes()
        out.chmod(0o700)
        extras += ['--secret', f'id=wifi_config,src={config}', '--build-arg', 'RPI5_EMBED_CONFIG=true', '--build-arg', 'RPI5_CONFIG_REVISION=' + hashlib.sha256(data).hexdigest()]
    else:
        if args.wifi_config:
            parser.error('--wifi-config is accepted only by private-initramfs')
        extras += ['--build-arg', 'RPI5_EMBED_CONFIG=false']
    if args.target == 'installer':
        extras += ['--output', f'type=oci,dest={out}/installer-arm64.oci.tar', '--provenance=false', '--sbom=false']
    elif not args.target.endswith('-tests'):
        extras += ['--output', f'type=local,dest={out}']
    make = os.environ.get('MAKE') or shutil.which('gmake') or shutil.which('make')
    if not make:
        raise SystemExit('GNU make is required')
    run([make, f'target-{target}', 'PLATFORM=linux/arm64', 'ARCH=arm64', 'INSTALLER_ARCH=arm64', 'BUILD=' + shlex.join(buildx), f'TAG={version}', f'ABBREV_TAG={version}', 'PKG_KERNEL=' + image('kernel'), 'PROGRESS=plain', 'TARGET_ARGS=' + shlex.join(extras)], ROOT / 'talos')


if __name__ == '__main__':
    main()
