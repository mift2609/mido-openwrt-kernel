# mido — OpenWrt UTUH di Redmi Note 4 (msm8953)

Hotspot portable: **kernel mainline 6.11.1 (pmOS msm8953) + OpenWrt 24.10.5 armsr/armv8 utuh**
(procd + ubus + netifd + dnsmasq + firewall/nftables + dropbear + LuCI), dijalankan sebagai
**initramfs** lewat `fastboot boot` (tanpa flash partisi — aman, non-persisten).

## Status terverifikasi

| Layanan | Hasil |
|---|---|
| procd (PID 1) / ubus / netifd | ✅ jalan, `ubus list` = 25 objek |
| USB RNDIS gadget (`usb0`) | ✅ 192.168.42.1/24 via UCI |
| DHCP server (dnsmasq) | ✅ host dapat lease 192.168.42.164 |
| SSH (dropbear :22) | ✅ `ssh root@192.168.42.1`, password `toor` |
| LuCI (uhttpd :80) | ✅ HTTP 200 |
| NAT / firewall (nftables) | ✅ `nft list ruleset` OK, zone `usb` masq |
| WiFi AP (wcn36xx) | ❌ modul belum dimuat + firmware `/lib/firmware/wlan` belum ada |

## Cara pakai

```bash
# 1. build (butuh out-artifact/Image.gz-dtb + modules-*.tar.gz dari CI)
./build-openwrt.sh                # -> boot-openwrt.img

# 2. hp ke fastboot (Power+Vol Bawah), lalu
fastboot boot boot-openwrt.img

# 3. host: DHCP otomatis (atau set manual 192.168.42.2/24)
ssh root@192.168.42.1             # password: toor
#   LuCI:  http://192.168.42.1/
#   debug: http://192.168.42.1:8080/dbg.txt   (tinynet)
```

## Struktur

- `overlay/init` — `/init` initramfs: mount proc/sys/dev, `export INITRAMFS=1`, `exec /sbin/init` (procd).
- `overlay/etc/config/{network,dhcp,firewall}` — `usb0` static 192.168.42.1, DHCP 100–200, zone masq.
- `overlay/etc/init.d/mido-usb` — setup gadget RNDIS configfs (START=15, sebelum network).
- `overlay/etc/init.d/mido-debug` — dump diagnostik ke `/tmp/dbg.txt` + tinynet http:8080/shell:23.
- `overlay/lib/functions/procd.sh` — `_procd_add_jail*` dinonaktifkan (pivot_root gagal di initramfs).

## Dua jebakan penting (WAJIB diingat)

1. **Owner file harus `root:root`.** `cpio ... --owner 0:0`. Kalau file tetap milik uid 1000,
   `/root` jadi tak terbaca dan dropbear gagal.
2. **`getspnam()` GAGAL di musl OpenWrt** (pesan `passwd: no record of root in /etc/shadow`).
   Akibatnya dropbear & `passwd` jatuh ke `/etc/passwd`. **Taruh hash password di field kedua
   `/etc/passwd`** (bukan hanya `/etc/shadow`) → autentikasi password baru berhasil.
3. **procd ujail tidak jalan di initramfs** (`pivot_root: Invalid argument`) → dnsmasq crash-loop.
   Perbaikan: `_procd_add_jail()` → `return 0` di `lib/functions/procd.sh`.

## WiFi AP (WCNSS / wcn36xx) — status: phy hidup, AP belum tuntas

Urutan muat modul (wajib, kalau tidak banyak "Unknown symbol"):
```
libarc4 rfkill cfg80211 mac80211 qrtr qrtr-smd mdt_loader qcom_common \
qcom_pil_info qmi_helpers qcom_sysmon qcom_wcnss_pil wcn36xx
```
**`qrtr` + `qrtr-smd` wajib** meski `depmod` tidak menyebutnya: `qcom_sysmon` memanggil
`qmi_handle_init()` → `sock_create_kern(AF_QIPCRTR)`. Tanpa itu: `failed to initialize qmi handle`
dan remoteproc langsung di-release.

Firmware (dari backup `persist`/`modem` HP):
- `/lib/firmware/wcnss.mdt` + `wcnss.b00…b12`
- `/lib/firmware/wlan/prima/{WCNSS_qcom_wlan_nv.bin,WCNSS_cfg.dat,WCNSS_wlan_dictionary.dat}`
- `/lib/firmware/regulatory.db` (paket OpenWrt `wireless-regdb`)

Terbukti: `remoteproc0: Booting fw image wcnss.mdt` → `is now up` → `wcn36xx` bind →
**`/sys/class/ieee80211/phy0` muncul**.

Skrip: `overlay/scripts/fetch-openwrt-wifi-pkgs.sh` (ambil hostapd-basic/wifi-scripts/iw/iwinfo/regdb),
`overlay/scripts/collect-wifi-modules.py` (closure modul + firmware ke staging),
`overlay/etc/init.d/mido-wifi` (muat modul → tunggu phy0 → `wifi config` → AP `mido-hotspot`).

Catatan boot: image besar bikin boot lambat (~50–60 s sampai layanan). Buang `.ko.gz` yang tak dipakai
(45 MB → 20 MB). Layar HP tetap gelap — itu normal, jangan dipakai sebagai indikator.
