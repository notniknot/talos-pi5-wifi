# Validation and limitations

## Evidence from the original prototype

A Pi 5 D0 / 8 GB with a USB SATA SSD successfully ran the Wi-Fi fork at
`0abf5f5f887939226916b3412c891f8a39ee4bc7` plus local patches, reporting
`v1.15.0-alpha.0-rpi5-wifi`. It used kernel `6.18.48-talos` and Kubernetes v1.37.1.

Observed results: onboard Wi-Fi association/DHCP, Talos API, single control-plane
installation, Ready node, healthy control-plane services, scheduling workloads
on the control plane, internal/external DNS, ClusterIP HTTP, a software reboot,
and a reset limited to STATE/EPHEMERAL followed by a fresh cluster bootstrap.
After moving the Pi closer to its access point and disabling Wi-Fi power saving,
a 60-packet check showed no loss. That is not a long-term reliability result.

First installation did not boot successfully until recovery replaced the EFI
initramfs and enabled diagnostics. Those changes were made together, so the
cause was not isolated. Diagnostics also load USB-storage drivers early. The
subsequent running cluster read its config from STATE. Upgrades/rollback and
SELinux enforcing mode were not tested; full-disk reset is not supported here.

## Stable port

The v1.14.2 port uses official Talos commit
`f513c7358cefc69255e29b517ba96c651e0326ad` and kernel `6.18.54-talos`.
**Prototype evidence does not validate these new binaries.** Local validation on 2026-10-10 passed for source commit
`67c8792c2c1931af4472f9412493ce9318acc54e`:

| Check | Result |
| --- | --- |
| Complete patches against clean pinned sources; repeated preparation | Passed |
| Five local Python tests; generated/example config validation | Passed |
| Wi-Fi controller/config/country-consistency tests | Passed |
| Direct-boot installer unit tests | Passed |
| Kernel, full machine daemon, public initramfs and installer builds | Passed |
| macOS ARM64 and Linux ARM64 custom client builds | Passed |
| Public rootfs contains no embedded machine config | Passed build guard |
| Full local release packaging, checksums and custom OCI labels | Passed |
| Initial install into a disposable 8 GiB loop disk | Passed |
| Upgrade refusal before changes, verified with whole-disk SHA256 | Passed |
| Private Wi-Fi maintenance image and diagnostic tryboot bundle build | Passed locally; private artifacts excluded from release |
| pi5.1 boot over Wi-Fi on the physical Pi | **Failed: ARM64 image omitted Wi-Fi kernel modules** |

Public boot-bundle SHA256:
`b94520fb010b598625e773c178b2ae65f14629b5707879f0c136bd66db6fe319`.
Public installer OCI-archive SHA256:
`67676016bd8e5af84c14ce0f5e51c7e8fafa2e38c4756ae6aa638f8bf9ba72f3`.
These identify the local validation artifacts; no GitHub image release was
published. These hashes identify the earlier `pi5.1` build, which subsequently
failed the hardware Wi-Fi boot test; do not deploy it.

Before publishing a release:

- Prepare from a clean checkout, verify patch application and all source hashes.
- Run Python script tests, Wi-Fi controller/config tests and bootloader tests.
- Build kernel, public initramfs, installer and custom talosctl. Validate example
  configuration with the custom client. Confirm there is no embedded config in
  public rootfs and no private data in the release directory.
- Run `scripts/test-installer.sh` on the Linux builder with the public installer.
  It creates its own disposable loop device, installs into that, checks boot
  assets, stages an A/B upgrade without changing the active slot or cluster-data
  partitions, and verifies that pending-trial and legacy-layout upgrades are
  rejected before changing any disk byte.
- Test private tryboot and recovery to Pi OS before erasing a disk.
- Test the **public installed initramfs** loading Wi-Fi config from STATE, both
  warm and cold boot. Isolate any requirement for early USB diagnostics.
- Bootstrap Kubernetes, run health checks and the smoke workload, then reboot and
  repeat. Test Wi-Fi for a sustained period, including reconnect behavior.
- Test targeted reset only with a private boot recovery path ready; capture the
  exact expected network behavior after deleting STATE.

The smoke workload checks DNS and HTTP without privileged containers:

```sh
kubectl apply -f tests/smoke.yaml
kubectl -n pi5-smoke-test rollout status deployment/web --timeout=180s
kubectl -n pi5-smoke-test wait --for=condition=complete job/networking --timeout=300s
kubectl delete namespace pi5-smoke-test
```

Retain private logs and recovery backups locally. Release notes should record
artifact hashes, Pi revision, adapter model, results, and untested features,
without personal network identifiers or credentials.


## pi5.2 packaging correction

Hardware testing exposed that the wireless-module copy step had been applied to
`depmod-amd64` rather than `depmod-arm64`. The Pi kernel contained the drivers,
but its rootfs did not. The copy step now runs in the ARM64 stage. The new
`image-tests` target checks cfg80211, mac80211, brcmfmac and its WCC module, Wi-Fi
firmware, wpa_supplicant and the regulatory database in the assembled rootfs.
It reproduced the failure before the fix and passed after the fix. Local release
builds now require this check.

The corrected local release was built from clean project commit
`72f4b39c86da153935fb6d0cc22e65c38bba3f0a` and reports `v1.14.2-pi5.2`.
Its public boot-bundle SHA256 is
`b27f84e87b5cdbb3abb5a69871837ade9ca7e4fa3784fbce3adc700ac0d2bdeb`;
its installer OCI-archive SHA256 is
`ebccf167a87d61ed8820b0851c5fa8968159039585f082860e3573e8ed49695d`.

The corrected installer also passed initial installation into a disposable 8 GiB
loop disk; its unsupported upgrade path refused before changing any disk byte.
The five Python script tests passed again.

Hardware validation on 2026-10-10 used the original D0 / 8 GB Pi and USB SATA SSD:

- Backed up etcd, machine configuration and EFI before changing boot files.
- Recovered through an EFI-only SSD write, verified by full read-back comparison.
  STATE and the primary partition-table area were byte-identical before/after.
- Cold-booted the corrected public initramfs with the existing STATE Wi-Fi config.
  Talos reported `v1.14.2-pi5.2`, kernel `6.18.54-talos`, containerd `2.3.6`;
  Kubernetes remained `v1.37.1`.
- Original node and kube-system namespace UIDs were preserved; all Talos health
  checks passed and the node became Ready.
- The smoke Job passed internal/external DNS and ClusterIP HTTP checks after
  initial retries while Kubernetes recovered.
- A Talos software reboot returned over Wi-Fi without a power cycle. The new
  boot ID, unchanged node UID and Ready status were verified; all Talos health
  checks passed again. The DNS/HTTP smoke Job also passed after this reboot,
  and its temporary namespace was removed.
- A 30-packet Wi-Fi check had no loss, but latency ranged from 19 to 556 ms.
  This is a short connectivity check, not a reliability or performance guarantee.

Both cold and warm boots started with the clock at 1970. Before time synchronization, Talos
rejected and removed the existing kubelet client certificate as not yet valid.
Automatic certificate renewal and control-plane recovery completed, but added a
startup delay. This timing issue remains a follow-up; it was not fixed by the
Wi-Fi packaging correction.

This was a manual EFI replacement with local backups and an old-image fallback,
not a Talos API upgrade. Diagnostic early USB loading remained enabled. A fresh
stable installation without that setting, automatic rollback, and long-term
Wi-Fi reliability still need separate hardware validation. Build metadata retains
`hardware_validated: false` because the full release qualification is incomplete.

## A/B upgrade implementation

The `pi5.3` and `pi5.4` local builds use project commit `22324ce` and the same
upstream Talos/kernel versions as `pi5.2`. They add the Pi firmware tryboot reboot
handler, two boot slots, readiness-gated confirmation and watchdog fallback.

Local validation on 2026-10-10 passed:

- Complete source preparation, Python tests, Wi-Fi tests and image-content guards.
- Boot-slot unit tests, including interrupted confirmation, failed trials,
  explicit rollback, corrupted assets and invalid metadata.
- Existing upgrade-fallback, runtime-watchdog and sequencer tests.
- Full kernel, machine daemon, public installer/initramfs and both client builds.
- Disposable-disk integration for both final installers: initial install, staged
  upgrade, unchanged active assets/GPT/seeded STATE and EPHEMERAL, and byte-for-byte
  refusal of pending-trial and legacy-layout upgrades.

The existing physical Pi was migrated to slot A on `pi5.3` using an EFI-only file
update after off-device backups. It returned over Wi-Fi through a Talos software
reboot, retained its Kubernetes node UID, and passed all Talos health checks.
This bootstrap slot retains the diagnostic early USB-loading setting.

A standard `talosctl upgrade --reboot-mode=powercycle --drain=false` then installed
`pi5.4` in slot B. Hardware evidence confirmed a new boot ID, firmware tryboot=1,
and the public command line without diagnostic USB loading. All Talos health
checks and the DNS/HTTP smoke Job passed. Read-only EFI inspection confirmed
`config.txt` selected B, `previous.txt` selected A and pending/tryboot files were
removed. The node UID remained unchanged.

The subsequent explicit rollback did not return online. Source inspection found
that the Pi's kexec hook returned an error, which aborts the default reboot path
before the firmware reboot task. Revision `pi5.5` changes that hook to a successful
no-op and adds a regression test. A cold power cycle recovered the committed
`pi5.4` slot; this recovery was manual, not a watchdog-fallback result.

The first public `pi5.5` trial failed to become reachable. After the ten-minute
startup deadline, the Pi automatically returned to committed `pi5.4` without
physical intervention. Firmware boot count increased from 1 to 3, reset status
changed to `0x20`, and the fallback reported tryboot=0. All Talos health checks
passed. EFI inspection confirmed B remained selected, pending/tryboot metadata
was cleared, and the candidate assets still matched their manifest. The CLI
upgrade wait returned success despite fallback, so verify the running server
version separately. A retry of the same `pi5.5` assets with diagnostic early USB loading enabled
booted slot A successfully, passed all health checks and committed A with B as
its previous slot. Plain `talosctl rollback` then returned to `pi5.4` in slot B
with tryboot=1, passed all health checks, committed B, and retained A as the
previous slot. This validates the corrected default reboot path, but does not
qualify the unmodified `pi5.5` boot path.

Revision `pi5.6`, built from clean project commit `12de789`, preloads Pi USB host
and storage modules in the existing Pi-specific udev startup hook. This is a
focused mitigation for the apparent boot-order dependency; the failed `pi5.5`
trial did not provide logs proving its precise cause. Its full local release and
disposable-disk checks passed. A normal `talosctl upgrade --namespace cri` then
booted the public `pi5.6` image in slot A without diagnostic flags. Firmware
reported tryboot=1, all health checks passed, and EFI inspection confirmed A was
committed with B as the previous slot and no pending/tryboot metadata remaining.
The original Kubernetes node UID has remained unchanged through completed tests.
The first synthetic pre-Linux hang fixture used a truncated 4 KiB ARM64 image.
It did not return online within fifteen minutes of losing API access, so this
is **not** a successful early-kernel watchdog test. A firmware rejection before
kernel handoff is one possible explanation, not a confirmed cause. Recovery via
a cold power cycle also failed to restore observed network access. Read-only SSD
inspection found a clean FAT filesystem, the healthy A selector and assets intact,
and pending/tryboot files already absent. Their absence suggests the OS cleared
the trial at some point, but neither the timing nor the connectivity failure is
established. Enabling existing boot diagnostics restored access; this changes
early USB initialization, so it does not isolate the cause.

On 2026-10-10, a repeat native upgrade with the **default reboot mode** installed
public `pi5.6` in B without diagnostic flags. Firmware reported tryboot=1 and
boot count 2. All health checks and DNS/HTTP smoke tests passed. EFI inspection
confirmed B was committed, A was retained as the previous slot, and pending
metadata was cleared.

The revised failure fixture preserves the entire 65,169,920-byte kernel image,
including its header, and changes only the ARM64 entry branch at offset 4 to
`B .`. Its installed kernel SHA256 was
`4f7ff2df3954e88358b0ca7318db5a1e9e098df0a192cd7d43a3949db3cec898`.
A native upgrade staged this deliberately hung kernel in A. **Without a manual
power cycle**, the Pi returned to healthy public B roughly a minute after API
access disappeared. The boot ID changed, firmware count advanced from 2 to 4,
tryboot was 0 and reset status was `0x20`. All Talos/Kubernetes health checks
passed and the original node UID was preserved. Read-only EFI inspection verified
the exact hung kernel remained in A, healthy B was still selected, and
pending/tryboot metadata had been removed. This demonstrates automatic watchdog
fallback after kernel handoff; it does not demonstrate recovery from a firmware
loader hang before handoff. EEPROM `BOOT_WATCHDOG_TIMEOUT` was not configured or
validated in this test.

A subsequent native upgrade restored the public image in A. It passed all health
checks and DNS/HTTP smoke tests. EFI verification found A committed, B retained
for explicit rollback, both kernels and initramfs files matching the public
release, and no diagnostic flags or pending trial. The two failure-test images
and their cache aliases were removed from the node; temporary privileged and
smoke-test namespaces were deleted. Cluster node identity remained unchanged.

The final physical power cycle also passed with the public image and diagnostics
disabled. It booted the committed A slot with a new boot ID, firmware count 1
and tryboot=0. All Talos/Kubernetes health checks and the DNS/HTTP smoke test
passed; the original node UID was preserved. This validates a cold boot of the
restored image, but does not explain the earlier connectivity loss or establish
long-term boot/Wi-Fi reliability.

The exact public `pi5.6` artifacts tested have these SHA256 values:

- Boot bundle: `9de8f4783edd70820768182ffd7662ade50236e930c26553158a36837f95c77d`.
- Installer OCI archive: `51de1603f482d9cf32dee70ab77fab62b4ff8e81a66e6a83635e7973541778cd`.
- Local-registry installer manifest: `eb9c581c8c1be75338fd936d32a1906351af1344fec7517df01898831bdbe7fa`.
- Installed kernel: `e64d3eb7f60d54dd6507b5e7635bda9b575784d11c90f301f2cba324f9341c28`.
- Installed initramfs: `2d58e49c97408ee04a59e6a0e83e1644f7bb51456eced5b02f446ae59f52ad54`.

The registry manifest digest depends on OCI-to-registry layer representation;
verify the digest returned by your own registry when publishing the archive.
