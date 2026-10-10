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
printf 'talos.platform=metal talos.rpi5.ab=1 talos.rpi5.slot=A\n' > "$work/cmdline"
"$runtime" run --rm --privileged --network=none -v /dev:/dev \
  -v "$work/cmdline:/proc/cmdline:ro" "$image" install \
  --disk "$loop" --platform metal --arch arm64 2>&1 | tee "$work/install.log"
mkdir "$work/boot"
mount -o ro "${loop}p1" "$work/boot"
for name in Image initramfs.xz bcm2712d0-rpi-5-b.dtb overlays/disable-v3d.dtbo; do
  test -s "$work/boot/talos/A/$name"
done
grep -qx 'raspberrypi5-d0-tryboot-v2' "$work/boot/talos-rpi5-direct"
grep -qx 'kernel=talos/A/Image' "$work/boot/config.txt"
grep -q 'talos.rpi5.wifi_no_ps=1' "$work/boot/talos/A/cmdline.txt"
if grep -q 'talos.rpi5.test_timeout' "$work/boot/talos/A/cmdline.txt"; then
  echo 'Permanent installer unexpectedly enabled a reboot watchdog' >&2
  exit 1
fi
sha256sum "$work/boot/talos/A/Image" "$work/boot/talos/A/initramfs.xz" "$work/boot/talos/A/bcm2712d0-rpi-5-b.dtb" > "$work/boot.sha256"
if [[ -n ${EXPORT_INITIAL_BOOT:-} ]]; then
  test ! -e "$EXPORT_INITIAL_BOOT"
  tar -C "$work/boot" -cf "$EXPORT_INITIAL_BOOT" config.txt talos-rpi5-direct talos
fi
umount "$work/boot"
sync
# STATE/EPHEMERAL normally appear on first boot. Model them here with seeded
# partitions so the offline upgrade can prove it leaves real data bytes intact.
printf 'size=100MiB, type=linux, name=STATE\nsize=128MiB, type=linux, name=EPHEMERAL\n' | sfdisk --append "$loop"
udevadm settle
dd if=/dev/urandom of="${loop}p3" bs=1M count=1 conv=notrunc status=none
dd if=/dev/urandom of="${loop}p4" bs=1M count=1 conv=notrunc status=none
# Upgrade must preserve the active slot, GPT and cluster-data partitions.
dd if="$loop" of="$work/gpt-before" bs=1M count=1 status=none
sha256sum "${loop}p3" "${loop}p4" > "$work/data-before.sha256"
"$runtime" run --rm --privileged --network=none -v /dev:/dev \
  -v "$work/cmdline:/proc/cmdline:ro" "$image" install \
  --disk "$loop" --platform metal --arch arm64 --upgrade > "$work/upgrade.log" 2>&1
mount -o ro "${loop}p1" "$work/boot"
sha256sum -c "$work/boot.sha256"
grep -qx 'kernel=talos/A/Image' "$work/boot/config.txt"
grep -qx 'kernel=talos/B/Image' "$work/boot/tryboot.txt"
grep -qx 'kernel_watchdog_timeout=600' "$work/boot/tryboot.txt"
grep -q '"slot":"B"' "$work/boot/talos-pending.json"
test -s "$work/boot/talos/B/manifest.json"
umount "$work/boot"
dd if="$loop" of="$work/gpt-after" bs=1M count=1 status=none
cmp "$work/gpt-before" "$work/gpt-after"
sha256sum -c "$work/data-before.sha256"
# A second upgrade cannot overwrite the pending slot or change any disk byte.
before=$(sha256sum "$work/disk.img")
if "$runtime" run --rm --privileged --network=none -v /dev:/dev \
  -v "$work/cmdline:/proc/cmdline:ro" "$image" install \
  --disk "$loop" --platform metal --arch arm64 --upgrade > "$work/rejected.log" 2>&1; then
  echo 'Unexpected overwrite of pending trial' >&2
  exit 1
fi
grep 'trial is already pending' "$work/rejected.log"
test "$before" = "$(sha256sum "$work/disk.img")"
# Legacy disks also fail closed before any write.
mount "${loop}p1" "$work/boot"
printf 'raspberrypi5-d0-direct-v1\n' > "$work/boot/talos-rpi5-direct"
sync
umount "$work/boot"
before=$(sha256sum "$work/disk.img")
if "$runtime" run --rm --privileged --network=none -v /dev:/dev \
  -v "$work/cmdline:/proc/cmdline:ro" "$image" install \
  --disk "$loop" --platform metal --arch arm64 --upgrade > "$work/legacy.log" 2>&1; then
  echo 'Unexpected legacy-layout upgrade' >&2
  exit 1
fi
grep 'one-time A/B migration' "$work/legacy.log"
test "$before" = "$(sha256sum "$work/disk.img")"
echo 'Initial install and staged upgrade passed; active slot, GPT and cluster data preserved; pending and legacy upgrades rejected without writes.'
