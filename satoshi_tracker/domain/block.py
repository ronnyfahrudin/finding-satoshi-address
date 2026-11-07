"""Block entity: the per-block features the Patoshi analysis works on."""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Block:
    height: int
    hash: str
    time_utc: str          # "YYYY-MM-DD HH:MM:SS"
    nonce: int
    extranonce: Optional[int]
    pubkey: str            # coinbase P2PK public key (hex), "" if the output is not P2PK
    address: str           # P2PKH address of the reward key

    @property
    def nonce_lsb(self):
        return self.nonce & 0xFF
