# TOPF on this Wi-Fi port

[TOPF](https://github.com/postfinance/topf) generates and applies Talos machine
configuration and exposes cluster lifecycle operations. It does not deploy
application Helm charts/manifests. Use it for the cluster's desired configuration,
the custom `talosctl` for OS upgrades/resets and orchestrated Kubernetes upgrades,
and Kubernetes tools for workloads.

## Compatibility findings

Checked on 2026-10-10:

- The installed Homebrew TOPF `0.6.1` embeds upstream Talos `v1.14.1`. An offline
  render with our Wi-Fi patch fails with `"WifiConfig" "v1alpha1": not registered`.
  Removing Wi-Fi from the desired config is not a fix: applying that incomplete
  config could disconnect the Pi.
- A local TOPF build at commit
  `232db62aef7b1e714106edbc62f8bf377f0498ec`, linked against this repository's
  patched Talos `v1.14.2` sources, successfully rendered both saved Pi configs.
  The custom client validated both outputs in strict metal mode. After removing
  redundant list patches described below, the outputs matched the saved configs
  structurally. After moving raspberry1 closer to the repeater, a live
  `apply --dry-run` reached both nodes. It returned exit code 2 for document
  reordering; comparing the rendered and live configs by `(kind, name)` confirmed
  identical settings on both nodes. No configuration was applied, and TOPF's
  mutating apply/upgrade/reset operations have not been hardware-tested here.
- TOPF generates an Image Factory installer by default. Override it explicitly
  with our custom installer for every node. Setting only `talosVersion` is
  insufficient.
- TOPF's current upgrade parser expects a factory-style `.../<schematic>:<version>`
  reference. Our repository name is not a schematic, and a digest-only reference
  does not fit that parser. Use the custom `talosctl upgrade` procedure in the
  [operations runbook](runbook.md), rather than relying on TOPF upgrade selection
  or repeatedly upgrading an already-current custom image. The parser was
  inspected [at this exact commit](https://github.com/postfinance/topf/blob/232db62aef7b1e714106edbc62f8bf377f0498ec/internal/cmd/upgrade/upgrade.go).
- **Do not use `topf reset` on these Wi-Fi-only installations.** Its default is a
  full-disk wipe; `--full=false` still wipes both STATE and EPHEMERAL, including
  Wi-Fi credentials. Use our EPHEMERAL-only reset when retaining connectivity.
  See [TOPF's reset documentation](https://postfinance.github.io/topf/main/commands/reset/).

## Build the compatible management client locally

Do not replace the Homebrew binary globally. Prepare this repository's Talos
sources with `python3 scripts/prepare.py` first. Go 1.27 or newer is needed by
this TOPF commit. The build downloads Go dependencies but does not contact or
modify either Pi.

From the repository root, use an unused destination:

```sh
git clone https://github.com/postfinance/topf.git _out/topf-pi5-source
git -C _out/topf-pi5-source checkout --detach 232db62aef7b1e714106edbc62f8bf377f0498ec
cd _out/topf-pi5-source
go mod edit \
  -replace github.com/siderolabs/talos=../../talos \
  -replace github.com/siderolabs/talos/pkg/machinery=../../talos/pkg/machinery \
  -replace github.com/mdlayher/ethtool=github.com/siderolabs/ethtool@v0.6.0-sidero \
  -replace github.com/coredns/coredns=github.com/siderolabs/coredns@v1.14.53 \
  -replace github.com/mdlayher/kobject=github.com/smira/kobject@v0.0.0-20240304111826-49c8d4613389 \
  -replace github.com/secure-io/siv-go=github.com/smira/siv-go@v0.0.0-20260706144621-2093d2730928 \
  -replace golang.zx2c4.com/wireguard/wgctrl=github.com/siderolabs/wgctrl-go@v0.0.0-20251029173431-c4fd5f6a4e72
go build -mod=mod -o ../topf-pi5 \
  -ldflags '-X main.version=232db62-pi5 -X github.com/siderolabs/talos/pkg/machinery/version.Tag=v1.14.2-pi5.7' \
  ./cmd/topf
cd ../..
export TOPF="$PWD/_out/topf-pi5"
"$TOPF" --version
```

The extra replacements come from the prepared Talos modules' `go.mod` files;
Go does not inherit dependency-module replacements automatically. When porting
to another Talos base, review these replacements and the TOPF API compatibility,
update the version label, and rerun offline rendering/validation. Keep the build's
`go.mod`/`go.sum` and source pins with your local build records. This recipe is
verified for the versions above; it is not a promise that every future TOPF and
Talos version will compile together.

## Adopt the existing cluster without changing its identity

The local working directory is `private/topf-raspberry-pi/`; an offline-validated
copy was prepared there during this runbook's creation. It has not been applied
to the cluster. The following steps show how to reproduce the import in a fresh
directory. Do not overwrite a maintained TOPF configuration with an old snapshot.

Set `TALOSCTL`, `TALOSCONFIG` and `KUBECONFIG` as in [the operations runbook](runbook.md).
Take fresh backups and confirm the saved full node configs describe the live
cluster before importing them. For raw `get machineconfig -o json` output, the
`spec` field is the complete YAML **string**; extract it into a private file,
not terminal output. Never import configs from the previous independent clusters.

```sh
umask 077
mkdir -p private/topf-raspberry-pi/node/raspberry1
mkdir -p private/topf-raspberry-pi/node/raspberry2
"$TALOSCTL" gen secrets \
  --from-controlplane-config private/raspberry-pi/raspberry1.yaml \
  --output-file private/topf-raspberry-pi/secrets.yaml
cp private/raspberry-pi/raspberry1.yaml private/topf-raspberry-pi/node/raspberry1/00-current.yaml
cp private/raspberry-pi/raspberry2.yaml private/topf-raspberry-pi/node/raspberry2/00-current.yaml
```

Importing the existing secrets preserves the cluster CA, tokens and encryption
material. Do not let TOPF generate new secrets for an existing cluster; stop if
it unexpectedly prompts to do so. `topf secrets` prints the bundle to stdout,
even with output redaction enabled.

Create `private/topf-raspberry-pi/topf.yaml`:

```yaml
clusterName: raspberry-pi
clusterEndpoint: https://192.168.178.31:6443
kubernetesVersion: 1.37.1
talosVersion: 1.14.2
secretsPath: secrets.yaml
nodes:
  - host: raspberry1
    ip: 192.168.178.31
    role: control-plane
  - host: raspberry2
    ip: 192.168.178.110
    role: worker
```

The imported full configs are a conservative starting point: they preserve
hostnames, Wi-Fi, KubeSpan/discovery, installer selection and cluster identity.
They also pin Kubernetes component versions, so they must later be updated along
with `kubernetesVersion`. TOPF's `host` field alone does **not** set a node's Talos
hostname; keep `HostnameConfig` in the patches.

Render without contacting the nodes:

```sh
export TOPFCONFIG="$PWD/private/topf-raspberry-pi/topf.yaml"
"$TOPF" render -o private/topf-raspberry-pi/rendered
"$TALOSCTL" validate --config private/topf-raspberry-pi/rendered/raspberry1.yaml --mode metal --strict
"$TALOSCTL" validate --config private/topf-raspberry-pi/rendered/raspberry2.yaml --mode metal --strict
```

Compare parsed YAML documents by `(kind, name)`, including all secret values,
locally without logging their contents. Whole-config strategic merge can append
list entries already present in generated defaults. In this cluster, the only
differences were identical duplicate entries in raspberry1's
`KubeAdmissionControlConfig` and `KubeEtcdEncryptionConfig`, and raspberry2's
`KubeAPIServerCAConfig`. Omitting those three documents from the corresponding
`00-current.yaml` patches let TOPF regenerate them from the imported secrets and
defaults, producing an exact structural match. Only do this after verifying that
the regenerated documents equal the originals; customized admission policies,
encryption configurations or extra trusted CAs must not be discarded.

Check the complete diff against live nodes before any apply:

```sh
"$TOPF" --nodes-filter '^raspberry2$' apply --dry-run
"$TOPF" --nodes-filter '^raspberry1$' apply --dry-run
```

Exit code `2` means changes were found; it is not a successful no-change adoption.
The initial live preview reported document reordering only; a private structural
comparison confirmed there were no setting changes. Check such diffs rather than
assuming every exit code 2 is harmless.
Stop on connectivity, schema or certificate errors. The first adoption should
have no unintended differences. Do not use `--auto-bootstrap` on this already
bootstrapped cluster. Avoid `--redact=false`; rendered files and private patch
files contain credentials regardless of terminal redaction.

## Routine configuration changes

TOPF merges `all/`, then the role directory (`control-plane/` or `worker/`), then
`node/<hostname>/`, with lexical filename order within each directory. See the
[upstream configuration model](https://postfinance.github.io/topf/main/configuration-model/).
While `node/*/00-current.yaml` remains a full baseline, it can override shared
patches: edit the relevant per-node file or add a later per-node patch. Do not
silently keep two competing sources of desired state.

As a separate reviewed cleanup, reduce the snapshots to only necessary overrides
and move common fields into `all/`, requiring an unchanged rendered result after
each step. Keep `secrets.yaml`, plaintext Wi-Fi and rendered configs private, or
use SOPS before putting configuration in a separate infrastructure repository.
The build repository must never receive plaintext cluster secrets.

Always retain these settings when reorganizing:

```yaml
apiVersion: v1alpha1
kind: HostnameConfig
auto: "off"
hostname: raspberry2 # raspberry1 in its own node patch
---
apiVersion: v1alpha1
kind: KubeSpanConfig
enabled: true
allowDownPeerBypass: false
---
apiVersion: v1alpha1
kind: UnattendedInstallConfig
installer:
  image: ghcr.io/notniknot/talos-pi5-wifi/installer@sha256:REPLACE_WITH_VERIFIED_DIGEST
provisioning:
  diskSelector:
    match: disk.dev_path == "/dev/sda"
  wipe: false
```

The digest is a placeholder, not an existing published image. Retain the existing
disk/bootloader settings too; this partial patch is not a full machine config.
Keep the `WifiConfig`, `LinkConfig`, `DHCPv4Config` and shared discovery identity
from the imported configs. Never configure legacy `machine.install` alongside
`UnattendedInstallConfig`.

After rendering and reviewing an intentional change, apply to one node first:

```sh
"$TOPF" --nodes-filter '^raspberry2$' apply --dry-run
"$TOPF" --nodes-filter '^raspberry2$' apply --mode=no-reboot
kubectl get nodes -o wide
"$TALOSCTL" -e 192.168.178.110 -n 192.168.178.110 get kubespanpeerstatuses
```

`no-reboot` rejects a change requiring reboot. If a reboot is actually needed,
plan that explicitly and choose `auto`/`staged` after reviewing the diff. Repeat
for raspberry1 only after the worker is healthy. Keep TOPF's normal confirmation
and readiness checks; do not bypass them to work around unreliable Wi-Fi.

## Kubernetes version upgrades

TOPF's own [Kubernetes upgrade guide](https://github.com/postfinance/topf/blob/232db62aef7b1e714106edbc62f8bf377f0498ec/docs/kubernetes-upgrade.md)
recommends the orchestrated `talosctl upgrade-k8s` path. Changing
`kubernetesVersion` and running `topf apply` does not provide equivalent version
skew and rollout checks.

Back up etcd and application data, verify Talos supports the target Kubernetes
version, read the target's release notes and follow supported sequential minor
upgrades. Inspect the plan before running it:

```sh
K8S_VERSION=1.37.2 # Example only: choose an available, supported target.
"$TALOSCTL" -e 192.168.178.31 -n 192.168.178.31 upgrade-k8s --to "$K8S_VERSION" --dry-run
"$TALOSCTL" -e 192.168.178.31 -n 192.168.178.31 upgrade-k8s --to "$K8S_VERSION"
kubectl get nodes -o wide
```

After it succeeds, set `kubernetesVersion` in `topf.yaml` to match **and refresh
the component-version fields in the imported per-node baselines from the live
configs**. Render and dry-run both nodes until no version downgrade is proposed.
Only changing `topf.yaml` while retaining old component image/kubelet fields in
the later patches can revert an upgrade.

Generate client configs privately when needed; these files are not merged into
your global contexts automatically:

```sh
umask 077
"$TOPF" talosconfig > private/topf-raspberry-pi/talosconfig
"$TOPF" kubeconfig > private/topf-raspberry-pi/kubeconfig
```

TOPF's generated multi-node talosconfig selects all nodes by default. Always
pass a single `-n` for destructive `talosctl` operations. Keep the original
private client configs until the generated replacements have been tested.
