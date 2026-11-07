#!/usr/bin/env python3
"""Bangun folder kaggle_dataset/ dari hasil pipeline Patoshi: CSV (kolom bahasa Inggris),
gambar (flow, histogram LSB nonce, plot ExtraNonce), checksum, dan dataset-metadata.json.

Pemakaian:
    python3 buat_kaggle.py
    kaggle datasets create -p kaggle_dataset      # upload pertama
    kaggle datasets version -p kaggle_dataset -m "update saldo"   # update

Kolom saldo hanya disertakan kalau semua alamat keyakinan tinggi+sedang sudah dicek.
"""
import csv
import hashlib
import json
import os
import shutil

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

import patoshi_scan as ps

DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(DIR, "kaggle_dataset")
KAGGLE_USER = os.environ.get("KAGGLE_USER", "<username-kaggle>")
CONF = {"tinggi": "high", "sedang": "medium", "rendah": "low"}


def baca(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def tulis(path, fields, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def csv_blok(blok):
    rows = [{
        "height": r["height"],
        "block_hash": r["hash"],
        "timestamp_utc": r["waktu_utc"],
        "nonce": r["nonce"],
        "nonce_lsb": r["nonce_lsb"],
        "extranonce": r["extranonce"],
        "coinbase_pubkey": r["pubkey"],
        "address": r["alamat"],
        "lsb_match": int(ps.cocok_patoshi(int(r["nonce_lsb"]))),
    } for r in blok]
    tulis(os.path.join(OUT, "bitcoin_blocks_0_54316.csv"), list(rows[0]), rows)


def csv_patoshi(pat):
    target = [r for r in pat if r["keyakinan"] in ("tinggi", "sedang")]
    lengkap = all(r["total_btc"] for r in target)
    rows = []
    for r in pat:
        row = {
            "height": r["height"],
            "block_hash": r["hash"],
            "timestamp_utc": r["waktu_utc"],
            "nonce_lsb": r["nonce_lsb"],
            "extranonce": r["extranonce"],
            "coinbase_pubkey": r["pubkey"],
            "address": r["alamat"],
            "confidence": CONF[r["keyakinan"]],
        }
        if lengkap:
            row.update({
                "coinbase_txid": r["coinbase_txid"],
                "reward_btc": r["reward_btc"],
                "reward_spent": {"ya": "yes", "tidak": "no", "genesis": "genesis_unspendable"}.get(r["reward_dipindah"], ""),
                "reward_spent_txid": r["reward_dipindah_txid"],
                "p2pkh_balance_btc": r["saldo_p2pkh_btc"],
                "total_btc": r["total_btc"],
                "balance_checked_utc": r["waktu_cek_utc"],
            })
        rows.append(row)
    tulis(os.path.join(OUT, "patoshi_addresses.csv"), list(rows[0]), rows)
    return lengkap


def gambar_flow():
    fig, ax = plt.subplots(figsize=(14, 17))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 17)
    ax.axis("off")

    def kotak(x, y, w, h, judul, isi, warna):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08,rounding_size=0.18",
                                    fc=warna, ec="#333333", lw=1.4))
        ax.text(x + w / 2, y + h - 0.32, judul, ha="center", va="top", fontsize=12.5, weight="bold")
        ax.text(x + w / 2, y + h - 0.78, isi, ha="center", va="top", fontsize=9.6, linespacing=1.45)

    def panah(x1, y1, x2, y2, label=""):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=18, lw=1.6, color="#333333"))
        if label:
            ax.text((x1 + x2) / 2 + 0.15, (y1 + y2) / 2, label, fontsize=9, va="center", style="italic", color="#444444")

    ax.text(7, 16.6, "Patoshi Pattern Pipeline: from public blockchain data to Satoshi-attributed addresses",
            ha="center", fontsize=14.5, weight="bold")

    kotak(3.5, 14.3, 7, 1.8, "0. SOURCE: Bitcoin blockchain (public)",
          "Blocks 0 - 54,316 (Jan 2009 - May 2010)\nread via mempool.space public REST API (no node, no key)\n"
          "every value is verifiable against Bitcoin Core / any block explorer", "#e8eef7")
    kotak(3.5, 11.4, 7, 2.3, "1. DOWNLOAD  (patoshi_scan.py unduh)",
          "GET /api/v1/blocks/{h}  ->  10 blocks per request, ~5,430 requests\n"
          "per block: hash, timestamp, nonce, coinbase scriptSig, coinbase output\n"
          "nonce_lsb = nonce & 0xFF      extranonce = 2nd push of coinbase scriptSig\n"
          "address = Base58Check(0x00 + RIPEMD160(SHA256(P2PK pubkey)))", "#dff0e0")
    kotak(3.5, 8.6, 7, 2.2, "2. FILTER A: nonce LSB  (Lerner 2013)",
          "keep blocks with nonce_lsb in [0-9] or [19-58]  (50 of 256 values)\n"
          "54,317 blocks  ->  28,746 candidates\n"
          "negative control: 25,571 blocks outside the range\n"
          "background estimate: 25,571 x 50/206 = ~6,207 chance matches", "#fff3d6")
    kotak(3.5, 5.6, 7, 2.4, "3. FILTER B: ExtraNonce line tracking",
          "Patoshi = steep lines (one machine, extranonce rises fast per block)\n"
          "other miners = shallow lines\n"
          "anchors: collinear steep neighbours on BOTH sides (window 15)\n"
          "grow lines until stable (window 100)  ->  confidence\n"
          "high 19,815  |  medium 2,522  |  low 6,409", "#fde2d6")
    kotak(3.5, 2.7, 7, 2.3, "4. BALANCE CHECK  (patoshi_scan.py saldo)",
          "3 requests per high/medium address:\n"
          "/block/{hash}/txs/0  -> coinbase txid + reward\n"
          "/tx/{txid}/outspends -> was the 50 BTC P2PK output ever spent?\n"
          "/address/{addr}      -> later P2PKH deposits (tributes)", "#efe2f7")
    kotak(3.5, 0.3, 7, 1.8, "5. OUTPUT  (Kaggle dataset)",
          "bitcoin_blocks_0_54316.csv   patoshi_addresses.csv\n"
          "plot_extranonce.png   nonce_lsb_histogram.png   SHA256SUMS", "#e8eef7")

    panah(7, 14.3, 7, 13.75)
    panah(7, 11.4, 7, 10.85)
    panah(7, 8.6, 7, 8.05)
    panah(7, 5.6, 7, 5.05)
    panah(7, 2.7, 7, 2.15)

    # bukti / validasi di samping
    kotak(10.9, 11.4, 2.95, 2.3, "PROOF",
          "block 0 ->\n1A1zP1eP5...DivfNa\n(genesis, known)\nblock 9 ->\n12cbQLTF...pTu3S\n(Satoshi -> Hal F.)", "#f4f4f4")
    kotak(10.9, 8.6, 2.95, 2.2, "PROOF",
          "LSB histogram:\nexcess only in\n0-9 & 19-58,\nflat elsewhere\n(uniform background)", "#f4f4f4")
    kotak(10.9, 5.6, 2.95, 2.4, "PROOF",
          "same filter run on\nnegative control\n-> est. false pos.\nhigh: ~196 (99%)\nhigh+med: ~721", "#f4f4f4")
    kotak(10.9, 2.7, 2.95, 2.3, "PROOF",
          "block 9 reward\nspent in tx\nf4184fc5...\n(block 170,\nfirst BTC tx)", "#f4f4f4")
    kotak(0.15, 5.6, 2.95, 2.4, "BENCHMARK",
          "Lerner: ~22k blocks\nArkham: ~21.9k addr\nthis work:\nstat. ~22,539\nhigh+med 22,337", "#f4f4f4")
    for y in (12.55, 9.7, 6.8, 3.85):
        panah(10.5, y, 10.9, y)
    panah(3.1, 6.8, 3.5, 6.8)

    fig.savefig(os.path.join(OUT, "pipeline_flow.png"), dpi=110, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def gambar_lsb(blok):
    n = [0] * 256
    for r in blok:
        n[int(r["nonce_lsb"])] += 1
    luar = [n[i] for i in range(256) if not ps.cocok_patoshi(i)]
    dasar = sum(luar) / len(luar)
    fig, ax = plt.subplots(figsize=(14, 5.5))
    ax.bar(range(256), n, width=1.0, color=["tab:blue" if ps.cocok_patoshi(i) else "#aaaaaa" for i in range(256)])
    ax.axhline(dasar, color="tab:red", ls="--", lw=1.2, label=f"background (mean outside range) = {dasar:.0f} blocks per value")
    ax.set_xlim(-1, 256)
    ax.set_xlabel("nonce & 0xFF  (least significant byte of the block nonce)")
    ax.set_ylabel("number of blocks")
    ax.set_title("Blocks 0-54,316: nonce LSB distribution. Excess only in 0-9 and 19-58 = Patoshi miner")
    ax.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "nonce_lsb_histogram.png"), dpi=100, facecolor="white")
    plt.close(fig)
    return dasar


def metadata(lengkap):
    with open(os.path.join(DIR, "ARTICLE.md")) as f:
        artikel = f.read()
    meta = {
        "title": "Satoshi Nakamoto Patoshi Addresses (Bitcoin 2009-2010)",
        "subtitle": "Early Bitcoin blocks attributed to Satoshi via the Patoshi pattern, reproducible",
        "id": f"{KAGGLE_USER}/satoshi-patoshi-addresses",
        "licenses": [{"name": "CC0-1.0"}],
        "keywords": ["bitcoin", "cryptocurrency", "blockchain", "finance", "history"],
        "description": artikel,
        "resources": [
            {"path": "bitcoin_blocks_0_54316.csv", "description": "All blocks 0-54,316 with nonce, extranonce, coinbase pubkey and address"},
            {"path": "patoshi_addresses.csv", "description": "Blocks matching the Patoshi nonce-LSB pattern with ExtraNonce confidence"
                                                         + (" and current balance" if lengkap else "")},
        ],
    }
    with open(os.path.join(OUT, "dataset-metadata.json"), "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)


def checksum():
    baris = []
    for nama in sorted(os.listdir(OUT)):
        if nama in ("SHA256SUMS", "dataset-metadata.json"):
            continue
        with open(os.path.join(OUT, nama), "rb") as f:
            baris.append(f"{hashlib.sha256(f.read()).hexdigest()}  {nama}")
    with open(os.path.join(OUT, "SHA256SUMS"), "w") as f:
        f.write("\n".join(baris) + "\n")


def main():
    os.makedirs(OUT, exist_ok=True)
    blok = sorted(baca(ps.BLOK_CSV), key=lambda r: int(r["height"]))
    pat = baca(ps.PATOSHI_CSV)
    csv_blok(blok)
    lengkap = csv_patoshi(pat)
    gambar_flow()
    dasar = gambar_lsb(blok)
    shutil.copy(ps.PLOT_PNG, os.path.join(OUT, "plot_extranonce.png"))
    shutil.copy(os.path.join(DIR, "ARTICLE.md"), os.path.join(OUT, "ARTICLE.md"))
    metadata(lengkap)
    checksum()
    print(f"Folder       : {OUT}")
    print(f"Kolom saldo  : {'disertakan' if lengkap else 'belum (tahap saldo belum selesai)'}")
    print(f"Background LSB: {dasar:.1f} blok per nilai")
    for nama in sorted(os.listdir(OUT)):
        print(f"  {os.path.getsize(os.path.join(OUT, nama)) / 1e6:8.2f} MB  {nama}")


if __name__ == "__main__":
    main()
