"""Use case: compact list of high + medium confidence addresses with their balance."""
from ..domain.patoshi import Confidence

ATTRIBUTED = (Confidence.HIGH, Confidence.MEDIUM)


def attributed_with_balance(candidates_repo, balances):
    by_height = balances.by_height()
    return [(c, by_height.get(c.block.height)) for c in candidates_repo.all() if c.confidence in ATTRIBUTED]


def build_wallet_list(candidates_repo, balances, wallets):
    entries = attributed_with_balance(candidates_repo, balances)
    wallets.save(entries)
    return entries
