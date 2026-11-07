#!/usr/bin/env python3
"""Cek saldo dan riwayat transaksi alamat Bitcoin lewat API publik mempool.space.

Pemakaian:
    python3 cek_alamat_btc.py                 # default: alamat genesis Satoshi
    python3 cek_alamat_btc.py <alamat> [n]    # n = jumlah transaksi terbaru yang ditampilkan

Hasil disimpan di folder script:
    riwayat_saldo.csv        satu baris per run (ditambahkan, tidak ditimpa)
    transaksi_<alamat>.csv   transaksi terbaru dari run terakhir (ditimpa)
"""
import csv
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

API = "https://mempool.space/api"
GENESIS = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
SATS = 100_000_000
DIR = os.path.dirname(os.path.abspath(__file__))


def get(path):
    req = urllib.request.Request(API + path, headers={"User-Agent": "cek-alamat-btc/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def btc(sats):
    return f"{sats / SATS:,.8f} BTC"


def simpan_saldo(row):
    path = os.path.join(DIR, "riwayat_saldo.csv")
    baru = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if baru:
            w.writeheader()
        w.writerow(row)
    return path


def simpan_transaksi(addr, rows):
    path = os.path.join(DIR, f"transaksi_{addr}.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["waktu_utc", "selisih_btc", "status", "txid"])
        w.writeheader()
        w.writerows(rows)
    return path


def main():
    addr = sys.argv[1] if len(sys.argv) > 1 else GENESIS
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    info = get(f"/address/{addr}")
    chain, mem = info["chain_stats"], info["mempool_stats"]
    saldo = chain["funded_txo_sum"] - chain["spent_txo_sum"]
    pending = mem["funded_txo_sum"] - mem["spent_txo_sum"]

    try:
        harga = get("/v1/prices")
    except Exception:
        harga = {}

    print(f"Alamat          : {addr}")
    print(f"Saldo           : {btc(saldo)}")
    if pending:
        print(f"Pending mempool : {btc(pending)}")
    print(f"Total diterima  : {btc(chain['funded_txo_sum'])}")
    print(f"Total dikirim   : {btc(chain['spent_txo_sum'])}")
    print(f"Jumlah transaksi: {chain['tx_count']:,}")
    if harga.get("USD"):
        print(f"Nilai saat ini  : ${saldo / SATS * harga['USD']:,.2f} (1 BTC = ${harga['USD']:,})")

    harga_usd = harga.get("USD")
    path_saldo = simpan_saldo({
        "waktu_cek_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "alamat": addr,
        "saldo_btc": f"{saldo / SATS:.8f}",
        "pending_btc": f"{pending / SATS:.8f}",
        "total_diterima_btc": f"{chain['funded_txo_sum'] / SATS:.8f}",
        "total_dikirim_btc": f"{chain['spent_txo_sum'] / SATS:.8f}",
        "jumlah_tx": chain["tx_count"],
        "harga_btc_usd": harga_usd or "",
        "nilai_usd": f"{saldo / SATS * harga_usd:.2f}" if harga_usd else "",
    })

    txs = get(f"/address/{addr}/txs")[:n]
    rows = []
    print(f"\n{len(txs)} transaksi terbaru:")
    for tx in txs:
        masuk = sum(o["value"] for o in tx["vout"] if o.get("scriptpubkey_address") == addr)
        keluar = sum(
            i["prevout"]["value"]
            for i in tx["vin"]
            if i.get("prevout") and i["prevout"].get("scriptpubkey_address") == addr
        )
        st = tx["status"]
        waktu = (
            datetime.fromtimestamp(st["block_time"], timezone.utc).strftime("%Y-%m-%d %H:%M")
            if st.get("confirmed")
            else "belum konfirmasi"
        )
        print(f"  {waktu}  {(masuk - keluar) / SATS:+.8f} BTC  {tx['txid']}")
        rows.append({
            "waktu_utc": waktu if st.get("confirmed") else "",
            "selisih_btc": f"{(masuk - keluar) / SATS:+.8f}",
            "status": "confirmed" if st.get("confirmed") else "pending",
            "txid": tx["txid"],
        })

    path_tx = simpan_transaksi(addr, rows)
    print(f"\nTersimpan: {path_saldo}")
    print(f"Tersimpan: {path_tx}")


if __name__ == "__main__":
    main()
