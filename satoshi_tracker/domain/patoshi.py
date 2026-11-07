"""Patoshi attribution rules (after Sergio Demian Lerner, 2013).

Signal 1, nonce LSB: the Patoshi miner only produced nonces whose last byte is in 0-9 or 19-58.
Signal 2, ExtraNonce lines: Patoshi blocks lie on steep ExtraNonce-vs-height lines (one machine
hashing continuously), other miners on shallow lines.
"""
import bisect
from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple

from .block import Block

LSB_VALUES = 50          # 0-9 and 19-58
NON_LSB_VALUES = 256 - LSB_VALUES
BLOCK_REWARD_BTC = 50


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class PatoshiCandidate:
    """A block that passes the nonce LSB rule, graded by the ExtraNonce line analysis."""
    block: Block
    confidence: Confidence


class LineRule(NamedTuple):
    window: int         # height window around the point
    min_slope: float    # minimum ExtraNonce per block
    max_step: int       # maximum ExtraNonce difference to a neighbour
    max_ratio: float    # maximum ratio between the slopes before and after
    both_sides: bool    # needs collinear neighbours before AND after


ANCHOR = LineRule(15, 3, 80, 2.5, True)    # very strict: initial anchor points
HIGH = LineRule(100, 2, 600, 3, True)      # between two collinear anchor neighbours
MEDIUM = LineRule(60, 2, 300, 3, False)    # one steep anchor neighbour is enough


def matches_nonce_lsb(lsb):
    return 0 <= lsb <= 9 or 19 <= lsb <= 58


def _on_steep_line(point, ref, ref_heights, rule):
    h, e = point
    i = bisect.bisect_left(ref_heights, h - rule.window)
    j = bisect.bisect_right(ref_heights, h + rule.window)
    ahead, behind = [], []
    for hq, eq in ref[i:j]:
        dh, de = hq - h, eq - e
        if dh == 0 or de == 0 or abs(de) > rule.max_step or (dh > 0) != (de > 0):
            continue
        if de / dh >= rule.min_slope:
            (ahead if dh > 0 else behind).append(de / dh)
    if rule.both_sides:
        return any(1 / rule.max_ratio <= a / b <= rule.max_ratio for a in ahead for b in behind)
    return bool(ahead or behind)


def classify(blocks):
    """Grade LSB-matching blocks (sorted by height) -> list of PatoshiCandidate in the same order."""
    points = [(b.height, b.extranonce or 0) for b in blocks]
    heights = [p[0] for p in points]
    anchors = [p for p in points if _on_steep_line(p, points, heights, ANCHOR)]
    # grow the anchors until stable
    for _ in range(5):
        anchor_heights = [p[0] for p in anchors]
        grown = [p for p in points if _on_steep_line(p, anchors, anchor_heights, HIGH)]
        if len(grown) == len(anchors):
            break
        anchors = grown
    anchor_heights = [p[0] for p in anchors]
    high = set(anchors)
    result = []
    for b, p in zip(blocks, points):
        if p in high:
            level = Confidence.HIGH
        elif _on_steep_line(p, anchors, anchor_heights, MEDIUM):
            level = Confidence.MEDIUM
        else:
            level = Confidence.LOW
        result.append(PatoshiCandidate(b, level))
    return result


def estimate_true_patoshi(total_blocks, lsb_matches):
    """Statistical Patoshi block count. Blocks outside the LSB range are certainly not Patoshi and
    are uniform over 206 values, so 50/206 of their count fell into the range by chance."""
    return lsb_matches - (total_blocks - lsb_matches) * LSB_VALUES / NON_LSB_VALUES
