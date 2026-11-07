"""Fund-flow graph: addresses and transactions as nodes, BTC moved as edges."""

# recipient of 10 BTC in the first Bitcoin transaction (block 170), address derived from the output script
KNOWN_ADDRESSES = {"1Q2TWHE3GMdB6BZKafqwxXtWAWgFt5Jvm3": "Hal Finney (block 170)"}


class FundFlowGraph:
    def __init__(self, patoshi_heights):
        self.patoshi_heights = patoshi_heights   # address -> block height
        self.nodes = {}
        self.edges = {}                          # (from, to) -> sats

    def address(self, a):
        if a not in self.nodes:
            if a in self.patoshi_heights:
                h = self.patoshi_heights[a]
                self.nodes[a] = {"id": a, "kind": "patoshi", "label": f"block {h}", "height": h}
            else:
                self.nodes[a] = {"id": a, "kind": "label" if a in KNOWN_ADDRESSES else "addr",
                                 "label": KNOWN_ADDRESSES.get(a, a[:8] + "…")}
        return a

    def transaction(self, txid, hop, height, date):
        tid = "tx:" + txid
        self.nodes[tid] = {"id": tid, "kind": "tx", "label": f"tx · block {height if height is not None else '?'}",
                           "txid": txid, "hop": hop, "height": height, "time": date}
        return tid

    def flow(self, src, dst, sats):
        self.edges[(src, dst)] = self.edges.get((src, dst), 0) + sats

    def address_nodes(self):
        return [n for n in self.nodes.values() if n["kind"] != "tx"]

    def kinds(self):
        counts = {}
        for n in self.nodes.values():
            counts[n["kind"]] = counts.get(n["kind"], 0) + 1
        return counts
