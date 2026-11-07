#!/usr/bin/env python3
"""Graf aliran dana dari reward mining Patoshi yang pernah dipindah -> aliran_dana.html

Node  = alamat (oranye = alamat Patoshi/hasil mining, biru = alamat lain) dan
        transaksi (belah ketupat abu-abu).
Edge  = BTC yang mengalir: alamat -> transaksi (input), transaksi -> alamat (output).

Sumber reward yang dipindah: saldo_alamat.csv (reward_dipindah = ya), jadi graf ikut
bertambah selama tahap saldo berjalan. Transaksi diikuti sampai KEDALAMAN hop; hanya
output >= MIN_BTC yang diikuti ke transaksi berikutnya. Respons API disimpan di
aliran_cache.json supaya tidak diminta ulang.

Ukuran lingkaran alamat = saldo saat ini: saldo P2PKH dari /address/{alamat} ditambah
output P2PK yang belum dibelanjakan di transaksi yang ditelusuri (query alamat tidak
menghitung P2PK). Alamat Patoshi memakai total_btc dari saldo_alamat.csv.

Pemakaian:
    python3 buat_aliran.py                 # kedalaman 2 hop
    ALIRAN_SALDO=0 python3 buat_aliran.py  # tanpa cek saldo alamat (lebih cepat)
    ALIRAN_HOP=3 ALIRAN_MIN_BTC=5 python3 buat_aliran.py
"""
import csv
import json
import os
import time
from datetime import datetime, timezone

import patoshi_scan as ps

DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(DIR, "aliran_dana.html")
CACHE = os.path.join(DIR, "aliran_cache.json")
HOP = int(os.environ.get("ALIRAN_HOP", 2))
MIN_BTC = float(os.environ.get("ALIRAN_MIN_BTC", 1))
MAKS_TX = int(os.environ.get("ALIRAN_MAKS_TX", 400))
CEK_SALDO = os.environ.get("ALIRAN_SALDO", "1") != "0"
JEDA = 3  # sama dengan tahap saldo yang mungkin sedang berjalan

# penerima 10 BTC di transaksi Bitcoin pertama (blok 170), alamat diturunkan dari script output
LABEL = {"1Q2TWHE3GMdB6BZKafqwxXtWAWgFt5Jvm3": "Hal Finney (block 170)"}


def muat_cache():
    if os.path.exists(CACHE):
        with open(CACHE) as f:
            return json.load(f)
    return {}


def simpan_cache(c):
    with open(CACHE, "w") as f:
        json.dump(c, f)


def ambil(cache, path):
    if path not in cache:
        cache[path] = ps.ambil(path)
        simpan_cache(cache)
        time.sleep(JEDA)
    return cache[path]


def alamat_output(o):
    if o.get("scriptpubkey_address"):
        return o["scriptpubkey_address"]
    s = o.get("scriptpubkey", "")
    if o.get("scriptpubkey_type") == "p2pk" and s.endswith("ac"):
        return ps.pubkey_ke_alamat(s[2:-2])
    return f"script:{s[:16]}"


def main():
    saldo = list(csv.DictReader(open(ps.SALDO_CSV)))
    patoshi = {r["alamat"]: int(r["height"]) for r in csv.DictReader(open(ps.PATOSHI_CSV))
               if r["keyakinan"] in ("tinggi", "sedang")}
    awal = sorted({r["reward_dipindah_txid"] for r in saldo if r["reward_dipindah"] == "ya"})
    cache = muat_cache()

    nodes, edges, txs = {}, {}, {}
    antrean = [(t, 1) for t in awal]
    dilihat = set()
    while antrean and len(dilihat) < MAKS_TX:
        txid, hop = antrean.pop(0)
        if txid in dilihat:
            continue
        dilihat.add(txid)
        tx = ambil(cache, f"/tx/{txid}")
        outs = ambil(cache, f"/tx/{txid}/outspends")
        txs[txid] = (tx, hop, outs)
        if hop < HOP:
            for o, sp in zip(tx["vout"], outs):
                if sp.get("spent") and o["value"] / ps.SATS >= MIN_BTC:
                    antrean.append((sp["txid"], hop + 1))
        print(f"\r  transaksi: {len(dilihat):,} (hop {hop})", end="", flush=True)
    print()

    def node_alamat(a):
        if a not in nodes:
            if a in patoshi:
                nodes[a] = {"id": a, "kind": "patoshi", "label": f"block {patoshi[a]}", "height": patoshi[a]}
            else:
                nodes[a] = {"id": a, "kind": "label" if a in LABEL else "addr",
                            "label": LABEL.get(a, a[:8] + "…")}
        return a

    def tambah_edge(src, dst, sats):
        k = (src, dst)
        edges[k] = edges.get(k, 0) + sats

    for txid, (tx, hop, _) in txs.items():
        st = tx.get("status", {})
        tid = "tx:" + txid
        nodes[tid] = {"id": tid, "kind": "tx", "label": f"tx · block {st.get('block_height', '?')}",
                      "txid": txid, "hop": hop, "height": st.get("block_height"),
                      "time": datetime.fromtimestamp(st["block_time"], timezone.utc).strftime("%Y-%m-%d")
                      if st.get("block_time") else ""}
        for i in tx["vin"]:
            if i.get("is_coinbase") or not i.get("prevout"):
                continue
            tambah_edge(node_alamat(alamat_output(i["prevout"])), tid, i["prevout"]["value"])
        for o in tx["vout"]:
            if o["value"] > 0:
                tambah_edge(tid, node_alamat(alamat_output(o)), o["value"])

    # saldo per alamat
    saldo_patoshi = {r["alamat"]: float(r["total_btc"]) for r in saldo}
    p2pk_utxo = {}
    for tx, _, outs in txs.values():
        for o, sp in zip(tx["vout"], outs):
            if o.get("scriptpubkey_type") == "p2pk" and not sp.get("spent"):
                a = alamat_output(o)
                p2pk_utxo[a] = p2pk_utxo.get(a, 0) + o["value"]
    alamat = [n for n in nodes.values() if n["kind"] != "tx"]
    for i, n in enumerate(alamat, 1):
        a = n["id"]
        if a in saldo_patoshi:
            n["btc"] = saldo_patoshi[a]
        elif CEK_SALDO and not a.startswith("script:"):
            st = ambil(cache, f"/address/{a}")["chain_stats"]
            n["btc"] = round((st["funded_txo_sum"] - st["spent_txo_sum"] + p2pk_utxo.get(a, 0)) / ps.SATS, 8)
        elif a in p2pk_utxo:
            n["btc"] = round(p2pk_utxo[a] / ps.SATS, 8)
        print(f"\r  saldo alamat: {i:,}/{len(alamat):,}", end="", flush=True)
    print()

    data = {
        "nodes": list(nodes.values()),
        "edges": [{"from": a, "to": b, "btc": round(v / ps.SATS, 8)} for (a, b), v in edges.items()],
        "meta": {
            "spent_rewards": len(awal),
            "checked": len(saldo),
            "hop": HOP,
            "min_btc": MIN_BTC,
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        },
    }
    with open(os.path.join(DIR, "aliran_template.html")) as f:
        html = f.read().replace("__DATA__", json.dumps(data, separators=(",", ":")))
    with open(OUT, "w") as f:
        f.write(html)
    jenis = {}
    for n in nodes.values():
        jenis[n["kind"]] = jenis.get(n["kind"], 0) + 1
    print(f"Reward dipindah : {len(awal)} (dari {len(saldo):,} alamat yang sudah dicek)")
    print(f"Node            : {len(nodes):,} {jenis}")
    print(f"Edge            : {len(edges):,}")
    print(f"Tersimpan       : {OUT}")


if __name__ == "__main__":
    main()
