# Raspberry Pi cluster handoff

This folder is the configuration source for our two-node home cluster. Both Pis
run the custom Talos `v1.14.2-pi5.7`, Kubernetes is `1.37.1`, and KubeSpan is
disabled. Flannel carries pod traffic over the LAN. Keep the router's DHCP
reservations stable and both Pis within reliable Wi-Fi range.

| Name | Address | Job |
| --- | --- | --- |
| raspberry1 | 192.168.178.31 | Only control plane and etcd member |
| raspberry2 | 192.168.178.110 | Worker for applications |

The cluster is not highly available. Rebooting raspberry1 temporarily takes the
Kubernetes API offline; losing its data requires an etcd restore or rebuilding
the cluster. Talos has no SSH login. The USB-C port supplies power; management
uses the network.

## What to give the next maintainer

Share **this whole folder**, including its ignored `bin/`, `secrets/` and
`patches/all/90-wifi.yaml`, through a private encrypted transfer. A Git clone
alone deliberately lacks the credentials and binaries. Do not post the complete
folder or a credential-bearing archive to the public repository or a public
release. No transfer to another person is performed automatically.

- `topf.yaml` identifies the cluster, versions, nodes and roles.
- `patches/` contains small overrides. `90-wifi.yaml` contains the real Wi-Fi key
  and is ignored by Git. There are no full machine-config snapshots pinning old
  Kubernetes component images.
- `secrets/secrets.yaml` holds the cluster CA/private keys and encryption
  secrets. Treat it as full administrator access; keep a separate encrypted
  backup. **Do not regenerate it for an existing cluster.**
- `secrets/talosconfig` and `secrets/kubeconfig` are administrator client configs.
- `bin/topf` and `bin/talosctl` are the compatible Apple Silicon binaries.
  Stock TOPF does not understand this port's `WifiConfig`.
- `tools.sha256` and `toolchain.json` identify the supplied tools. Check the
  hashes against a trusted copy from the person handing over the folder.
- `output/` is generated full configuration, including secrets; it is ignored.

Existing etcd snapshots and recovery artifacts stay with the owner's private
backups. Hand over a recent etcd snapshot and the known-good pi5.7 installer/boot
artifacts separately, along with access to the backup location. A CA bundle is
not an etcd or application-data backup.

## First use on an Apple Silicon Mac

Install `kubectl` (`brew install kubectl` if Homebrew is already installed), then
open Terminal in this folder. Connect the Mac to the home network; the cluster
is not exposed to the internet. The supplied tools require no build VM or Go
installation for day-to-day management.

```sh
chmod +x manage bin/topf bin/talosctl
./manage verify-tools
./manage credentials
./manage render
./manage status
./manage health
./manage plan
```

`credentials` creates fresh client certificates using the **existing** CA; it
does not rotate cluster secrets or modify a node. `render` checks both generated
configs locally. `plan` previews changes without applying them: exit code 0 means
no changes, 2 means a diff needs review, and other failures need investigation.
The helper sets paths only for its own process, so it does not change another
cluster's global kubectl or Talos context. It works after moving this folder.
Its health command targets raspberry1 at `192.168.178.31`; update that address
in `manage` too if deliberately changing the control-plane address.

## Normal maintenance

```sh
./manage status
./manage kubectl get pods -A
./manage health
```

For applications use `./manage kubectl ...`, or set `KUBECONFIG` to the absolute
path of this folder's `secrets/kubeconfig` for Helm or other Kubernetes tools.
Avoid changing the node roles or network addresses during routine maintenance.

For an intentional Talos configuration change, edit the small YAML patches,
then render and preview. Apply to one node first:

```sh
./manage render
./manage plan
./manage apply raspberry2
./manage health
./manage apply raspberry1
./manage plan
```

TOPF asks for confirmation if there is a change. The helper uses `no-reboot`,
which refuses a change requiring reboot; plan those separately. Only apply to
raspberry1 after raspberry2 is healthy. Do not add plaintext secrets to Git or
remove Wi-Fi to make a validation error disappear.

## Backups, OS upgrades and resets

From this folder, explicitly select the control plane for an etcd snapshot:

```sh
export TALOSCONFIG="$PWD/secrets/talosconfig"
export KUBECONFIG="$PWD/secrets/kubeconfig"
umask 077
mkdir -p secrets/backups
bin/talosctl -e 192.168.178.31 -n 192.168.178.31 etcd snapshot \
  "secrets/backups/etcd-$(date +%Y%m%d-%H%M%S).snapshot"
```

Copy snapshots to protected off-device storage and back up application volumes
separately. Read [the operations runbook](../../docs/runbook.md) in the full
`talos-pi5-wifi` repository before an upgrade or reset. A standalone copy of this
folder should be accompanied by that repository's docs.

The installer digest in `patches/all/00-install.yaml` identifies the tested public
OCI archive. The GHCR location is the intended publication path, **not a claim
that the package has been published**. The initial upgrade used a temporary
LAN cache of that exact archive. Before another install/upgrade, make the public
installer available through an accessible registry/cache and verify its digest.
Do not substitute a stock Talos image or treat `topf apply` as an OS upgrade.

For worker OS upgrades through `talosctl`, use raspberry1 as the API endpoint
and raspberry2 as the target (`-e 192.168.178.31 -n 192.168.178.110`) so the client
can fetch the control-plane kubeconfig for draining. Use `--reboot-mode=powercycle`,
wait for readiness, and check the actual server version afterwards. If an upgrade
installs successfully but fails at the drain step, do not rerun installation into
a pending trial: finish the drain, reboot the staged candidate, then verify and
uncordon the worker. The handoff notes/validation record describe the tested case.

**Do not use `topf reset` for this setup.** It wipes STATE/Wi-Fi even with
`--full=false`. Use the documented EPHEMERAL-only reset when retaining Wi-Fi.
Resetting raspberry1 destroys the only etcd database. Do not run `bootstrap`
except when deliberately creating a new empty cluster or following recovery.

For Kubernetes upgrades, use `bin/talosctl upgrade-k8s` against raspberry1,
following supported version transitions; then update `kubernetesVersion` in
`topf.yaml`, render and preview so future applies retain the new version.

## If something stops responding

Check power, SSD connection and Wi-Fi placement first. Keep antennas away from
SSDs/cables. Check that the Mac is on the correct LAN, then retry status/health.
A reboot may take several minutes while time sync and certificates recover.
For an OS trial allow the watchdog/fallback window described in the runbook;
do not repeatedly power-cycle or reset the node as a connectivity fix.

Keep this repository's [TOPF build guide](../../docs/topf.md) for rebuilding the
custom management binary. Refresh the supplied tools and their hashes after
changing the Talos base. The runtime image, this configuration, and the toolchain
are separate versioned inputs; changing one does not automatically update the
others.
