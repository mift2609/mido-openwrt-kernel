#!/usr/bin/env bash
# Ambil paket WiFi OpenWrt (hostapd + wifi-scripts) untuk aarch64_generic, ekstrak ke /tmp/stage
set -eu
VER=24.10.5
ARCH=aarch64_generic
BASE="https://downloads.openwrt.org/releases/${VER}/packages/${ARCH}"
DL=/tmp/wpkg
STAGE=/tmp/stage
mkdir -p "$DL"

# index (base + packages)
for f in base packages; do
  [ -f /tmp/idx-$f.gz ] || curl -sfL -o /tmp/idx-$f.gz "$BASE/$f/Packages.gz"
done

PKGS="hostapd-basic hostapd-common wifi-scripts wireless-regdb iw iwinfo \
      ucode-mod-fs ucode-mod-nl80211 ucode-mod-rtnl ucode-mod-ubus ucode-mod-uloop ucode-mod-uci \
      libubox20240329 libnl-tiny1"

for p in $PKGS; do
  for feed in base packages; do
    fn=$(zcat /tmp/idx-$feed.gz 2>/dev/null | awk -v p="$p" 'BEGIN{RS=""} $0 ~ "^Package: "p"\n"{for(i=1;i<=split($0,a,"\n");i++) if(a[i] ~ /^Filename: /) print substr(a[i],11)}' | head -1)
    [ -n "$fn" ] && { FEED=$feed; break; }
  done
  if [ -z "${fn:-}" ]; then echo "SKIP $p (tidak ada di index)"; continue; fi
  out="$DL/$(basename "$fn")"
  [ -f "$out" ] || curl -sfL -o "$out" "$BASE/$FEED/$fn" || { echo "GAGAL unduh $p"; continue; }
  # ipk: bisa format tar.gz (debian-binary+data.tar.gz) atau ar
  d="$DL/x-$p"; rm -rf "$d"; mkdir -p "$d"
  if tar tzf "$out" >/dev/null 2>&1; then
    ( cd "$d" && tar xzf "$out" && tar xzf data.tar.gz -C "$STAGE" ) || { echo "GAGAL ekstrak $p"; continue; }
  else
    ( cd "$d" && ar x "$out" && tar xzf data.tar.gz -C "$STAGE" ) || { echo "GAGAL ekstrak $p"; continue; }
  fi
  echo "OK   $p -> $fn"
done
echo "--- selesai ---"
ls -l "$STAGE/usr/sbin/hostapd" "$STAGE/sbin/wifi" 2>/dev/null || true
