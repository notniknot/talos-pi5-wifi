"""Check the public/private boundary and pinned release identity without a builder."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import runpy
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BuildInputs(unittest.TestCase):
    def test_hang_fixture_preserves_header_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            kernel = root / 'Image'
            original = bytearray(128)
            original[56:60] = b'ARM\x64'
            struct.pack_into('<Q', original, 8, 0x80000)
            kernel.write_bytes(original)
            output = root / 'fixture'
            fixture = load('make-hang-fixture')
            fixture.make_fixture(kernel, output)
            data = (output / 'hang-Image').read_bytes()
            self.assertEqual(len(data), len(original))
            self.assertEqual(struct.unpack_from('<I', data, 4)[0], 0x14000000)
            self.assertEqual(data[:4], original[:4])
            self.assertEqual(data[8:], original[8:])
            self.assertEqual(kernel.read_bytes(), original)
            with self.assertRaises(FileExistsError):
                fixture.make_fixture(kernel, output)
            self.assertEqual((output / 'hang-Image').read_bytes(), data)
            kernel.write_bytes(b'not an ARM64 Image')
            with self.assertRaises(ValueError):
                fixture.make_fixture(kernel, root / 'invalid')
            self.assertFalse((root / 'invalid').exists())

    def test_versions_keep_upstream_identity(self):
        build = load('build')
        for upstream in [build.LOCK['upstream_version'], 'v99.98.97']:
            with self.subTest(upstream=upstream), patch.dict(build.LOCK, upstream_version=upstream):
                valid = f'{upstream}-pi5.1'
                self.assertEqual(build.validate_version(valid), valid)
                major, minor, micro = upstream.removeprefix('v').split('.')
                other_upstream = f'v{int(major) + 1}.{minor}.{micro}'
                for version in [upstream, f'{other_upstream}-pi5.1',
                                f'{upstream}-pi5.0', valid + ';id', valid + '\n']:
                    with self.subTest(version=version), self.assertRaises(ValueError):
                        build.validate_version(version)

    def test_release_packaging_preserves_modes_and_checksums(self):
        with patch('sys.path', [str(ROOT / 'scripts'), *sys.path]):
            release = load('release')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            release.ROOT = root
            artifacts = {
                'installer/installer-arm64.oci.tar': (b'public installer', 0o644),
                'talosctl-linux-arm64/talosctl-linux-arm64': (b'linux client', 0o755),
                'talosctl-darwin-arm64/talosctl-darwin-arm64': (b'macos client', 0o755),
                'kernel-export/kernel.spdx.json': (b'{}', 0o644),
                'private-initramfs/initramfs-arm64.xz': (b'PRIVATE SECRET', 0o600),
            }
            for name, (data, mode) in artifacts.items():
                source = root / '_out' / name
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_bytes(data)
                source.chmod(mode)

            def fake_build(command, **kwargs):
                if str(root / 'scripts/assemble-boot.py') in command:
                    boot = root / '_out/boot'
                    boot.mkdir()
                    (boot / 'tryboot.txt').write_text('public boot config\n')

            # Exercise real packaging; only expensive builds and Git queries are stubbed.
            with patch('sys.argv', ['release.py']), \
                 patch.object(release, 'validate_example'), \
                 patch.object(release.subprocess, 'run', side_effect=fake_build), \
                 patch.object(release.subprocess, 'check_output', side_effect=['test-commit', b'']):
                release.main()

            version = release.LOCK['default_version']
            output = root / '_out/releases' / version
            for client in ['talosctl-linux-arm64', 'talosctl-darwin-arm64']:
                self.assertEqual((output / client).stat().st_mode & 0o777, 0o755)
                self.assertEqual((output / client).read_bytes(), artifacts[f'{client}/{client}'][0])
            installer = output / f'talos-pi5-wifi-{version}-arm64-installer.oci.tar'
            self.assertEqual(installer.stat().st_mode & 0o777, 0o644)
            listed = set()
            for line in (output / 'SHA256SUMS').read_text().splitlines():
                digest, name = line.split('  ', 1)
                listed.add(name)
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), digest)
                self.assertNotIn(b'PRIVATE SECRET', (output / name).read_bytes())
            self.assertEqual(listed, {p.name for p in output.iterdir()} - {'SHA256SUMS'})
            self.assertFalse((output / 'private-initramfs').exists())

    def test_boot_assets_match_lock(self):
        lock = json.loads((ROOT / 'sources.lock.json').read_text())
        for name, digest in lock['device_tree']['assets'].items():
            self.assertEqual(hashlib.sha256((ROOT / 'assets/boot' / name).read_bytes()).hexdigest(), digest)

    def test_checksum_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            load('prepare').checked(b'changed', hashlib.sha256(b'original').hexdigest(), 'firmware')

    def test_wifi_generator_private_file_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'maintenance.yaml'
            argv = ['wifi-config.py', '--output', str(output)]
            with patch('sys.argv', argv), patch('builtins.input', side_effect=['Example "SSID"', 'DE']), patch('getpass.getpass', return_value='example-password'):
                runpy.run_path(str(ROOT / 'scripts/wifi-config.py'), run_name='__main__')
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            before = output.read_bytes()
            with patch('sys.argv', argv), patch('builtins.input', side_effect=['OtherSSID', 'DE']), patch('getpass.getpass', return_value='different-password'):
                with self.assertRaises(FileExistsError):
                    runpy.run_path(str(ROOT / 'scripts/wifi-config.py'), run_name='__main__')
            self.assertEqual(output.read_bytes(), before)

    def test_public_bundle_uses_public_initramfs(self):
        assemble = load('assemble-boot')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            assemble.ROOT = root
            (root / '_out/kernel-export').mkdir(parents=True)
            (root / '_out/initramfs').mkdir()
            (root / '_out/private-initramfs').mkdir()
            (root / 'boot').mkdir()
            (root / 'sources.lock.json').write_text(json.dumps({'kernel_version': '6.18.54-talos', 'device_tree': {'assets': {}}}))
            (root / '_out/kernel-export/kernel.spdx.json').write_text('{"packages":[{"versionInfo":"6.18.54"}]}')
            (root / '_out/kernel-export/Image').write_bytes(b'kernel')
            (root / '_out/initramfs/initramfs-arm64.xz').write_bytes(b'public')
            (root / '_out/private-initramfs/initramfs-arm64.xz').write_bytes(b'PRIVATE SECRET')
            (root / 'boot/cmdline.txt').write_text('talos.platform=metal\n')
            (root / 'boot/tryboot.txt').write_text('kernel=talos-test/Image\n')
            assemble.assemble()
            self.assertEqual((root / '_out/boot/talos-test/initramfs-arm64.xz').read_bytes(), b'public')
            self.assertNotIn('test_timeout', (root / '_out/boot/talos-test/cmdline.txt').read_text())
            with self.assertRaises(FileExistsError):
                assemble.assemble()


if __name__ == '__main__':
    unittest.main()
