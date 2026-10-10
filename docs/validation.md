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
published. The existing Pi cluster was not modified.

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
builds now require this check. Hardware recovery/validation is in progress.
