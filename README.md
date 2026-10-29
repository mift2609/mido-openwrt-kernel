# mido-openwrt-kernel

Mainline kernel 6.x for **Xiaomi Redmi Note 4** (`mido`, MSM8953 / Snapdragon 625, arm64),
built for OpenWrt native + portable WiFi hotspot.

Built in GitHub Actions — no local toolchain needed.

## What it produces (artifact `mido-kernel`)

| File | Purpose |
|---|---|
| `boot-mido.img` | Android boot image: kernel + initramfs (USB RNDIS 192.168.1.1, telnet, dropbear) |
| `Image.gz-dtb` | kernel + appended mido DTB |
| `Image.gz` | raw kernel |
| `msm8953-xiaomi-mido.dtb` | device tree |
| `modules-<krel>.tar.gz` | `/lib/modules/<krel>` layout (WCN36xx, USB gadget, nf_tables, squashfs…) |
| `initramfs.cpio.gz` | early network initramfs |
| `config-<tag>` | kernel .config used |
| `openwrt-rootfs.tar.gz` | OpenWrt 23.05.5 armsr/armv8 rootfs |

## Required hardware state

- bootloader unlocked (UBL)
- `lk2nd-msm8953.img` booted via `fastboot boot` — stock aboot **cannot** boot mainline arm64
- backups of `boot` / `persist` / `modem` / `efs` made before any flash

## Run

```bash
gh workflow run build.yml -f kernel_tag=v6.12.0-r2
gh run watch
gh run download -n mido-kernel -D ~/mido-openwrt/out
```

## Boot test (no flash)

```bash
fastboot boot lk2nd-msm8953.img   # secondary bootloader
fastboot boot boot-mido.img       # then the kernel
ping 192.168.1.1
telnet 192.168.1.1 23
```

## Sources

- kernel: [`msm8953-mainline/linux`](https://github.com/msm8953-mainline/linux) tag `v6.12.0-r2`
- base config: postmarketOS `linux-postmarketos-qcom-msm8953`
- rootfs: OpenWrt 23.05.5 `armsr/armv8`
