"""Interactive HTML pages: the address bubble plot (Plotly) and the fund-flow graph (vis-network)."""
import json
import os
from datetime import datetime, timezone

from ..domain.bitcoin import SATS

TEMPLATES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
BUBBLE_STATUS = {"no": "unspent", "yes": "spent", "genesis": "genesis"}


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _render(template, path, **values):
    with open(os.path.join(TEMPLATES, template)) as f:
        html = f.read()
    for key, value in values.items():
        html = html.replace(f"__{key}__", value)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(html)


def bubble_page(entries, path):
    """entries: (PatoshiCandidate, RewardBalance or None) for every attributed address."""
    data = [{
        "a": c.block.address,
        "h": c.block.height,
        "t": c.block.time_utc.replace(" ", "T"),
        "en": c.block.extranonce or 0,
        "c": c.confidence.value,
        "s": BUBBLE_STATUS[s.status.value] if s else "unchecked",
        "btc": round(s.total_sats / SATS, 8) if s else 0,
    } for c, s in entries]
    _render("bubble.html", path, DATA=json.dumps(data, separators=(",", ":")), GENERATED=_now())
    return data


def flow_page(graph, meta, path):
    data = {
        "nodes": list(graph.nodes.values()),
        "edges": [{"from": a, "to": b, "btc": round(v / SATS, 8)} for (a, b), v in graph.edges.items()],
        "meta": {**meta, "generated": _now()},
    }
    _render("flow.html", path, DATA=json.dumps(data, separators=(",", ":")))
