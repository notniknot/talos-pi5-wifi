# Pi firmware upgrades and rollback

This port uses Raspberry Pi firmware `tryboot`, not GRUB or UEFI. The A/B layout
introduced in `v1.14.2-pi5.3` keeps two complete kernel/initramfs/device-tree sets
inside the existing 1 GiB EFI partition. STATE and EPHEMERAL stay in place.
Use revision `pi5.5` or later: `pi5.3`/`pi5.4` have a default-reboot/rollback
kexec error. Hardware validation of the correction is in progress; see
[the recorded results](validation.md).

## Upgrade an A/B installation

Build the new upstream port, including the Pi patches, and publish its **public
installer** to a registry reachable by the node. Follow upstream Talos's supported
version transition requirements. Do not use an unmodified upstream installer,
which does not implement this boot layout. Use an immutable image digest for
hardware tests and deployments:

```sh
talosctl --context YOUR_PI_CONTEXT upgrade \
  --image REGISTRY/REPOSITORY/installer@sha256:YOUR_MANIFEST_DIGEST \
  --reboot-mode=powercycle --drain=false --wait
talosctl --context YOUR_PI_CONTEXT health
kubectl --context YOUR_PI_KUBE_CONTEXT get nodes -o wide
```

`powercycle` here means a firmware reboot requested by Talos; it does not require
you to unplug the power supply. Kexec is intentionally disabled on this Pi.
The installer refuses to overwrite an uncommitted trial, a mismatched running
slot or an unknown boot layout. On this single-node cluster, upgrades interrupt
Kubernetes availability. The example disables draining for this single-node lab;
with multiple nodes, normally keep draining enabled so workloads can move.

To return to the previous committed image:

```sh
talosctl --context YOUR_PI_CONTEXT rollback
talosctl --context YOUR_PI_CONTEXT health
```

Explicit rollback also trials its target before making it the default. Only one
previous image is retained; staging another upgrade consumes the older slot.
OS rollback does not restore old cluster-data contents or reverse arbitrary
application/database migrations. Keep off-device etcd/config backups.

## What happens on failure

1. The installer validates assets, writes the inactive slot, synchronizes it and
   verifies a SHA256 manifest. It leaves `config.txt` pointing to the current OS.
2. `tryboot.txt` points to the candidate. Pending metadata is written last. Talos
   finishes its normal shutdown and issues `reboot("0 tryboot")`; the kernel's
   Pi firmware handler sets the one-shot firmware flag.
3. Firmware clears that flag before starting the candidate. Any subsequent reset
   selects the unchanged normal configuration.
4. The candidate's firmware configuration enables the hardware watchdog. Linux
   feeds it for at most `watchdog.open_timeout=600` seconds while waiting for
   userspace to take ownership. Talos does not take ownership during the trial.
   A kernel hang stops hardware feeding; a missing or unhealthy userspace times
   out. A kernel panic also has a ten-second reboot timeout.
5. Once Talos is Running and Ready, including time/network, required services,
   static control-plane pods and Kubernetes node readiness, it saves the old
   selector, commits the candidate selector, clears pending metadata and disarms
   the watchdog. A configured runtime watchdog can then take ownership.
6. If the old slot boots instead, it clears the failed trial without promoting it.

Each slot contains its own device tree and overlay as well as kernel and
initramfs. A checksummed manifest prevents promotion of incomplete/torn file
copies. The committed configuration is authoritative after a reset during the
commit sequence. The slots share a FAT filesystem and an SSD: this does not
protect against filesystem destruction, controller failure or storage that lies
about completed flushes.

Use Pi EEPROM firmware with `kernel_watchdog_timeout` support (introduced in
2025). For watchdog coverage during firmware loading as well, configure
`BOOT_WATCHDOG_TIMEOUT` in EEPROM; this setting is separate from the kernel
watchdog and is not silently changed by the installer. A hung firmware loader
before kernel handoff cannot be covered by a userspace watchdog.

Firmware references:
[Raspberry Pi tryboot](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#fail-safe-os-updates-tryboot),
[kernel watchdog](https://www.raspberrypi.com/documentation/computers/config_txt.html#kernel_watchdog_timeout),
[bootloader watchdog](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#BOOT_WATCHDOG_TIMEOUT).

## One-time migration from pi5.1/pi5.2

Those images lack the kernel tryboot reboot handler and the slot-confirmation
controller. Their legacy EFI marker is deliberately rejected by the new
installer; replacing it alone does not make an old image upgrade-capable.

Back up etcd, machine configuration and the full EFI partition first. Build an
A/B-capable public installer. On the dedicated Linux builder, the disposable-disk
test can export the exact initial boot layout without touching a physical disk:

```sh
sudo CONTAINER=podman EXPORT_INITIAL_BOOT=/absolute/path/migration-boot.tar \
  scripts/test-installer.sh INSTALLER_IMAGE
```

The destination must not exist. The export contains `talos/A`, `config.txt` and
the new layout marker, with no machine or Wi-Fi configuration. The test also
checks that a subsequent staged upgrade preserves GPT, STATE and EPHEMERAL.

During a maintenance window, copy the exported slot directory to the Pi's EFI
partition, verify its manifest, preserve the current firmware configuration as a
recovery copy, and replace `config.txt` and the layout marker last. Synchronize,
unmount and reboot through Talos. This first migration is a manual boot switch:
the old running kernel cannot initiate a firmware tryboot, so have physical SSD
recovery access available. Do not repartition or format STATE/EPHEMERAL.

Verify the new version, Talos health, node identity, DNS/HTTP and a software
reboot before relying on subsequent `talosctl upgrade` operations. Keep the old
EFI backup off-device; a fallback image for normal A/B operations must itself
contain the A/B support.
