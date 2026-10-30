#!/usr/bin/env bash
# Bangun boot.img OpenWrt UTUH untuk mido (Redmi Note 4, msm8953), berbasis initramfs.
# Hasil: boot-openwrt.img  →  fastboot boot boot-openwrt.img
#
# Pemakaian:  ./build-openwrt.sh [OPENWRT_VERSION] [KERNEL_VERSION]
set -euo pipefail

OWRT_VER="${1:-24.10.5}"
KVER="${2:-6.11.1-postmarketos-qcom-msm8953}"
GHADIR="$(cd "$(dirname "$0")" && pwd)"
ART="$GHADIR/out-artifact"                 # Image.gz-dtb + modules-*.tar.gz dari CI
STAGE="${STAGE:-/tmp/stage}"
ROOTFS_TAR="/tmp/owrt-armsr-rootfs.tar.gz"
ROOTFS_URL="https://downloads.openwrt.org/releases/${OWRT_VER}/targets/armsr/armv8/openwrt-${OWRT_VER}-armsr-armv8-rootfs.tar.gz"
OUT="${OUT:-$GHADIR/boot-openwrt.img}"

[ -f "$ART/Image.gz-dtb" ] || { echo "ERROR: $ART/Image.gz-dtb tidak ada (jalankan CI dulu)"; exit 1; }

# 1. rootfs OpenWrt
[ -f "$ROOTFS_TAR" ] || curl -fL -o "$ROOTFS_TAR" "$ROOTFS_URL"
rm -rf "$STAGE"; mkdir -p "$STAGE"
tar xzf "$ROOTFS_TAR" -C "$STAGE"

# 2. overlay (init procd, config network/dhcp/firewall, service gadget USB, patch jail)
cp -a "$GHADIR/overlay/." "$STAGE/"

# 3. modul kernel mido (flatten path)
if [ -f "$ART/modules-${KVER}.tar.gz" ]; then
    mkdir -p "$STAGE/lib/modules/$KVER"
    tar xzf "$ART/modules-${KVER}.tar.gz" -C "$STAGE/lib/modules/$KVER" --strip-components=1 2>/dev/null || \
      tar xzf "$ART/modules-${KVER}.tar.gz" -C "$STAGE/lib/modules/$KVER"
fi

# 4. aktifkan service
chmod +x "$STAGE/init" "$STAGE/etc/init.d/mido-usb" "$STAGE/etc/init.d/mido-debug"
ln -sf ../init.d/mido-usb   "$STAGE/etc/rc.d/S15mido-usb"
ln -sf ../init.d/mido-debug "$STAGE/etc/rc.d/S95mido-debug"
rm -f "$STAGE/etc/rc.d/S35odhcpd" "$STAGE/etc/rc.d/K85odhcpd"   # odhcpd tak perlu
chmod 600 "$STAGE/etc/shadow"; chmod 700 "$STAGE/root"

# 5. initramfs (owner root:root WAJIB — kalau bukan, dropbear tak bisa baca /etc/shadow)
cd "$STAGE"
find . | cpio -o -H newc --owner 0:0 --quiet 2>/dev/null | gzip -9 > /tmp/initramfs-openwrt.cpio.gz

# 6. boot.img
cd "$ART"
python3 "$GHADIR/tools/mkbootimg.py" \
  --kernel Image.gz-dtb --ramdisk /tmp/initramfs-openwrt.cpio.gz \
  --cmdline "console=tty0 loglevel=7 panic=10 ramoops.mem_address=0x9ff00000 ramoops.mem_size=0x200000" \
  --base 0x80000000 --kernel_offset 0x00008000 --ramdisk_offset 0x01000000 \
  --tags_offset 0x00000100 --pagesize 2048 --header_version 0 --output "$OUT"
echo "OK -> $OUT"
echo "flash: fastboot boot $OUT"
