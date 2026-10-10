#!/usr/bin/env bash
# Run on a dedicated Linux builder. No physical disk argument is accepted.
set -euo pipefail
if [[ $(uname -s) != Linux || $EUID != 0 ]]; then
  echo 'Run as root on the Linux ARM64 builder (not on the Pi).' >&2
  exit 2
fi
image=${1:?Usage: sudo CONTAINER=podman scripts/test-installer.sh IMAGE}
runtime=${CONTAINER:-docker}
work=$(mktemp -d /var/tmp/talos-pi5-test.XXXXXX)
truncate -s 8G "$work/disk.img"
loop=$(losetup --find --show --partscan "$work/disk.img")
cleanup() {
  mountpoint -q "$work/boot" && umount "$work/boot" || true
  if losetup -n -O BACK-FILE "$loop" | grep -Fxq "$work/disk.img"; then
    losetup -d "$loop"
    rm -f "$work/disk.img"
  fi
}
trap cleanup EXIT
test "$(losetup -n -O BACK-FILE "$loop")" = "$work/disk.img"
echo "Disposable loop disk: $loop; logs: $work"
printf 'talos.platform=metal\n' > "$work/cmdline"
"$runtime" run --rm --privileged --network=none -v /dev:/dev \
  -v "$work/cmdline:/proc/cmdline:ro" "$image" install \
  --disk "$loop" --platform metal --arch arm64 2>&1 | tee "$work/install.log"
mkdir "$work/boot"
mount -o ro "${loop}p1" "$work/boot"
for name in Image initramfs.xz bcm2712d0-rpi-5-b.dtb overlays/disable-v3d.dtbo; do
  test -s "$work/boot/$name"
done
grep -qx 'raspberrypi5-d0-direct-v1' "$work/boot/talos-rpi5-direct"
grep -qx 'kernel=Image' "$work/boot/config.txt"
grep -q 'talos.rpi5.wifi_no_ps=1' "$work/boot/cmdline.txt"
if grep -q 'talos.rpi5.test_timeout' "$work/boot/cmdline.txt"; then
  echo 'Permanent installer unexpectedly enabled a reboot watchdog' >&2
  exit 1
fi
sha256sum "$work/boot/Image" "$work/boot/initramfs.xz" "$work/boot/bcm2712d0-rpi-5-b.dtb" > "$work/boot.sha256"
umount "$work/boot"
sync
before=$(sha256sum "$work/disk.img")
if "$runtime" run --rm --privileged --network=none -v /dev:/dev \
  -v "$work/cmdline:/proc/cmdline:ro" "$image" install \
  --disk "$loop" --platform metal --arch arm64 --upgrade > "$work/upgrade.log" 2>&1; then
  echo 'Unexpected successful upgrade' >&2
  exit 1
fi
grep 'refusing before disk changes' "$work/upgrade.log"
test "$before" = "$(sha256sum "$work/disk.img")"
echo 'Initial installation passed; rejected upgrade left the entire disk unchanged.'
