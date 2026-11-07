"""Use case: apply both Patoshi signals to the downloaded blocks and store the graded candidates."""
from dataclasses import dataclass

from ..domain import patoshi


@dataclass
class ClassificationReport:
    blocks: int
    lsb_matches: int
    estimated_patoshi: float
    by_confidence: dict


def classify_patoshi(blocks, candidates_repo, balances, start, end):
    rows = sorted((b for b in blocks.all() if start <= b.height <= end), key=lambda b: b.height)
    matches = [b for b in rows if patoshi.matches_nonce_lsb(b.nonce_lsb)]
    candidates = patoshi.classify(matches)
    candidates_repo.save(candidates, balances.by_height())
    return ClassificationReport(
        blocks=len(rows),
        lsb_matches=len(matches),
        estimated_patoshi=patoshi.estimate_true_patoshi(len(rows), len(matches)),
        by_confidence={c: sum(x.confidence == c for x in candidates) for c in patoshi.Confidence},
    )
