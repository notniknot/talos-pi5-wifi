# Talos Pi 5 Wi-Fi

An experimental Talos Linux port for a **Raspberry Pi 5 (BCM2712 D0)** using
onboard Wi-Fi and an SSD connected through a USB 3 SATA adapter. It boots the
ARM64 kernel directly through Raspberry Pi firmware and installs Kubernetes
without Ethernet or a serial debug cable.

**Current stable-base port: Talos v1.14.2 → `v1.14.2-pi5.7`.** This revision
corrects the private bootstrap device-tree path and generated single-node
configuration example; hardware validation of this revision is in progress.
The preceding `pi5.6` image passed native upgrades, explicit rollback, automatic
recovery from a deliberately hung kernel, and a public cold boot over Wi-Fi.
Exact results and limits are recorded in [validation](docs/validation.md).
This is not an official Sidero Labs image or a production-supported distribution.

Earlier revisions exposed missing Wi-Fi modules (`pi5.1`), a default reboot error
(`pi5.3`/`pi5.4`), and an apparent USB startup-order dependency (`pi5.5`). Use the
current revision and read the [upgrade guide](docs/upgrading.md).

## What is here

- Pinned official Talos and package sources, plus complete patches for the Wi-Fi
  backport, Pi kernel modules, firmware integration and direct-boot installer.
- Hash-checked boot assets and Wi-Fi firmware, with source and license notices.
- Local build, private maintenance-image, boot-bundle and release scripts.
- Configuration examples, installation/recovery instructions and focused tests.

No cluster credentials, Wi-Fi keys, disk backups or personalized machine
configuration belong in this repository. `_out/` and `private/` are ignored.

## Start here

1. Set up a Linux ARM64 BuildKit builder using [the build guide](docs/building.md).
2. Run `python3 scripts/prepare.py` to fetch the exact sources and apply patches.
3. Build locally with `python3 scripts/release.py`. This creates public files in
   `_out/releases/v1.14.2-pi5.7/`; it does not publish or install anything.
4. For a Pi reachable only over Wi-Fi, create a **private** maintenance image and
   follow [the installation guide](docs/installing.md).

Builds need Python 3.11+, Git, GNU make, Docker Buildx, an ARM64 Linux builder,
roughly 24 GiB RAM and 150 GiB free build storage. Apple Silicon can use a Linux
VM. A first full build is substantial; later builds reuse BuildKit's cache.
There is no GitHub Actions build or paid runner requirement.

## Versioning and image names

Use **`v<upstream Talos version>-pi5.<revision>`**, starting at `v1.14.2-pi5.1`.

| Change | Version |
| --- | --- |
| First port of upstream v1.14.2 | `v1.14.2-pi5.1` |
| A fix to this port on the same upstream | `v1.14.2-pi5.2` |
| Move to upstream v1.14.3 | `v1.14.3-pi5.1` |

This is both a valid SemVer prerelease and an OCI tag. SemVer sorts our build
before the corresponding upstream version; that is intentional for this
experimental distribution. Do not use `+pi5.1`, because `+` is not allowed in
OCI tags. Never overwrite a published tag.

The planned installer image name is
`ghcr.io/notniknot/talos-pi5-wifi/installer:v1.14.2-pi5.7`.
This name does not imply that an image has already been published. Talos reports
the complete custom version; `build.json` also records upstream and project
commits separately. See [local releases](docs/releases.md).

## Scope and known limitations

The tested prototype used a D0 Pi 5 with 8 GB RAM and an Intenso 120 GB SSD through
a USB SATA adapter. Other Pi revisions, adapters and Wi-Fi environments need
validation. Stable Talos v1.14.2 brings kernel `6.18.54-talos`; the tested alpha
prototype used `6.18.48-talos`.

- Upgrades use two boot slots and firmware tryboot with a hardware watchdog.
  Legacy `pi5.1`/`pi5.2` installations need a
  [one-time migration](docs/upgrading.md). Slots share an SSD and FAT filesystem;
  this does not protect against filesystem/media failure or undo data migrations.
- Only SELinux permissive mode has been tested on hardware. The Wi-Fi policy is
  included, but enforcing mode needs validation.
- WPA2 personal was tested; the backport also implements WPA3 personal. Enterprise
  Wi-Fi is not implemented. A derived 64-hex WPA2 PSK cannot authenticate WPA3 SAE.
- The original first installer boot needed recovery. The working recovery also
  enabled early USB/log diagnostics; the exact failure cause remains unresolved.
  See [validation and recovery](docs/validation.md) before erasing an OS disk.
- Wi-Fi power saving is disabled for this Pi profile. Keep the antenna clear of
  the USB SSD/dock, and provide a suitable power supply. RF placement mattered in
  the prototype.
- Fresh installation of the current A/B image, long-term Wi-Fi reliability,
  multi-node operation and secure boot remain unvalidated. See the recorded
  hardware tests rather than treating a successful build as full qualification.

## Sources and license

Repository code and Talos patches are MPL-2.0 unless otherwise marked. Firmware
and device trees retain their upstream licenses. See [third-party sources](docs/sources.md),
[LICENSE](LICENSE), and [licenses/](licenses/).

The Wi-Fi implementation was backported from
[dot8development/talos-wifi](https://github.com/dot8development/talos-wifi).
The base OS and package build system are from
[siderolabs/talos](https://github.com/siderolabs/talos) and
[siderolabs/pkgs](https://github.com/siderolabs/pkgs).
