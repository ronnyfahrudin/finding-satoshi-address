#!/usr/bin/env python3
"""Replikasi sederhana analisis "Patoshi pattern" (Sergio Lerner) tanpa full node,
memakai API publik mempool.space (10 blok per request).

Tahap 1 - unduh:  data setiap blok disimpan ke blok_awal.csv (bisa dilanjutkan
                  kalau terputus; jalankan ulang saja).
Tahap 2 - analisa: blok yang cocok dengan LSB nonce Patoshi disimpan ke alamat_patoshi.csv,
                  masing-masing diberi tingkat keyakinan dari analisis garis ExtraNonce.
Tahap 3 - saldo:   cek isi alamat Patoshi (3 request per blok), disimpan ke
                  saldo_alamat.csv lalu digabung ke alamat_patoshi.csv.

Pemakaian:
    python3 patoshi_scan.py              # blok 0 .. 54316
    python3 patoshi_scan.py 0 5000       # rentang blok tertentu
    python3 patoshi_scan.py unduh 0 5000 # hanya unduh
    python3 patoshi_scan.py analisa      # hanya analisa data yang sudah diunduh
    python3 patoshi_scan.py saldo 0 999  # cek saldo alamat Patoshi di blok 0-999
    python3 patoshi_scan.py plot         # gambar plot_extranonce.png
    python3 patoshi_scan.py daftar       # wallet_satoshi.csv: alamat + saldo BTC (ringkas)
    PATOSHI_JEDA=3 python3 ...           # jeda antar request (detik)
    PATOSHI_KEYAKINAN=tinggi,sedang ...  # tingkat yang dicek saldonya (default: tinggi)

Untuk unduhan pelan dan aman selama ~1 hari, pakai run_patoshi.sh.

Catatan: atribusi ini berbasis statistik, bukan bukti kepemilikan.
"""
import bisect
import csv
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = "https://mempool.space/api"
DIR = os.path.dirname(os.path.abspath(__file__))
BLOK_CSV = os.path.join(DIR, "blok_awal.csv")
PATOSHI_CSV = os.path.join(DIR, "alamat_patoshi.csv")
SALDO_CSV = os.path.join(DIR, "saldo_alamat.csv")
PLOT_PNG = os.path.join(DIR, "plot_extranonce.png")
DAFTAR_CSV = os.path.join(DIR, "wallet_satoshi.csv")
FIELDS = ["height", "hash", "waktu_utc", "nonce", "nonce_lsb", "extranonce", "pubkey", "alamat"]
SALDO_FIELDS = [
    "coinbase_txid", "reward_btc", "reward_dipindah", "reward_dipindah_txid",
    "saldo_p2pkh_btc", "total_btc", "waktu_cek_utc",
]
SATS = 100_000_000
JEDA = float(os.environ.get("PATOSHI_JEDA", 0.35))  # detik antar request, supaya tidak kena rate limit
KEYAKINAN = os.environ.get("PATOSHI_KEYAKINAN", "tinggi").split(",")

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def base58check(payload):
    data = payload + hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    n = int.from_bytes(data, "big")
    s = ""
    while n:
        n, r = divmod(n, 58)
        s = B58[r] + s
    return "1" * (len(data) - len(data.lstrip(b"\0"))) + s


def pubkey_ke_alamat(pubkey_hex):
    h160 = hashlib.new("ripemd160", hashlib.sha256(bytes.fromhex(pubkey_hex)).digest()).digest()
    return base58check(b"\0" + h160)


def extranonce(coinbase_hex):
    # scriptSig coinbase awal: <push bits 4 byte> <push extranonce> ...
    b = bytes.fromhex(coinbase_hex)
    if len(b) < 6:
        return ""
    n1 = b[0]
    i = 1 + n1
    if i >= len(b):
        return ""
    n2 = b[i]
    return int.from_bytes(b[i + 1:i + 1 + n2], "little") if 1 <= n2 <= 8 else ""


def ambil(path):
    for coba in range(6):
        try:
            req = urllib.request.Request(API + path, headers={"User-Agent": "patoshi-scan/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, TimeoutError) as e:
            tunggu = 2 ** coba * 5
            print(f"\n  error di {path} ({e}), coba lagi dalam {tunggu}s")
            time.sleep(tunggu)
    raise SystemExit(f"Gagal mengambil {path}, jalankan ulang untuk melanjutkan.")


def baris(b):
    ex = b["extras"]
    pubkey = ""
    alamat = ex.get("coinbaseAddress") or ""
    sig = (ex.get("coinbaseSignature") or "").split()
    if len(sig) == 3 and sig[0].startswith("OP_PUSHBYTES_") and sig[2] == "OP_CHECKSIG":
        pubkey = sig[1]
        alamat = alamat or pubkey_ke_alamat(pubkey)
    return {
        "height": b["height"],
        "hash": b["id"],
        "waktu_utc": datetime.fromtimestamp(b["timestamp"], timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "nonce": b["nonce"],
        "nonce_lsb": b["nonce"] & 0xFF,
        "extranonce": extranonce(ex.get("coinbaseRaw") or ""),
        "pubkey": pubkey,
        "alamat": alamat,
    }


def unduh(awal, akhir):
    sudah = set()
    if os.path.exists(BLOK_CSV):
        with open(BLOK_CSV) as f:
            sudah = {int(r["height"]) for r in csv.DictReader(f)}
    baru = not os.path.exists(BLOK_CSV)
    with open(BLOK_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if baru:
            w.writeheader()
        # endpoint mengembalikan blok h, h-1, ..., h-9
        for top in range(awal + 9, akhir + 10, 10):
            butuh = {h for h in range(top - 9, top + 1) if awal <= h <= akhir} - sudah
            if not butuh:
                continue
            for b in ambil(f"/v1/blocks/{top}"):
                if b["height"] in butuh:
                    w.writerow(baris(b))
                    sudah.add(b["height"])
            f.flush()
            selesai = len([h for h in sudah if awal <= h <= akhir])
            print(f"\r  {selesai:,}/{akhir - awal + 1:,} blok", end="", flush=True)
            time.sleep(JEDA)
    print()


def cocok_patoshi(lsb):
    return 0 <= lsb <= 9 or 19 <= lsb <= 58


# Analisis garis ExtraNonce. Blok Patoshi membentuk garis curam (ExtraNonce naik cepat
# terhadap height), penambang lain membentuk garis landai. Parameter: (jendela height,
# kemiringan minimum, selisih ExtraNonce maksimum, rasio kemiringan maksimum, butuh dua sisi).
P_JANGKAR = (15, 3, 80, 2.5, True)   # sangat ketat: titik jangkar awal
P_TINGGI = (100, 2, 600, 3, True)    # di antara dua tetangga jangkar yang segaris
P_SEDANG = (60, 2, 300, 3, False)    # cukup satu tetangga jangkar yang curam


def segaris(h, e, ref, refh, jendela, smin, dmax, rasio, dua_sisi):
    i, j = bisect.bisect_left(refh, h - jendela), bisect.bisect_right(refh, h + jendela)
    maju, mundur = [], []
    for hq, eq in ref[i:j]:
        dh, de = hq - h, eq - e
        if dh == 0 or de == 0 or abs(de) > dmax or (dh > 0) != (de > 0):
            continue
        if de / dh >= smin:
            (maju if dh > 0 else mundur).append(de / dh)
    if dua_sisi:
        return any(1 / rasio <= a / b <= rasio for a in maju for b in mundur)
    return bool(maju or mundur)


def beri_keyakinan(hasil):
    titik = [(int(r["height"]), int(r["extranonce"] or 0)) for r in hasil]
    th = [t[0] for t in titik]
    jangkar = [t for t in titik if segaris(*t, titik, th, *P_JANGKAR)]
    # kembangkan jangkar sampai stabil
    for _ in range(5):
        jh = [t[0] for t in jangkar]
        baru = [t for t in titik if segaris(*t, jangkar, jh, *P_TINGGI)]
        if len(baru) == len(jangkar):
            break
        jangkar = baru
    jh = [t[0] for t in jangkar]
    tinggi = set(jangkar)
    for r, t in zip(hasil, titik):
        if t in tinggi:
            r["keyakinan"] = "tinggi"
        elif segaris(*t, jangkar, jh, *P_SEDANG):
            r["keyakinan"] = "sedang"
        else:
            r["keyakinan"] = "rendah"


def baca_saldo():
    if not os.path.exists(SALDO_CSV):
        return {}
    with open(SALDO_CSV) as f:
        return {int(r["height"]): r for r in csv.DictReader(f)}


def tulis_patoshi(rows):
    # gabungkan data saldo (kalau sudah dicek) ke alamat_patoshi.csv
    saldo = baca_saldo()
    with open(PATOSHI_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS + ["keyakinan"] + SALDO_FIELDS)
        w.writeheader()
        for r in rows:
            s = saldo.get(int(r["height"]), {})
            w.writerow({**{k: r[k] for k in FIELDS + ["keyakinan"]}, **{k: s.get(k, "") for k in SALDO_FIELDS}})
    dicek = [saldo[int(r["height"])] for r in rows if int(r["height"]) in saldo]
    if dicek:
        utuh = sum(1 for s in dicek if s["reward_dipindah"] == "tidak")
        total = sum(float(s["total_btc"]) for s in dicek)
        print(f"Saldo sudah dicek: {len(dicek):,}/{len(rows):,} alamat")
        print(f"Reward belum dipindah: {utuh:,} alamat")
        print(f"Total isi wallet : {total:,.8f} BTC (dari alamat yang sudah dicek)")


def analisa(awal, akhir):
    with open(BLOK_CSV) as f:
        rows = sorted(
            (r for r in csv.DictReader(f) if awal <= int(r["height"]) <= akhir),
            key=lambda r: int(r["height"]),
        )
    hasil = [r for r in rows if cocok_patoshi(int(r["nonce_lsb"]))]
    beri_keyakinan(hasil)
    # blok di luar rentang LSB (206 dari 256 nilai) pasti bukan Patoshi; dari situ
    # diperkirakan berapa blok penambang lain yang kebetulan lolos filter LSB
    est = len(hasil) - (len(rows) - len(hasil)) * 50 / 206
    print(f"Blok dianalisa   : {len(rows):,} (blok {awal}-{akhir})")
    print(f"Cocok LSB nonce  : {len(hasil):,} blok / alamat")
    print(f"Perkiraan Patoshi asli (statistik): ~{est:,.0f} blok (~{est * 50:,.0f} BTC)")
    for k in ("tinggi", "sedang", "rendah"):
        n = sum(r["keyakinan"] == k for r in hasil)
        print(f"  keyakinan {k:<7}: {n:>6,} alamat ({n * 50:,} BTC)")
    tulis_patoshi(hasil)
    print(f"Tersimpan        : {PATOSHI_CSV}")


def cek_satu(r):
    # 1) transaksi coinbase blok: txid dan nilai reward
    cb = ambil(f"/block/{r['hash']}/txs/0")[0]
    time.sleep(JEDA)
    reward = cb["vout"][0]["value"]
    # 2) apakah output reward (P2PK) sudah pernah dibelanjakan
    out = ambil(f"/tx/{cb['txid']}/outspends")[0]
    time.sleep(JEDA)
    # 3) kiriman lain ke alamat 1xxx dari pubkey yang sama (P2PKH, tidak termasuk reward)
    a = ambil(f"/address/{r['alamat']}")["chain_stats"]
    time.sleep(JEDA)
    p2pkh = a["funded_txo_sum"] - a["spent_txo_sum"]
    sisa_reward = 0 if out.get("spent") else reward
    return {
        "height": r["height"],
        "alamat": r["alamat"],
        "coinbase_txid": cb["txid"],
        "reward_btc": f"{reward / SATS:.8f}",
        # reward blok genesis tidak pernah masuk UTXO set, jadi tidak bisa dibelanjakan
        "reward_dipindah": "ya" if out.get("spent") else ("genesis" if r["height"] == "0" else "tidak"),
        "reward_dipindah_txid": out.get("txid", ""),
        "saldo_p2pkh_btc": f"{p2pkh / SATS:.8f}",
        "total_btc": f"{(sisa_reward + p2pkh) / SATS:.8f}",
        "waktu_cek_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    }


def saldo(awal, akhir):
    with open(PATOSHI_CSV) as f:
        semua = list(csv.DictReader(f))
    sudah = baca_saldo()
    target = [
        r for r in semua
        if awal <= int(r["height"]) <= akhir and r["keyakinan"] in KEYAKINAN and int(r["height"]) not in sudah
    ]
    if not target:
        return 2  # tidak ada yang perlu dicek (dipakai run_patoshi.sh untuk melewati batch)
    print(f"Cek saldo {len(target):,} alamat keyakinan {'/'.join(KEYAKINAN)} (blok {awal}-{akhir}) ...")
    baru = not os.path.exists(SALDO_CSV)
    with open(SALDO_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["height", "alamat"] + SALDO_FIELDS)
        if baru:
            w.writeheader()
        for i, r in enumerate(target, 1):
            w.writerow(cek_satu(r))
            f.flush()
            print(f"\r  {i:,}/{len(target):,} alamat", end="", flush=True)
    print()
    tulis_patoshi(semua)
    return 0


def daftar():
    with open(PATOSHI_CSV) as f:
        pat = [r for r in csv.DictReader(f) if r["keyakinan"] in ("tinggi", "sedang")]
    saldo = baca_saldo()
    rows = []
    for r in pat:
        s = saldo.get(int(r["height"]))
        rows.append({
            "alamat": r["alamat"],
            "saldo_btc": s["total_btc"] if s else "",
            "reward_dipindah": s["reward_dipindah"] if s else "",
            "status": "sudah dicek" if s else "belum dicek",
            "height": r["height"],
            "waktu_blok_utc": r["waktu_utc"],
            "keyakinan": r["keyakinan"],
        })
    with open(DAFTAR_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    dicek = [r for r in rows if r["saldo_btc"]]
    print(f"Alamat (tinggi+sedang): {len(rows):,}")
    print(f"Saldo sudah dicek     : {len(dicek):,} ({len(dicek) / len(rows):.1%})")
    print(f"Total saldo dicek     : {sum(float(r['saldo_btc']) for r in dicek):,.8f} BTC")
    print(f"Tersimpan             : {DAFTAR_CSV}")


def plot():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with open(BLOK_CSV) as f:
        semua = list(csv.DictReader(f))
    with open(PATOSHI_CSV) as f:
        kel = {int(r["height"]): r["keyakinan"] for r in csv.DictReader(f)}
    warna = [
        ("bukan", "#bbbbbb", "LSB tidak cocok"),
        ("rendah", "tab:orange", "LSB cocok, keyakinan rendah"),
        ("sedang", "tab:green", "keyakinan sedang"),
        ("tinggi", "tab:blue", "keyakinan tinggi"),
    ]
    fig, ax = plt.subplots(figsize=(16, 8))
    for k, c, label in warna:
        pts = [(int(r["height"]), int(r["extranonce"] or 0)) for r in semua if kel.get(int(r["height"]), "bukan") == k]
        ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=0.6, c=c, label=f"{label} ({len(pts):,})")
    ax.set_ylim(0, 7000)
    ax.set_xlabel("height")
    ax.set_ylabel("extranonce")
    ax.set_title("Patoshi pattern: ExtraNonce vs height")
    ax.legend(markerscale=12, loc="upper left")
    fig.tight_layout()
    fig.savefig(PLOT_PNG, dpi=90)
    print(f"Tersimpan        : {PLOT_PNG}")


def main():
    args = sys.argv[1:]
    mode = args.pop(0) if args and args[0] in ("unduh", "analisa", "saldo", "plot", "daftar") else "semua"
    awal = int(args[0]) if len(args) > 0 else 0
    akhir = int(args[1]) if len(args) > 1 else 54316
    if mode in ("unduh", "semua"):
        print(f"Mengunduh blok {awal}-{akhir} dari mempool.space ...")
        unduh(awal, akhir)
    if mode in ("analisa", "semua"):
        analisa(awal, akhir)
    if mode == "saldo":
        sys.exit(saldo(awal, akhir))
    if mode == "plot":
        plot()
    if mode == "daftar":
        daftar()


if __name__ == "__main__":
    main()
