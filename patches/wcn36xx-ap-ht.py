#!/usr/bin/env python3
"""
Tambalan: wcn36xx mode AP dikonfigurasi sebagai NON-HT -> TX mentok legacy 6 Mbit/s.

Sebab: wcn36xx_smd_set_bss_ht_params() hanya mengisi bss_params->ht kalau argumen
`sta` non-NULL, sedangkan mode AP memanggil wcn36xx_smd_config_bss(wcn, vif, NULL, ...).
Akibatnya bss_params->ht = 0 dan firmware tidak pernah memakai rate MCS untuk TX.

Perbaikan: saat sta == NULL dan vif beroperasi sebagai AP/IBSS/MESH, ambil kapabilitas
HT dari phy sendiri (wiphy->bands[chan->band]->ht_cap) sehingga bss_params->ht = 1.

Dijalankan dari akar source kernel. Gagal keras (exit != 0) kalau pola tidak ketemu,
supaya build tidak diam-diam menghasilkan kernel tanpa tambalan.
"""
import re
import sys

PATH = "drivers/net/wireless/ath/wcn36xx/smd.c"

NEW_FUNC = r'''static void wcn36xx_smd_set_bss_ht_params(struct wcn36xx *wcn,
					  struct ieee80211_vif *vif,
					  struct ieee80211_sta *sta,
					  struct wcn36xx_hal_config_bss_params *bss_params)
{
	const struct ieee80211_ht_cap *ht_cap = NULL;
	struct ieee80211_supported_band *band;
	unsigned long caps;

	if (sta && sta->deflink.ht_cap.ht_supported) {
		ht_cap = &sta->deflink.ht_cap;
	} else if (vif->type == NL80211_IFTYPE_AP ||
		   vif->type == NL80211_IFTYPE_ADHOC ||
		   vif->type == NL80211_IFTYPE_MESH_POINT) {
		/*
		 * Mode AP: config_bss dipanggil dengan sta == NULL. Tanpa cabang ini
		 * bss_params->ht tetap 0, firmware menganggap BSS non-HT, dan TX
		 * AP->klien terkunci di rate legacy (terukur ~6 Mbit/s).
		 */
		if (vif->bss_conf.chandef.chan &&
		    vif->bss_conf.chandef.width != NL80211_CHAN_WIDTH_20_NOHT) {
			band = wcn->hw->wiphy->bands[vif->bss_conf.chandef.chan->band];
			if (band && band->ht_cap.ht_supported)
				ht_cap = &band->ht_cap;
		}
	}

	if (!ht_cap || !ht_cap->ht_supported)
		return;

	caps = ht_cap->cap;
	bss_params->ht = 1;
	bss_params->tx_channel_width_set =
		(vif->bss_conf.chandef.width == NL80211_CHAN_WIDTH_40);
	bss_params->lsig_tx_op_protection_full_support =
		is_cap_supported(caps, IEEE80211_HT_CAP_LSIG_TXOP_PROT);

	bss_params->ht_oper_mode = vif->bss_conf.ht_operation_mode;
	bss_params->lln_non_gf_coexist =
		!!(vif->bss_conf.ht_operation_mode &
		   IEEE80211_HT_OP_MODE_NON_GF_STA_PRSNT);
	/* IEEE80211_HT_STBC_PARAM_DUAL_CTS_PROT */
	bss_params->dual_cts_protection = 0;
	/* IEEE80211_HT_OP_MODE_PROTECTION_20MHZ */
	bss_params->ht20_coexist = 0;
}'''


def main():
    try:
        src = open(PATH).read()
    except OSError as e:
        print("GAGAL membuka %s: %s" % (PATH, e))
        return 1

    # 1. Buang definisi lama (dari tanda tangan fungsi sampai '}' di kolom 0).
    pattern = re.compile(
        r"static void wcn36xx_smd_set_bss_ht_params\(struct ieee80211_vif \*vif,.*?\n\}\n",
        re.S)
    src, n = pattern.subn(NEW_FUNC + "\n", src)
    if n != 1:
        print("GAGAL: definisi fungsi tidak unik/tidak ketemu (n=%d)" % n)
        return 1
    print("OK: definisi fungsi diganti")

    # 2. Perbarui pemanggilnya supaya mengirim pointer wcn.
    src, n2 = re.subn(r"wcn36xx_smd_set_bss_ht_params\(vif, sta, bss\);",
                      "wcn36xx_smd_set_bss_ht_params(wcn, vif, sta, bss);", src)
    if n2 != 1:
        print("GAGAL: pemanggil tidak ketemu (n=%d)" % n2)
        return 1
    print("OK: pemanggil diperbarui")

    open(PATH, "w").write(src)
    print("SELESAI: %s ditambal" % PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
