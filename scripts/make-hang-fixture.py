#!/usr/bin/env python3
"""Create a local-only, deliberately unbootable installer build context."""
import argparse
from pathlib import Path
import struct


def make_fixture(kernel: Path, output: Path):
    image = bytearray(kernel.read_bytes())
    if len(image) < 64 or image[56:60] != b'ARM\x64':
        raise ValueError('Expected an uncompressed ARM64 Linux Image')
    # Keep the complete image, PE header, code0 and size fields intact. A tiny
    # synthetic image could be rejected before firmware hands over its watchdog.
    # Replace the normal entry branch (code1) with AArch64 B .: no Linux worker runs.
    struct.pack_into('<I', image, 4, 0x14000000)
    output.mkdir(mode=0o700)  # Refuse existing paths, including release directories.
    (output / 'hang-Image').write_bytes(image)
    (output / 'Dockerfile').write_text(
        'ARG BASE\nFROM ${BASE}\nCOPY hang-Image /usr/install/rpi5/Image\n'
        'LABEL org.opencontainers.image.description="PRIVATE FAILURE TEST: '
        'intentional pre-Linux hang; never publish as a release"\n'
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    make_fixture(args.kernel, args.output)
    print(f'Unbootable test fixture: {args.output}. Never publish as a release.')


if __name__ == '__main__':
    main()
