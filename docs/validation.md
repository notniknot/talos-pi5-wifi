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
**Prototype evidence does not validate these new binaries.** Build/test results
are recorded separately below as they become available.

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
