"""Use case: download block features for a height range (resumable)."""
from datetime import datetime, timezone

from ..domain.bitcoin import parse_extranonce, pubkey_to_address
from ..domain.block import Block


def block_from_api(b):
    ex = b["extras"]
    pubkey = ""
    address = ex.get("coinbaseAddress") or ""
    sig = (ex.get("coinbaseSignature") or "").split()
    if len(sig) == 3 and sig[0].startswith("OP_PUSHBYTES_") and sig[2] == "OP_CHECKSIG":
        pubkey = sig[1]
        address = address or pubkey_to_address(pubkey)
    return Block(
        height=b["height"],
        hash=b["id"],
        time_utc=datetime.fromtimestamp(b["timestamp"], timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        nonce=b["nonce"],
        extranonce=parse_extranonce(ex.get("coinbaseRaw") or ""),
        pubkey=pubkey,
        address=address,
    )


def download_blocks(client, blocks, start, end, progress=print):
    have = blocks.heights()
    with blocks.appender() as add:
        # the endpoint returns blocks h, h-1, ..., h-9
        for top in range(start + 9, end + 10, 10):
            need = {h for h in range(top - 9, top + 1) if start <= h <= end} - have
            if not need:
                continue
            for b in client.blocks_down_from(top):
                if b["height"] in need:
                    add(block_from_api(b))
                    have.add(b["height"])
            progress(len([h for h in have if start <= h <= end]), end - start + 1)
