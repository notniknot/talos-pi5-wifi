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
  assets, and verifies that an upgrade fails before changing any disk byte.
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
