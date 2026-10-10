# Local builds

## Builder setup

Use a native ARM64 Linux host or VM. The scripts also run on macOS and send
builds to a remote ARM64 BuildKit daemon. Allow about 24 GiB RAM and 150 GiB of
free storage; avoid putting this build on the Pi you are installing.

Requirements on the command host: Python 3.11+, Git, GNU make (`gmake` on macOS),
and Docker Buildx. The kernel uses the pinned Sidero Labs build frontend and
container toolchains, not the host compiler. Build downloads require internet.

One Linux Docker setup is below. Run it from this checkout, and use a dedicated
builder host: BuildKit runs privileged and its API must not be exposed publicly.
The registry shares BuildKit's network namespace, so package references using
`localhost:5000` resolve from inside the builder.

```sh
docker volume create talos-pi5-buildkit
docker volume create talos-pi5-registry
docker run -d --name talos-pi5-buildkit --privileged \
  -p 127.0.0.1:12340:1234 \
  -v talos-pi5-buildkit:/var/lib/buildkit \
  -v "$PWD/boot/buildkitd.toml:/etc/buildkit/buildkitd.toml:ro" \
  moby/buildkit:v0.34.0 --addr tcp://0.0.0.0:1234
docker run -d --name talos-pi5-registry \
  --network container:talos-pi5-buildkit \
  -v talos-pi5-registry:/var/lib/registry registry:2
docker buildx create --name talos-pi5 --driver remote tcp://127.0.0.1:12340
export BUILDER=talos-pi5
```

Docker Desktop on Apple Silicon can use the same container setup if its VM has
enough resources. Podman can host these services too; use Docker's standalone
Buildx client against the forwarded BuildKit port. Configure Podman with at least
24 GiB RAM and a 180 GiB disk. On macOS, keep the VM/port-forwarding service running
through the entire build. Do not change another project's default connection.

Optional environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `BUILDX` | `docker buildx` | Buildx executable/command |
| `BUILDER` | Buildx default | Builder name |
| `MAKE` | `gmake`, then `make` | GNU make executable |
| `PACKAGE_PREFIX` | `localhost:5000/talos-pi5-wifi` | Registry path reachable by BuildKit |
| `PACKAGE_TAG` | release version | Tag for intermediate kernel/Wi-Fi packages |

## Prepare and build

```sh
python3 scripts/prepare.py
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/release.py --version v1.14.2-pi5.7
```

Preparation checks exact Git commits and asset hashes. Existing source trees
with unexpected commits or incompatible changes cause an error; they are never
reset. Patch files contain the complete delta from the official sources,
including the Wi-Fi backport. Prepared trees are ignored, so preserve deliberate
source edits with `python3 scripts/save-patches.py`.

Individual targets are useful while developing:

```sh
python3 scripts/build.py kernel
python3 scripts/build.py wpa-supplicant
python3 scripts/build.py wireless-regdb
python3 scripts/build.py wifi-tests
python3 scripts/build.py boot-tests
python3 scripts/build.py image-tests
python3 scripts/build.py kernel-export
python3 scripts/build.py initramfs
python3 scripts/build.py installer
python3 scripts/build.py talosctl-darwin-arm64
python3 scripts/build.py talosctl-linux-arm64
python3 scripts/assemble-boot.py
```

The installer is `_out/installer/installer-arm64.oci.tar`. The public initramfs
contains drivers and firmware but **no Wi-Fi configuration**. The installer
build checks that `/usr/local/etc/talos/config.yaml` is absent from its rootfs.
The public boot tarball is a tryboot file bundle, not a raw flashable disk image.

`proto` and `generated` are maintenance targets for regenerating protobufs,
configuration/resource code and SELinux policy after source edits. Outputs land
in `_out/proto/` and `_out/generated/`; review and copy the intended generated
files into `talos/`, then save patches. Normal builds use the checked-in patches.

## Private maintenance image

```sh
python3 scripts/wifi-config.py
_out/talosctl-darwin-arm64/talosctl-darwin-arm64 validate \
  --config private/maintenance.yaml --mode metal --strict
python3 scripts/build.py private-initramfs --wifi-config private/maintenance.yaml
python3 scripts/assemble-boot.py --private --diagnostics
```

Use the Linux client on Linux. `wifi-config.py` prompts for credentials without
putting them in command arguments and refuses to overwrite an existing file.
`--wpa2-derived-key` stores a derived WPA2 key instead of the original passphrase;
the derived key still grants network access and remains a secret.

The config enters BuildKit as a secret, but the resulting private rootfs and
BuildKit cache **contain that secret**. Protect both the builder and
`_out/private-initramfs/` / `_out/private-boot/`. Never upload them, export their
cache to a public registry, or use the private initramfs as a release artifact.
Local release packaging uses an explicit public file allowlist.

The Pi diagnostic option logs early boot to `talos-test/boot-*.log`. It does not
set `talos.rpi5.test_timeout`, which would arm a reboot watchdog. Keep that option
out of permanent installations.
