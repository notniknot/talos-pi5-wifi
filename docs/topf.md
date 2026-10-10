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
  redundant list patches, the outputs matched the saved configs
  structurally. After moving raspberry1 closer to the repeater, a live
  `apply --dry-run` reached both nodes. It returned exit code 2 for document
  reordering; comparing the rendered and live configs by `(kind, name)` confirmed
  identical settings on both nodes. After the final LAN-only reset, both nodes
  use fresh TOPF-generated configurations: live dry-run and no-change apply both
  return exit code 0. Applying a changed configuration through TOPF, and TOPF's
  upgrade/reset operations, have not been hardware-tested here.
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

To refresh an Apple Silicon handoff, copy this binary and the matching custom
client into `clusters/raspberry-pi/bin/` as `topf` and `talosctl` with executable
permissions. Regenerate `tools.sha256` there and update `toolchain.json` only
after validating the new tools against the saved configuration and live preview.

The extra replacements come from the prepared Talos modules' `go.mod` files;
Go does not inherit dependency-module replacements automatically. When porting
to another Talos base, review these replacements and the TOPF API compatibility,
update the version label, and rerun offline rendering/validation. Keep the build's
`go.mod`/`go.sum` and source pins with your local build records. This recipe is
verified for the versions above; it is not a promise that every future TOPF and
Talos version will compile together.

## Current cluster configuration and handoff

Use [clusters/raspberry-pi](../clusters/raspberry-pi/README.md) as the source of
truth for this cluster. It contains `topf.yaml`, minimal shared patches and a
portable `manage` helper. Both nodes run pi5.7; raspberry1 is the control plane,
raspberry2 is the worker, and KubeSpan is disabled on this LAN.

The earlier `private/topf-raspberry-pi` snapshot import belongs to the old cluster
identity. Do not apply it or import its secrets after the final reset. Current
secrets live in `clusters/raspberry-pi/secrets/`, and the Wi-Fi patch is
`clusters/raspberry-pi/patches/all/90-wifi.yaml`; both are ignored by Git. Restore
these from a trusted private handoff, rather than generating new cluster secrets.

From the repository root:

```sh
clusters/raspberry-pi/manage verify-tools
clusters/raspberry-pi/manage credentials
clusters/raspberry-pi/manage render
clusters/raspberry-pi/manage plan
```

`credentials` regenerates client certificates from the existing CA, without
changing the cluster. Rendered configs in `output/` contain secrets too. The
helper refuses to run if the secrets bundle or Wi-Fi patch is missing, preventing
accidental creation of a new cluster identity during ordinary maintenance.

TOPF merges `all/`, then the role directory (`control-plane/` or `worker/`), then
`node/<hostname>/`, in lexical filename order within each directory. See the
[upstream configuration model](https://postfinance.github.io/topf/main/configuration-model/).
This setup uses small shared patches and a hostname template. It does not copy
full generated configs into per-node patches, so old component images and list
entries cannot silently override future generated defaults.

After reviewing an intentional change:

```sh
clusters/raspberry-pi/manage render
clusters/raspberry-pi/manage plan
clusters/raspberry-pi/manage apply raspberry2
clusters/raspberry-pi/manage health
clusters/raspberry-pi/manage apply raspberry1
```

Apply uses normal TOPF confirmation and `no-reboot`; changes requiring reboot
must be planned separately. A plan exits 2 when differences are found and 0 for
no changes. Stop on certificate/schema/connectivity errors. Do not use
`--auto-bootstrap` on the existing cluster, remove Wi-Fi to bypass a validation
error, or configure `machine.install` alongside `UnattendedInstallConfig`.

For direct custom-client commands, set the paths from [the operations runbook](runbook.md).
Keep the installer override: TOPF's Image Factory default lacks this port. Do
not use `topf upgrade` or `topf reset` for this setup; use the tested custom-client
procedures with explicit targets instead.

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

After it succeeds, set `kubernetesVersion` in `clusters/raspberry-pi/topf.yaml`
to match, render, and preview both nodes until no version downgrade is proposed.
The current patches do not pin Kubernetes component images. If you add such
per-node overrides later, update them along with the top-level version.

Use `clusters/raspberry-pi/manage credentials` to refresh client configs privately.
The helper does not modify global contexts. TOPF's multi-node talosconfig selects
all nodes by default; always pass a single `-n` for destructive `talosctl`
operations. Use a control-plane endpoint for worker upgrades that drain workloads.
