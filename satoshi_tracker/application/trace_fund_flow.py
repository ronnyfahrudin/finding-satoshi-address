"""Use case: follow every moved Patoshi reward through the transactions that spent it.

Transactions are followed breadth-first up to max_hop hops; only outputs >= min_btc are followed to
the next transaction. Address balance = P2PKH balance plus unspent P2PK outputs seen in the traced
transactions (address lookups do not count P2PK). Patoshi addresses use their checked balance.
"""
from datetime import datetime, timezone

from ..domain.balance import RewardStatus
from ..domain.bitcoin import SATS, script_address
from ..domain.flow import FundFlowGraph
from .wallet_list import ATTRIBUTED


def _output_address(o):
    return script_address(o.get("scriptpubkey", ""), o.get("scriptpubkey_type"), o.get("scriptpubkey_address"))


def trace_fund_flow(client, candidates_repo, balances, max_hop, min_btc, max_tx, check_balance, progress=print):
    by_height = balances.by_height()
    patoshi = {c.block.address: c.block.height for c in candidates_repo.all() if c.confidence in ATTRIBUTED}
    start = sorted({s.spent_txid for s in by_height.values() if s.status == RewardStatus.SPENT})

    txs = {}
    queue = [(t, 1) for t in start]
    seen = set()
    while queue and len(seen) < max_tx:
        txid, hop = queue.pop(0)
        if txid in seen:
            continue
        seen.add(txid)
        tx, outs = client.tx(txid), client.outspends(txid)
        txs[txid] = (tx, hop, outs)
        if hop < max_hop:
            for o, sp in zip(tx["vout"], outs):
                if sp.get("spent") and o["value"] / SATS >= min_btc:
                    queue.append((sp["txid"], hop + 1))
        progress("transactions", len(seen), None)

    graph = FundFlowGraph(patoshi)
    for txid, (tx, hop, _) in txs.items():
        st = tx.get("status", {})
        date = datetime.fromtimestamp(st["block_time"], timezone.utc).strftime("%Y-%m-%d") if st.get("block_time") else ""
        tid = graph.transaction(txid, hop, st.get("block_height"), date)
        for i in tx["vin"]:
            if i.get("is_coinbase") or not i.get("prevout"):
                continue
            graph.flow(graph.address(_output_address(i["prevout"])), tid, i["prevout"]["value"])
        for o in tx["vout"]:
            if o["value"] > 0:
                graph.flow(tid, graph.address(_output_address(o)), o["value"])

    patoshi_balance = {s.address: s.total_sats for s in by_height.values()}
    p2pk_utxo = {}
    for tx, _, outs in txs.values():
        for o, sp in zip(tx["vout"], outs):
            if o.get("scriptpubkey_type") == "p2pk" and not sp.get("spent"):
                a = _output_address(o)
                p2pk_utxo[a] = p2pk_utxo.get(a, 0) + o["value"]
    nodes = graph.address_nodes()
    for i, n in enumerate(nodes, 1):
        a = n["id"]
        if a in patoshi_balance:
            n["btc"] = patoshi_balance[a] / SATS
        elif check_balance and not a.startswith("script:"):
            st = client.address(a)["chain_stats"]
            n["btc"] = round((st["funded_txo_sum"] - st["spent_txo_sum"] + p2pk_utxo.get(a, 0)) / SATS, 8)
        elif a in p2pk_utxo:
            n["btc"] = round(p2pk_utxo[a] / SATS, 8)
        progress("address balances", i, len(nodes))

    return graph, {"spent_rewards": len(start), "checked": len(by_height), "hop": max_hop, "min_btc": min_btc}
