#!/usr/bin/env python3
"""Save source changes, including new files, without vendoring staged firmware."""
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
for name in ('talos', 'pkgs'):
    repo = root / name
    excludes = [':(exclude)hack/rpi5-rootfs', ':(exclude)hack/rpi5-boot'] if name == 'talos' else []
    subprocess.run(['git', 'add', '-N', '--', '.', *excludes], cwd=repo, check=True)
    patch = subprocess.check_output(['git', 'diff', '--binary', 'HEAD', '--', '.', *excludes], cwd=repo)
    (root / 'patches' / f'{name}.patch').write_bytes(patch)
