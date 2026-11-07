"""Kaggle dataset export: CSVs with dataset column names, figures (pipeline flow, nonce LSB histogram,
ExtraNonce plot), SHA256SUMS and dataset-metadata.json.

The dataset description is read from an article file (ARTICLE.md by default, not part of this repo).
Balance columns are only included once every high + medium address has been checked.
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

from ..domain.balance import RewardStatus
from ..domain.bitcoin import format_btc
from ..domain.patoshi import Confidence, matches_nonce_lsb


def _write(path, fields, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def _block_columns(b):
    return {
        "height": b.height,
        "block_hash": b.hash,
        "timestamp_utc": b.time_utc,
        "nonce": b.nonce,
        "nonce_lsb": b.nonce_lsb,
        "extranonce": "" if b.extranonce is None else b.extranonce,
        "coinbase_pubkey": b.pubkey,
        "address": b.address,
    }


def blocks_csv(blocks, out):
    rows = [{**_block_columns(b), "lsb_match": int(matches_nonce_lsb(b.nonce_lsb))} for b in blocks]
    _write(os.path.join(out, "bitcoin_blocks_0_54316.csv"), list(rows[0]), rows)


def patoshi_csv(candidates, balances, out):
    attributed = [c for c in candidates if c.confidence in (Confidence.HIGH, Confidence.MEDIUM)]
    complete = all(c.block.height in balances for c in attributed)
    rows = []
    for c in candidates:
        row = {k: v for k, v in _block_columns(c.block).items() if k != "nonce"}
        row["confidence"] = c.confidence.value
        if complete:
            s = balances.get(c.block.height)
            row.update({
                "coinbase_txid": s.coinbase_txid if s else "",
                "reward_btc": format_btc(s.reward_sats) if s else "",
                "reward_spent": ("genesis_unspendable" if s.status == RewardStatus.GENESIS else s.status.value) if s else "",
                "reward_spent_txid": s.spent_txid if s else "",
                "p2pkh_balance_btc": format_btc(s.p2pkh_sats) if s else "",
                "total_btc": format_btc(s.total_sats) if s else "",
                "balance_checked_utc": s.checked_utc if s else "",
            })
        rows.append(row)
    _write(os.path.join(out, "patoshi_addresses.csv"), list(rows[0]), rows)
    return complete


def flow_figure(out):
    fig, ax = plt.subplots(figsize=(14, 17))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 17)
    ax.axis("off")

    def box(x, y, w, h, title, body, color):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08,rounding_size=0.18",
                                    fc=color, ec="#333333", lw=1.4))
        ax.text(x + w / 2, y + h - 0.32, title, ha="center", va="top", fontsize=12.5, weight="bold")
        ax.text(x + w / 2, y + h - 0.78, body, ha="center", va="top", fontsize=9.6, linespacing=1.45)

    def arrow(x1, y1, x2, y2, label=""):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=18, lw=1.6, color="#333333"))
        if label:
            ax.text((x1 + x2) / 2 + 0.15, (y1 + y2) / 2, label, fontsize=9, va="center", style="italic", color="#444444")

    ax.text(7, 16.6, "Patoshi Pattern Pipeline: from public blockchain data to Satoshi-attributed addresses",
            ha="center", fontsize=14.5, weight="bold")

    box(3.5, 14.3, 7, 1.8, "0. SOURCE: Bitcoin blockchain (public)",
          "Blocks 0 - 54,316 (Jan 2009 - May 2010)\nread via mempool.space public REST API (no node, no key)\n"
          "every value is verifiable against Bitcoin Core / any block explorer", "#e8eef7")
    box(3.5, 11.4, 7, 2.3, "1. DOWNLOAD  (download)",
          "GET /api/v1/blocks/{h}  ->  10 blocks per request, ~5,430 requests\n"
          "per block: hash, timestamp, nonce, coinbase scriptSig, coinbase output\n"
          "nonce_lsb = nonce & 0xFF      extranonce = 2nd push of coinbase scriptSig\n"
          "address = Base58Check(0x00 + RIPEMD160(SHA256(P2PK pubkey)))", "#dff0e0")
    box(3.5, 8.6, 7, 2.2, "2. FILTER A: nonce LSB  (Lerner 2013)",
          "keep blocks with nonce_lsb in [0-9] or [19-58]  (50 of 256 values)\n"
          "54,317 blocks  ->  28,746 candidates\n"
          "negative control: 25,571 blocks outside the range\n"
          "background estimate: 25,571 x 50/206 = ~6,207 chance matches", "#fff3d6")
    box(3.5, 5.6, 7, 2.4, "3. FILTER B: ExtraNonce line tracking",
          "Patoshi = steep lines (one machine, extranonce rises fast per block)\n"
          "other miners = shallow lines\n"
          "anchors: collinear steep neighbours on BOTH sides (window 15)\n"
          "grow lines until stable (window 100)  ->  confidence\n"
          "high 19,815  |  medium 2,522  |  low 6,409", "#fde2d6")
    box(3.5, 2.7, 7, 2.3, "4. BALANCE CHECK  (balance)",
          "3 requests per high/medium address:\n"
          "/block/{hash}/txs/0  -> coinbase txid + reward\n"
          "/tx/{txid}/outspends -> was the 50 BTC P2PK output ever spent?\n"
          "/address/{addr}      -> later P2PKH deposits (tributes)", "#efe2f7")
    box(3.5, 0.3, 7, 1.8, "5. OUTPUT  (Kaggle dataset)",
          "bitcoin_blocks_0_54316.csv   patoshi_addresses.csv\n"
          "plot_extranonce.png   nonce_lsb_histogram.png   SHA256SUMS", "#e8eef7")

    arrow(7, 14.3, 7, 13.75)
    arrow(7, 11.4, 7, 10.85)
    arrow(7, 8.6, 7, 8.05)
    arrow(7, 5.6, 7, 5.05)
    arrow(7, 2.7, 7, 2.15)

    # proof / validation on the side
    box(10.9, 11.4, 2.95, 2.3, "PROOF",
          "block 0 ->\n1A1zP1eP5...DivfNa\n(genesis, known)\nblock 9 ->\n12cbQLTF...pTu3S\n(Satoshi -> Hal F.)", "#f4f4f4")
    box(10.9, 8.6, 2.95, 2.2, "PROOF",
          "LSB histogram:\nexcess only in\n0-9 & 19-58,\nflat elsewhere\n(uniform background)", "#f4f4f4")
    box(10.9, 5.6, 2.95, 2.4, "PROOF",
          "same filter run on\nnegative control\n-> est. false pos.\nhigh: ~196 (99%)\nhigh+med: ~721", "#f4f4f4")
    box(10.9, 2.7, 2.95, 2.3, "PROOF",
          "block 9 reward\nspent in tx\nf4184fc5...\n(block 170,\nfirst BTC tx)", "#f4f4f4")
    box(0.15, 5.6, 2.95, 2.4, "BENCHMARK",
          "Lerner: ~22k blocks\nArkham: ~21.9k addr\nthis work:\nstat. ~22,539\nhigh+med 22,337", "#f4f4f4")
    for y in (12.55, 9.7, 6.8, 3.85):
        arrow(10.5, y, 10.9, y)
    arrow(3.1, 6.8, 3.5, 6.8)

    fig.savefig(os.path.join(out, "pipeline_flow.png"), dpi=110, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def lsb_figure(blocks, out):
    n = [0] * 256
    for b in blocks:
        n[b.nonce_lsb] += 1
    outside = [n[i] for i in range(256) if not matches_nonce_lsb(i)]
    base = sum(outside) / len(outside)
    fig, ax = plt.subplots(figsize=(14, 5.5))
    ax.bar(range(256), n, width=1.0, color=["tab:blue" if matches_nonce_lsb(i) else "#aaaaaa" for i in range(256)])
    ax.axhline(base, color="tab:red", ls="--", lw=1.2, label=f"background (mean outside range) = {base:.0f} blocks per value")
    ax.set_xlim(-1, 256)
    ax.set_xlabel("nonce & 0xFF  (least significant byte of the block nonce)")
    ax.set_ylabel("number of blocks")
    ax.set_title("Blocks 0-54,316: nonce LSB distribution. Excess only in 0-9 and 19-58 = Patoshi miner")
    ax.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "nonce_lsb_histogram.png"), dpi=100, facecolor="white")
    plt.close(fig)
    return base


def metadata(complete, article_path, out, kaggle_user):
    with open(article_path) as f:
        article = f.read()
    meta = {
        "title": "Satoshi Nakamoto Patoshi Addresses (Bitcoin 2009-2010)",
        "subtitle": "Early Bitcoin blocks attributed to Satoshi via the Patoshi pattern, reproducible",
        "id": f"{kaggle_user}/satoshi-patoshi-addresses",
        "licenses": [{"name": "CC0-1.0"}],
        "keywords": ["bitcoin", "cryptocurrency", "blockchain", "finance", "history"],
        "description": article,
        "resources": [
            {"path": "bitcoin_blocks_0_54316.csv", "description": "All blocks 0-54,316 with nonce, extranonce, coinbase pubkey and address"},
            {"path": "patoshi_addresses.csv", "description": "Blocks matching the Patoshi nonce-LSB pattern with ExtraNonce confidence"
                                                         + (" and current balance" if complete else "")},
        ],
    }
    with open(os.path.join(out, "dataset-metadata.json"), "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)


def checksum(out):
    lines = []
    for name in sorted(os.listdir(out)):
        if name in ("SHA256SUMS", "dataset-metadata.json"):
            continue
        with open(os.path.join(out, name), "rb") as f:
            lines.append(f"{hashlib.sha256(f.read()).hexdigest()}  {name}")
    with open(os.path.join(out, "SHA256SUMS"), "w") as f:
        f.write("\n".join(lines) + "\n")


def export(blocks, candidates, balances, plot_png, article_path, out, kaggle_user):
    os.makedirs(out, exist_ok=True)
    blocks = sorted(blocks, key=lambda b: b.height)
    blocks_csv(blocks, out)
    complete = patoshi_csv(candidates, balances, out)
    flow_figure(out)
    base = lsb_figure(blocks, out)
    shutil.copy(plot_png, os.path.join(out, "plot_extranonce.png"))
    shutil.copy(article_path, os.path.join(out, "ARTICLE.md"))
    metadata(complete, article_path, out, kaggle_user)
    checksum(out)
    return complete, base
