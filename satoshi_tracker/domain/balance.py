"""What a Patoshi address holds: the block reward (P2PK) plus later P2PKH deposits."""
from dataclasses import dataclass
from enum import Enum


class RewardStatus(str, Enum):
    UNSPENT = "no"
    SPENT = "yes"
    GENESIS = "genesis"    # block 0: never entered the UTXO set, so it can never be spent


@dataclass(frozen=True)
class RewardBalance:
    height: int
    address: str
    coinbase_txid: str
    reward_sats: int
    status: RewardStatus
    spent_txid: str
    p2pkh_sats: int        # later payments to the P2PKH address of the same key ("tributes")
    checked_utc: str

    @property
    def total_sats(self):
        return (0 if self.status == RewardStatus.SPENT else self.reward_sats) + self.p2pkh_sats


def reward_status(height, spent):
    if spent:
        return RewardStatus.SPENT
    return RewardStatus.GENESIS if height == 0 else RewardStatus.UNSPENT
