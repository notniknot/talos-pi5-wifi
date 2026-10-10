"""Check the public/private boundary and pinned release identity without a builder."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BuildInputs(unittest.TestCase):
    def test_versions_keep_upstream_identity(self):
        build = load('build')
        self.assertEqual(build.validate_version('v1.14.2-pi5.1'), 'v1.14.2-pi5.1')
        for version in ['v1.14.2', 'v1.15.0-pi5.1', 'v1.14.2-pi5.0', 'v1.14.2-pi5.1;id', 'v1.14.2-pi5.1\n']:
            with self.assertRaises(ValueError):
                build.validate_version(version)

    def test_boot_assets_match_lock(self):
        lock = json.loads((ROOT / 'sources.lock.json').read_text())
        for name, digest in lock['device_tree']['assets'].items():
            self.assertEqual(hashlib.sha256((ROOT / 'assets/boot' / name).read_bytes()).hexdigest(), digest)

    def test_checksum_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            load('prepare').checked(b'changed', hashlib.sha256(b'original').hexdigest(), 'firmware')

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
