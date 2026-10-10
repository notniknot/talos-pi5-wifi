# Operating the two Pis

Run commands from the root of this repository. This runbook describes this
custom direct-boot port; a stock Talos installer is not interchangeable with it.
Build locally, validate on one Pi, and then update the other. Never overwrite a
published version tag.

## Inventory and access

| Node | Address | Role | Last verified OS |
| --- | --- | --- | --- |
| raspberry1 | 192.168.178.31 | Sole control plane | v1.14.2-pi5.7 |
| raspberry2 | 192.168.178.110 | Worker | v1.14.2-pi5.6 |

Cluster/context name: `raspberry-pi`. Kubernetes was `v1.37.1` when this runbook
was written. Both nodes have KubeSpan enabled and share the cluster's discovery
identity. Keep their DHCP reservations stable. The control plane is not highly
available: taking raspberry1 down interrupts the Kubernetes API and etcd.

```sh
export TALOSCTL="$PWD/_out/talosctl-darwin-arm64/talosctl-darwin-arm64"
# Linux ARM64: use _out/talosctl-linux-arm64/talosctl-linux-arm64 instead.
export TALOSCONFIG="$PWD/private/raspberry-pi/talosconfig"
export KUBECONFIG="$PWD/private/raspberry-pi/kubeconfig"
"$TALOSCTL" -e 192.168.178.31 -n 192.168.178.31 version
kubectl get nodes -o wide
"$TALOSCTL" -e 192.168.178.31 -n 192.168.178.31 get kubespanpeerstatuses
"$TALOSCTL" -e 192.168.178.110 -n 192.168.178.110 get kubespanpeerstatuses
```

These exports select only this shell's cluster. Global contexts also exist in
`~/.kube/config` and `~/.talos/config`; use `--context raspberry-pi` explicitly
when not using the private files. A worker cannot proxy requests to another node.

Each KubeSpan peer should be `up`, with a recent handshake and increasing RX/TX
when traffic crosses nodes. KubeSpan encrypts inter-node traffic; the Mac still
needs a reachable LAN endpoint. After raspberry1 was moved closer to the
repeater, both nodes passed Talos health checks and bidirectional pod DNS/HTTP
and 1 MiB transfer tests with KubeSpan up. See [validation](validation.md#two-node-cluster-and-kubespan)
for the results. Earlier Wi-Fi/API timeouts show that placement matters; these
short tests do not establish long-term reliability.

## Before a disruptive operation

Have physical power/SSD recovery access, a tested maintenance image, and copies
of the private configuration away from the Pi. Check both nodes' readiness and
Wi-Fi connectivity first. A flaky link can make a healthy reboot look like a
failed upgrade. Talos has no SSH service.

```sh
umask 077
BACKUP="$PWD/private/backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP"
cp private/raspberry-pi/{talosconfig,kubeconfig,raspberry1.yaml,raspberry2.yaml} "$BACKUP/"
"$TALOSCTL" -e 192.168.178.31 -n 192.168.178.31 etcd snapshot "$BACKUP/etcd.snapshot"
"$TALOSCTL" -e 192.168.178.31 -n 192.168.178.31 get machineconfig -o json > "$BACKUP/raspberry1.json"
"$TALOSCTL" -e 192.168.178.110 -n 192.168.178.110 get machineconfig -o json > "$BACKUP/raspberry2.json"
```

Check that every command succeeded and files are nonempty. Machine configuration
and snapshots contain secrets; keep `private/` out of Git and copy backups to
protected storage off this Mac too. Etcd snapshots do not back up application
volumes. Back those up separately before a reset or version migration.

## Port a newer upstream Talos release

A new upstream tag requires porting and validation, not just changing the
installer tag. Review its release notes, supported upgrade path and supported
Kubernetes versions at [Sidero Labs' Talos repository](https://github.com/siderolabs/talos/releases).
Keep the current Kubernetes version during the OS upgrade if the new OS supports
it; upgrade Kubernetes as a separate operation.

1. Start a clean checkout/branch such as `build/talos-1-14-3`, preserving the
   working checkout, its prepared source trees and recovery artifacts. The
   numbers here are examples, not a claim that that release is available.
2. Resolve the chosen official Talos tag to its full commit. Read that commit's
   `Makefile` to find the exact `PKGS` revision, resolve it in `siderolabs/pkgs`,
   and inspect its kernel version/config. Update `sources.lock.json`:
   `upstream_version`, `talos.commit`, `pkgs.commit`, `kernel_version` and
   `default_version`. For example, a first port becomes `v1.14.3-pi5.1`; another
   port fix on the same upstream increments only `pi5.N`.
3. Prepare clean `talos/` and `pkgs/` trees at those new pinned commits and port
   `patches/talos.patch` and `patches/pkgs.patch`. `scripts/prepare.py` deliberately
   stops when a tree has the wrong HEAD or a patch no longer applies. Resolve
   conflicts in the new checkout; do not reset the known-working source trees.
   Review upstream equivalents before removing any backport.
4. Check the Wi-Fi config/controller, wpa_supplicant and firmware packaging,
   BCM2712/SDIO/USB-SATA kernel support, direct firmware reboot handler,
   installer A/B layout, slot confirmation and watchdog behavior. Reassess
   device-tree/kernel compatibility. Update boot assets, firmware hashes and
   license notices if their inputs changed. A compiling patch is not enough.
5. Run `python3 scripts/save-patches.py` against the newly pinned trees to save
   their full delta. It compares against each tree's HEAD, so first verify those
   HEADs equal the new lock entries. Re-run preparation in another clean checkout
   to prove the saved patches and lock reproduce the result.
6. Commit the source/lock/patch changes and build from that commit. The release
   metadata records both the upstream pins and this project's commit.

Follow [builder setup](building.md) first; the ARM64 Linux builder needs about
24 GiB RAM and 150 GiB free storage. A macOS ARM64 VM works. Then:

```sh
VERSION=v1.14.3-pi5.1 # Replace with the version you just ported and pinned.
python3 scripts/prepare.py
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/release.py --version "$VERSION"
(cd "_out/releases/$VERSION" && shasum -a 256 -c SHA256SUMS)
```

`release.py` builds the kernel, Wi-Fi packages, installer, boot files and custom
clients, and runs the Wi-Fi/boot/image tests. An existing release directory is
rejected; preserve the old artifacts instead of overwriting them. Run the
disposable-disk test in [validation](validation.md) on the Linux builder too.
Record skipped tests explicitly. Release packaging excludes private images.

## Publish a candidate and upgrade one Pi

Publish the **public** OCI installer to a registry the Pis can reach. The local
builder's `localhost:5000` registry cannot be reached by the Pis. This example
requires registry credentials on the Mac; a private package also needs pull
credentials in the node configuration.

```sh
REPO=notniknot/talos-pi5-wifi
skopeo copy \
  "oci-archive:_out/releases/$VERSION/talos-pi5-wifi-$VERSION-arm64-installer.oci.tar" \
  "docker://ghcr.io/$REPO/installer:$VERSION"
DIGEST=$(skopeo inspect --format '{{.Digest}}' "docker://ghcr.io/$REPO/installer:$VERSION")
IMAGE="ghcr.io/$REPO/installer@$DIGEST"
```

Upgrade raspberry2 first. It is the worker, so this tests the image without
replacing the only etcd member. Account for workload disruption: the control
plane is normally tainted and there is only one worker, so drained workloads
may remain Pending until the worker returns. Do not bypass a PodDisruptionBudget
automatically; arrange a maintenance window if required.

```sh
PI=192.168.178.110
"$TALOSCTL" -e "$PI" -n "$PI" read /proc/sys/kernel/random/boot_id
"$TALOSCTL" -e "$PI" -n "$PI" upgrade \
  --image "$IMAGE" --reboot-mode=powercycle --wait --timeout=20m
"$TALOSCTL" -e "$PI" -n "$PI" version
"$TALOSCTL" -e "$PI" -n "$PI" get machinestatus
kubectl wait --for=condition=Ready node/raspberry2 --timeout=5m
"$TALOSCTL" -e "$PI" -n "$PI" get kubespanpeerstatuses
```

Use the candidate release's custom client when an upstream version transition
requires it. `powercycle` requests a firmware reboot; it does not ask a human
to unplug power. Compare the **server** version with `$VERSION`: a successful
CLI wait can also mean the old image recovered after a failed trial. Confirm
the boot ID changed, Kubernetes is Ready, and application/DNS/inter-node traffic
works. Do a cold boot on the candidate Pi before qualifying a new upstream port.
Once it passes, repeat for `PI=192.168.178.31` in a control-plane maintenance
window and wait for `node/raspberry1` instead. Run full health from raspberry1:

```sh
"$TALOSCTL" -e 192.168.178.31 -n 192.168.178.31 health \
  --control-plane-nodes 192.168.178.31 --worker-nodes 192.168.178.110
```

Update each node's saved `UnattendedInstallConfig.installer.image` to the
validated digest so later config application cannot restore an old desired
image. Keep the immutable digest and hardware results in release notes; publish
the source tag/release using [releases](releases.md). No GitHub Actions build is
required.

### Rollback and an offline Pi

```sh
# PI must be the individual node you intend to roll back.
"$TALOSCTL" -e "$PI" -n "$PI" rollback
"$TALOSCTL" -e "$PI" -n "$PI" version
```

Each upgrade trials the inactive slot and commits only after node readiness.
A hung kernel or unhealthy trial is meant to reboot into the previous slot;
allow the roughly ten-minute watchdog window plus fallback boot time before
intervening. Repeatedly unplugging power makes recovery testing inconclusive.
The next upgrade overwrites the older slot. Rollback restores OS boot assets,
not etcd, volumes or arbitrary data migrations. Read [the exact failure coverage
and recovery procedure](upgrading.md) before relying on it.

If the Pi stays offline, try one cold boot, then use Ethernet/display or attach
the powered-off Pi's SSD to the Mac. Back up EFI before repair and identify the
disk afresh with `diskutil list`. Do not guess a previous `diskN`. Keep known-good
boot bundles/private maintenance artifacts; do not copy only a mismatched kernel
or overwrite the whole SSD during a boot repair.

## Install from scratch

The public `*-boot.tar.gz` is a firmware file bundle, **not a raw disk image**;
do not `dd` it to an SSD. Use the complete [installation guide](installing.md):

1. Boot Raspberry Pi OS from the target SSD and establish SSH/Wi-Fi. Confirm the
   board, USB boot firmware, disk model/serial and backups.
2. Build a private Wi-Fi maintenance initramfs with `scripts/wifi-config.py`,
   `scripts/build.py private-initramfs --wifi-config private/maintenance.yaml`
   and `scripts/assemble-boot.py --private` using the candidate's sources.
3. Copy the private boot bundle to Pi OS, verify its hashes, and use one-time
   `reboot '0 tryboot'`. Verify Talos maintenance API, Wi-Fi and the intended
   installation disk before erasing Pi OS.
4. Make the public custom installer reachable and apply the correct full machine
   configuration. This initial installation destroys the disk's old contents.
   Keep Wi-Fi, link/DHCP, hostname and KubeSpan/discovery documents in that config.
5. For a replacement **raspberry2 joining this cluster**, use its existing worker
   configuration/current cluster secrets, with its intended image and disk;
   do not generate another cluster and do not run `bootstrap` on the worker.
   Remove the obsolete Node object only when that old machine is retired.
6. Replacing the sole control plane requires an explicit choice: restore the old
   cluster from etcd backup, or create a new empty cluster and reconfigure/reset
   the worker. A fresh bootstrap does not restore the previous cluster's data.

The Pi address may change between Pi OS and Talos DHCP. Confirm identity before
applying config. Once installed, a power cycle no longer returns to Pi OS.

## Reset while retaining Wi-Fi and boot slots

`EPHEMERAL` holds etcd/Kubernetes runtime data. `STATE` holds the persisted
machine configuration, including Wi-Fi. EFI holds the custom boot slots.
An EPHEMERAL-only reset of these two stable-port nodes was used to recreate this
cluster successfully. It is destructive to local runtime data; it does not
sanitize the disk or return the node to unconfigured maintenance mode.

### Reset/rejoin the worker to the same cluster

Back up application data first. Check its saved worker config still names the
correct cluster, hostname, Wi-Fi and installer. Drain deliberately, then reset:

```sh
kubectl drain raspberry2 --ignore-daemonsets --delete-emptydir-data --timeout=5m
# Proceed only after a successful drain, or a separately planned outage.
"$TALOSCTL" -e 192.168.178.110 -n 192.168.178.110 reset \
  --wipe-mode=system-disk --system-labels-to-wipe=EPHEMERAL \
  --graceful=false --reboot --wait=false
# Wait for the worker to reboot and become Ready, then:
kubectl wait --for=condition=Ready node/raspberry2 --timeout=10m
kubectl uncordon raspberry2
```

Here `--graceful=false` follows the explicit drain. The flag itself is not a
replacement for workload shutdown. Verify the new boot ID/uptime as well:
`kubectl wait` alone can briefly see stale Ready status from before the reboot.

### Destroy and recreate the whole cluster

Resetting the sole control plane destroys its etcd database. Do this only when
discarding the cluster or following a tested etcd restore plan. For a new empty
cluster, prepare and validate both full configs first (one control plane, one
worker, shared new secrets, correct Wi-Fi/KubeSpan and hostnames). Save the old
and new Talos client configs separately.

Using the **old** credentials, apply each new config with `--mode=staged`, check
success, then issue the EPHEMERAL-only reset above to that same node. Staging
persists the new config for the next boot; it does not activate it immediately.
Do not overwrite an old client context until both resets have been submitted.
After reboot use the **new** credentials, bootstrap raspberry1 **once**, retrieve
the new kubeconfig, and let raspberry2 join. Verify both hostnames, roles,
readiness, KubeSpan and cross-node traffic before calling the reset complete.

```sh
# Repeat per node, with OLD_TALOSCONFIG and NEW_NODE_CONFIG set deliberately.
"$TALOSCTL" --talosconfig "$OLD_TALOSCONFIG" -e "$PI" -n "$PI" apply-config \
  --file "$NEW_NODE_CONFIG" --mode=staged
# Then the targeted reset, still using OLD_TALOSCONFIG, before changing contexts.
```

For resetting within the same cluster identity, preserve STATE and its existing
configs, reset both nodes' EPHEMERAL partitions, then bootstrap only raspberry1.
Do not run bootstrap as an attempted fix for an existing healthy etcd cluster.

### Return to unconfigured maintenance / decommission

Wiping `STATE,EPHEMERAL` removes Wi-Fi and cluster credentials. The public image
has no embedded Wi-Fi credentials, so arrange working Ethernet or a tested
private maintenance boot path **before** such a reset. An unqualified full-disk
reset can also remove this port's EFI boot layout. These are different operations
from the Wi-Fi-preserving reset above, and neither is secure media erasure.

## Manage configuration and Kubernetes with TOPF

Follow [the TOPF runbook](topf.md) for the compatible local build, importing this
cluster's existing secrets, reviewing rendered configuration, and applying one
node at a time. TOPF manages Talos and Kubernetes cluster configuration; use
`kubectl`, Helm or your GitOps controller for application resources.
