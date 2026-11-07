"""Use case: find out what each Patoshi address holds.

A plain address lookup misses the 50 BTC reward, because the reward sits in a P2PK output while
address indexes count P2PKH. So each address needs three requests: the coinbase transaction, whether
its reward output was ever spent, and the P2PKH balance of the same key.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from ..domain.balance import RewardBalance, RewardStatus, reward_status


@dataclass
class BalanceSummary:
    candidates: int
    checked: int
    unspent: int
    total_sats: int


def check_reward(client, block):
    cb = client.coinbase_tx(block.hash)
    out = client.outspends(cb["txid"])[0]
    stats = client.address(block.address)["chain_stats"]
    return RewardBalance(
        height=block.height,
        address=block.address,
        coinbase_txid=cb["txid"],
        reward_sats=cb["vout"][0]["value"],
        status=reward_status(block.height, out.get("spent")),
        spent_txid=out.get("txid", ""),
        p2pkh_sats=stats["funded_txo_sum"] - stats["spent_txo_sum"],
        checked_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    )


def pending_targets(candidates, done, start, end, levels):
    return [c for c in candidates
            if start <= c.block.height <= end and c.confidence.value in levels and c.block.height not in done]


def check_balances(client, candidates_repo, balances, targets, progress=print):
    """Check the given candidates, then re-merge balances into the candidates file."""
    with balances.appender() as add:
        for i, c in enumerate(targets, 1):
            add(check_reward(client, c.block))
            progress(i, len(targets))
    return refresh_candidates(candidates_repo, balances)


def refresh_candidates(candidates_repo, balances):
    candidates = candidates_repo.all()
    by_height = balances.by_height()
    candidates_repo.save(candidates, by_height)
    return summarize(candidates, by_height)


def summarize(candidates, by_height):
    checked = [by_height[c.block.height] for c in candidates if c.block.height in by_height]
    return BalanceSummary(
        candidates=len(candidates),
        checked=len(checked),
        unspent=sum(s.status == RewardStatus.UNSPENT for s in checked),
        total_sats=sum(s.total_sats for s in checked),
    )
