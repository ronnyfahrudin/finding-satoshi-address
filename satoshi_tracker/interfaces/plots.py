"""Static figure: ExtraNonce vs height, colored by confidence."""
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

COLORS = [
    ("none", "#bbbbbb", "no LSB match"),
    ("low", "tab:orange", "LSB match, low confidence"),
    ("medium", "tab:green", "medium confidence"),
    ("high", "tab:blue", "high confidence"),
]


def extranonce_plot(blocks, candidates, path):
    level = {c.block.height: c.confidence.value for c in candidates}
    fig, ax = plt.subplots(figsize=(16, 8))
    for key, color, label in COLORS:
        pts = [(b.height, b.extranonce or 0) for b in blocks if level.get(b.height, "none") == key]
        ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=0.6, c=color, label=f"{label} ({len(pts):,})")
    ax.set_ylim(0, 7000)
    ax.set_xlabel("height")
    ax.set_ylabel("extranonce")
    ax.set_title("Patoshi pattern: ExtraNonce vs height")
    ax.legend(markerscale=12, loc="upper left")
    fig.tight_layout()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=90)
