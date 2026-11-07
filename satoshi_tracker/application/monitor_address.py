"""Use case: snapshot one address (balance, totals, recent transactions) and keep a history."""
from dataclasses import dataclass
from datetime import datetime, timezone

from ..domain.bitcoin import SATS, format_btc


@dataclass
class AddressSnapshot:
    address: str
    balance_sats: int
    pending_sats: int
    received_sats: int
    sent_sats: int
    tx_count: int
    usd: float
    transactions: list     # rows: time_utc, delta_btc, status, txid
    history_path: str
    transactions_path: str


def monitor_address(client, history, address, n):
    info = client.address(address)
    chain, mem = info["chain_stats"], info["mempool_stats"]
    balance = chain["funded_txo_sum"] - chain["spent_txo_sum"]
    pending = mem["funded_txo_sum"] - mem["spent_txo_sum"]
    try:
        usd = client.prices().get("USD")
    except Exception:
        usd = None

    history_path = history.append_snapshot({
        "checked_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "address": address,
        "balance_btc": format_btc(balance),
        "pending_btc": format_btc(pending),
        "total_received_btc": format_btc(chain["funded_txo_sum"]),
        "total_sent_btc": format_btc(chain["spent_txo_sum"]),
        "tx_count": chain["tx_count"],
        "btc_price_usd": usd or "",
        "value_usd": f"{balance / SATS * usd:.2f}" if usd else "",
    })

    rows = []
    for tx in client.address_txs(address)[:n]:
        received = sum(o["value"] for o in tx["vout"] if o.get("scriptpubkey_address") == address)
        sent = sum(i["prevout"]["value"] for i in tx["vin"]
                   if i.get("prevout") and i["prevout"].get("scriptpubkey_address") == address)
        st = tx["status"]
        rows.append({
            "time_utc": datetime.fromtimestamp(st["block_time"], timezone.utc).strftime("%Y-%m-%d %H:%M")
            if st.get("confirmed") else "",
            "delta_btc": f"{(received - sent) / SATS:+.8f}",
            "status": "confirmed" if st.get("confirmed") else "pending",
            "txid": tx["txid"],
        })
    tx_path = history.save_transactions(address, rows)
    return AddressSnapshot(address, balance, pending, chain["funded_txo_sum"], chain["spent_txo_sum"],
                           chain["tx_count"], usd, rows, history_path, tx_path)
