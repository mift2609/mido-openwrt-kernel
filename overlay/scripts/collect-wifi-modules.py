#!/usr/bin/env python3
"""Susun firmware + closure modul WiFi untuk staging OpenWrt mido."""
import gzip, os, pathlib, shutil, subprocess, sys

KV = "6.11.1-postmarketos-qcom-msm8953"
STAGE = pathlib.Path("/tmp/stage")
SRC = STAGE / "lib" / "modules" / KV          # berisi *.ko.gz
MT = pathlib.Path("/tmp/modtree") / "lib" / "modules" / KV
FW_HOST = pathlib.Path("/home/qiiin/mido-openwrt/firmware")

# ---------- 1. firmware ----------
fw_files = []
wlan_dst = STAGE / "lib" / "firmware" / "wlan" / "prima"
wlan_dst.mkdir(parents=True, exist_ok=True)
(STAGE / "lib" / "firmware").mkdir(parents=True, exist_ok=True)

# wcnss.mdt + segmen b00..b12 dari mana saja di firmware/ (rekursif)
for p in FW_HOST.rglob("wcnss.*"):
    if p.is_file():
        shutil.copy2(p, STAGE / "lib" / "firmware" / p.name)
        fw_files.append(p.name)
# NV/cfg/dictionary -> /lib/firmware/wlan/prima/
for name in ("WCNSS_cfg.dat", "WCNSS_qcom_wlan_nv.bin", "WCNSS_wlan_dictionary.dat"):
    for p in FW_HOST.rglob(name):
        if p.is_file():
            shutil.copy2(p, wlan_dst / name)
            fw_files.append(f"wlan/prima/{name}")
            break
print("firmware:", sorted(set(fw_files)))

# ---------- 2. modul: gunzip ke modtree lalu depmod ----------
if MT.exists():
    shutil.rmtree(MT)
MT.mkdir(parents=True)
n = 0
for gz in SRC.rglob("*.ko.gz"):
    rel = gz.relative_to(SRC)
    dst = MT / rel.with_suffix("")          # buang .gz
    dst.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(gz, "rb") as f, open(dst, "wb") as o:
        shutil.copyfileobj(f, o)
    n += 1
print("modul gunzip:", n)

r = subprocess.run(["depmod", "-b", str(MT.parents[2]), KV], capture_output=True, text=True)
print("depmod rc:", r.returncode, r.stderr.strip()[:200])

# ---------- 3. closure dependensi ----------
depfile = MT / "modules.dep"
deps = {}
for line in depfile.read_text().splitlines():
    if ":" not in line:
        continue
    path, d = line.split(":", 1)
    deps[os.path.basename(path)] = [os.path.basename(x) for x in d.split()]

targets = ["wcn36xx.ko", "qcom_wcnss_pil.ko", "mac80211.ko", "cfg80211.ko", "rfkill.ko", "qrtr.ko", "qrtr-smd.ko"]
need, stack = set(), list(targets)
while stack:
    m = stack.pop()
    if m in need or m not in deps:
        continue
    need.add(m)
    stack.extend(deps[m])
print("closure:", len(need), sorted(need))

# ---------- 4. salin closure ke staging (ekstra .ko) ----------
copied = []
for ko in MT.rglob("*.ko"):
    if ko.name in need:
        rel = ko.relative_to(MT)
        dst = SRC / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ko, dst)
        copied.append(str(rel))
# modules.dep hasil filter
lines = []
for line in depfile.read_text().splitlines():
    if ":" not in line:
        continue
    path, d = line.split(":", 1)
    if os.path.basename(path) in need:
        keep = [x for x in d.split() if os.path.basename(x) in need]
        lines.append(path + ":" + (" " + " ".join(keep) if keep else ""))
(SRC / "modules.dep").write_text("\n".join(lines) + "\n")
(SRC / "modules.alias").write_text("")
print("dikopi:", len(copied))
print("modules.dep baris:", len(lines))
