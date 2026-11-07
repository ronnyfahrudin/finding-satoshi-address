"""Bitcoin primitives: amounts, address derivation and coinbase parsing."""
import hashlib
from decimal import Decimal

SATS = 100_000_000
GENESIS_ADDRESS = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def format_btc(sats):
    """Satoshis -> fixed 8-decimal BTC string, the format used in every CSV."""
    return f"{sats / SATS:.8f}"


def parse_btc(text):
    """8-decimal BTC string -> exact satoshis."""
    return int(Decimal(text) * SATS)


def base58check(payload):
    data = payload + hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    n = int.from_bytes(data, "big")
    s = ""
    while n:
        n, r = divmod(n, 58)
        s = _B58[r] + s
    return "1" * (len(data) - len(data.lstrip(b"\0"))) + s


def pubkey_to_address(pubkey_hex):
    """P2PKH address of a public key: Base58Check(0x00 + RIPEMD160(SHA256(pubkey)))."""
    h160 = hashlib.new("ripemd160", hashlib.sha256(bytes.fromhex(pubkey_hex)).digest()).digest()
    return base58check(b"\0" + h160)


def parse_extranonce(coinbase_hex):
    """ExtraNonce from an early coinbase scriptSig: <push 4-byte bits> <push extranonce> ...

    Returns None when the script does not have that shape.
    """
    b = bytes.fromhex(coinbase_hex)
    if len(b) < 6:
        return None
    i = 1 + b[0]
    if i >= len(b):
        return None
    n = b[i]
    return int.from_bytes(b[i + 1:i + 1 + n], "little") if 1 <= n <= 8 else None


def script_address(scriptpubkey_hex, script_type, address=None):
    """Address an output pays to. Raw P2PK outputs are mapped to the P2PKH address of their key."""
    if address:
        return address
    if script_type == "p2pk" and scriptpubkey_hex.endswith("ac"):
        return pubkey_to_address(scriptpubkey_hex[2:-2])
    return f"script:{scriptpubkey_hex[:16]}"
