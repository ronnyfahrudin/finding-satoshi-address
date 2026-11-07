"""CSV-backed repositories. They map rows to domain objects and back, keeping the file formats stable."""
import csv
import os
from contextlib import contextmanager

from ..domain.balance import RewardBalance, RewardStatus
from ..domain.bitcoin import format_btc, parse_btc
from ..domain.block import Block
from ..domain.patoshi import Confidence, PatoshiCandidate

BLOCK_FIELDS = ["height", "hash", "time_utc", "nonce", "nonce_lsb", "extranonce", "pubkey", "address"]
BALANCE_FIELDS = [
    "coinbase_txid", "reward_btc", "reward_spent", "reward_spent_txid",
    "p2pkh_balance_btc", "total_btc", "checked_utc",
]


def _read(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _write(path, fields, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


@contextmanager
def _appender(path, fields, to_row):
    """Yields add(obj): appends one row and flushes, so an interrupted run loses nothing."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new:
            w.writeheader()

        def add(obj):
            w.writerow(to_row(obj))
            f.flush()

        yield add


def block_to_row(b):
    return {
        "height": b.height,
        "hash": b.hash,
        "time_utc": b.time_utc,
        "nonce": b.nonce,
        "nonce_lsb": b.nonce_lsb,
        "extranonce": "" if b.extranonce is None else b.extranonce,
        "pubkey": b.pubkey,
        "address": b.address,
    }


def row_to_block(r):
    return Block(
        height=int(r["height"]),
        hash=r["hash"],
        time_utc=r["time_utc"],
        nonce=int(r["nonce"]),
        extranonce=int(r["extranonce"]) if r["extranonce"] else None,
        pubkey=r["pubkey"],
        address=r["address"],
    )


def balance_to_row(s):
    return {
        "height": s.height,
        "address": s.address,
        "coinbase_txid": s.coinbase_txid,
        "reward_btc": format_btc(s.reward_sats),
        "reward_spent": s.status.value,
        "reward_spent_txid": s.spent_txid,
        "p2pkh_balance_btc": format_btc(s.p2pkh_sats),
        "total_btc": format_btc(s.total_sats),
        "checked_utc": s.checked_utc,
    }


def row_to_balance(r):
    return RewardBalance(
        height=int(r["height"]),
        address=r["address"],
        coinbase_txid=r["coinbase_txid"],
        reward_sats=parse_btc(r["reward_btc"]),
        status=RewardStatus(r["reward_spent"]),
        spent_txid=r["reward_spent_txid"],
        p2pkh_sats=parse_btc(r["p2pkh_balance_btc"]),
        checked_utc=r["checked_utc"],
    )


class BlockRepository:
    """blocks.csv: every downloaded block, append-only (not necessarily sorted)."""

    def __init__(self, path):
        self.path = path

    def all(self):
        return [row_to_block(r) for r in _read(self.path)]

    def heights(self):
        return {int(r["height"]) for r in _read(self.path)}

    def appender(self):
        return _appender(self.path, BLOCK_FIELDS, block_to_row)


class BalanceRepository:
    """balances.csv: balance check results, append-only cache keyed by block height."""

    def __init__(self, path):
        self.path = path

    def by_height(self):
        return {s.height: s for s in map(row_to_balance, _read(self.path))}

    def appender(self):
        return _appender(self.path, ["height", "address"] + BALANCE_FIELDS, balance_to_row)


class PatoshiRepository:
    """patoshi_addresses.csv: LSB-matching blocks with confidence, merged with balances where checked."""

    def __init__(self, path):
        self.path = path

    def all(self):
        return [PatoshiCandidate(row_to_block(r), Confidence(r["confidence"])) for r in _read(self.path)]

    def save(self, candidates, balances):
        rows = []
        for c in candidates:
            s = balances.get(c.block.height)
            extra = {k: v for k, v in balance_to_row(s).items() if k in BALANCE_FIELDS} if s else dict.fromkeys(BALANCE_FIELDS, "")
            rows.append({**block_to_row(c.block), "confidence": c.confidence.value, **extra})
        _write(self.path, BLOCK_FIELDS + ["confidence"] + BALANCE_FIELDS, rows)


class WalletListRepository:
    """satoshi_wallets.csv: compact address + balance list of the high and medium classes."""

    FIELDS = ["address", "balance_btc", "reward_spent", "status", "height", "block_time_utc", "confidence"]

    def __init__(self, path):
        self.path = path

    def save(self, entries):
        rows = [{
            "address": c.block.address,
            "balance_btc": format_btc(s.total_sats) if s else "",
            "reward_spent": s.status.value if s else "",
            "status": "checked" if s else "unchecked",
            "height": c.block.height,
            "block_time_utc": c.block.time_utc,
            "confidence": c.confidence.value,
        } for c, s in entries]
        _write(self.path, self.FIELDS, rows)


class AddressHistoryRepository:
    """balance_history.csv (one row per monitor run) and transactions_<address>.csv (latest run)."""

    def __init__(self, history_path, transactions_path_for):
        self.history_path = history_path
        self.transactions_path_for = transactions_path_for

    def append_snapshot(self, row):
        with _appender(self.history_path, list(row), lambda r: r) as add:
            add(row)
        return self.history_path

    def save_transactions(self, address, rows):
        path = self.transactions_path_for(address)
        _write(path, ["time_utc", "delta_btc", "status", "txid"], rows)
        return path
