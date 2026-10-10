# Source provenance

`sources.lock.json` is the machine-readable source of truth. Build scripts fetch
its exact official Talos and pkgs commits, then apply the complete binary-capable
patches in `patches/`. No fork checkout is required to recreate the port.

The original Wi-Fi code comes from `dot8development/talos-wifi`, commits after
`d5f53ed` through `0abf5f5f`, and the accompanying wireless packages from
`dot8development/pkgs`, commits after `4b9bf36` through `5c05b53`.
Those projects and the official Talos/pkgs sources use MPL-2.0. Changes made here
include Pi driver/module selection, 64-hex WPA2 PSKs, link readiness, optional
Wi-Fi power-save disabling, early boot diagnostics, and a direct-boot installer.
Generated Go code and the SELinux policy are regenerated with stable Talos tools.

## Device trees

`assets/boot/` contains the known prototype boot assets. They came from
[siderolabs/sbc-raspberrypi](https://github.com/siderolabs/sbc-raspberrypi)
commit `7aba05ed529e837959cfd15636d53c4e43fb39f2` (v0.2.2), whose DTB build uses
[raspberrypi/linux stable_20260724](https://github.com/raspberrypi/linux/tree/stable_20260724),
its downstream patch set and `disable-v3d` overlay source. The full recipe is
`artifacts/dtb/raspberrypi/pkg.yaml` at the pinned overlay commit.

The one extra DTB edit removes `cgroup_disable=memory` from `/chosen/bootargs`:
Talos needs memory cgroups and does not implement Raspberry Pi OS's override.
To reproduce the assets, build the pinned overlay's `dtb-raspberrypi` target using
its Pkgfile, export `/bcm2712d0-rpi-5-b.dtb` and `/overlays/disable-v3d.dtbo`, then:

```sh
# Requires device-tree-compiler tools; apply to the exported DTB.
DTB=bcm2712d0-rpi-5-b.dtb
BOOTARGS=$(fdtget "$DTB" /chosen bootargs)
fdtput -t s "$DTB" /chosen bootargs "${BOOTARGS//cgroup_disable=memory/}"
```

Use Bash for that substitution. Compare results to the hashes in the lock before
replacing assets. The format marker is plain project text, not firmware.
The Linux device tree sources retain their original license declarations; Linux
license text and syscall exception are in `licenses/`. Consult the pinned source
for the complete corresponding source, DTS includes and build recipe.

## Wi-Fi firmware

The three downloaded files are pinned to RPi-Distro/firmware-nonfree commit
`3bab0f823f5b53150b76aab77093adef6655b920`. The generic NVRAM text is also copied to
the Pi 5 board-specific name. The exact bytes match the working prototype.
`prepare.py` checks SHA256 before staging firmware. The full upstream Debian
copyright file is retained in `licenses/raspberrypi-firmware-copyright` and copied
into the Talos rootfs. Cypress firmware is redistributable under its included
terms, not under this repository's MPL license.

Kernel, wpa_supplicant and wireless-regdb package SBOMs are included by the Talos
rootfs build. The downloaded board firmware is separately identified by the lock
and its license notice; the package SBOM alone is not a complete firmware inventory.
