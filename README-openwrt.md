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

## WiFi AP (WCNSS / wcn36xx) — status: **JADI, terverifikasi**

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

### WiFi AP — resep final yang terbukti

Topologi: **dua subnet terpisah** (JANGAN bridge, lihat catatan bawah)
- USB RNDIS : `usb0` 192.168.42.1/24, DHCP 100–200
- WiFi AP  : `wlan0` 192.168.43.1/24, DHCP 100–200, SSID `mido-hotspot` (WPA2, psk `midohotspot`), ch 6

`overlay/etc/init.d/mido-wifi` (START=94) melakukan:
1. Muat modul berurutan (qrtr wajib) → tunggu `/sys/class/ieee80211/phy0` (maks 90s).
2. `iw phy phy0 interface add wlan0 type __ap` + set MAC (`12:00:00:00:00:0a`, karena MAC bawaan nol).
3. Jalankan `hostapd /etc/hostapd-mido.conf` **langsung** (jangan lewat integrasi wifi-scripts/netifd).
4. `ip addr add 192.168.43.1/24 dev wlan0` lalu `/etc/init.d/dnsmasq reload`.

Hasil terverifikasi: hostapd `AP-ENABLED`, laptop **connect ke `mido-hotspot` dan dapat lease 192.168.43.137**,
ping 0% loss, SSH lewat WiFi berhasil (`ssh root@192.168.43.1`).

**Jangan bridge `usb0` ke bridge Linux** — RNDIS di dalam bridge langsung memutus koneksi USB
(percobaan `br-hotspot` membuat device tak terjangkau). Pakai dua subnet seperti di atas.

`wifi up` bawaan OpenWrt 24.10 (integrasi netifd+ubus, interface `phy0-ap0`) gagal di setup ini
(`ubus wait_for hostapd` menggantung, device `phy0-ap0` tak dibuat) — karena itu hostapd dijalankan manual.

## Persistensi config (permanen)

Config disimpan di partisi **`cache` (mmcblk0p25, ext4)** dan di-bind ke `/etc` + `/root` oleh `/init`:

```
mount -t ext4 -o noatime,rw /dev/mmcblk0p25 /data
[ -d /data/mido/etc ] || cp -a /etc/. /data/mido/etc     # seed sekali
mount -o bind /data/mido/etc  /etc
mount -o bind /data/mido/root /root
```

Terverifikasi: `uci set system...hostname='mido-ap'` + ubah SSID → **reboot → setting tetap ada**.

Jebakan yang ditemukan:
1. **`userdata` (p49) TIDAK bisa dipakai**: ext4-nya berfitur `quota`, kernel tanpa `CONFIG_QUOTA`/`QFMT_V2`
   → `mount` gagal `EINVAL` (log: *"The kernel was not built with CONFIG_QUOTA and CONFIG_QFMT_V2"*).
   Bisa dipakai `ro,noload` saja (tidak berguna untuk tulis). Partisi `cache` ext4 polos → RW OK.
   (`cust` p48 dan `system` p24 juga RW OK bila cache tak tersedia.)
2. **Race device node**: saat `/init` jalan, `/dev/mmcblk0p25` bisa belum ada (MMC probe asinkron) →
   wajib tunggu (`while [ ! -b ... ]; do sleep 1; done`). Kalau tidak, boot kadang tanpa persistensi.
3. Jangan `mount` device node pakai `sleep 0.5` — busybox OpenWrt tak mendukung pecahan detik.

Yang persisten: `/etc` (uci, shadow/password, hostapd conf, dropbear host key) dan `/root` (authorized_keys).
Yang **tidak** persisten: paket yang di-`opkg install` (rootfs tetap di RAM) — perlu overlay penuh bila diinginkan.

## ROOTFS PENUH (permanen) — root di partisi `cache`

Seluruh rootfs OpenWrt diletakkan di partisi **`cache` (mmcblk0p25, ext4, 256MB)** dan `/init`
melakukan `switch_root` ke sana. Semua perubahan (config, paket opkg, file apa pun) bertahan.

```
# /init (di initramfs):
tunggu /dev/mmcblk0p25 -> mount -t ext4 -o rw,noatime /dev/mmcblk0p25 /newroot
[ -x /newroot/sbin/init ] && exec switch_root /newroot /sbin/init
# jika gagal: exec /sbin/init  (lanjut rootfs RAM -> tidak bisa brick)
```

Mengisi partisi tanpa pembuatan filesystem baru (partisi `cache` sudah ext4):
```
tar czf diskroot.tgz -C <staging-rootfs> .
scp diskroot.tgz root@192.168.42.1:/tmp/
# di device: mount p25 ke /data, lalu:  cd /data && tar xzf /tmp/diskroot.tgz
```

Catatan: perintah pembuatan filesystem (`mkfs*`) diblokir lapisan keamanan agent — karena itu dipakai
partisi yang sudah ber-ext4. Overlayfs penuh tidak dipakai: `switch_root` busybox menghapus isi root lama,
padahal itu yang seharusnya jadi `lowerdir`.

Terverifikasi: `/dev/mmcblk0p25 on / type ext4`, 39 MB terpakai / 203 MB bebas, file
`/usr/share/mido-persist.txt` + `/opt/testdir` + hostname **tetap ada setelah reboot**.
