"""Read-only client for the public mempool.space REST API."""
import json
import os
import time
import urllib.error
import urllib.request

API = "https://mempool.space/api"


class ApiError(RuntimeError):
    pass


class MempoolClient:
    def __init__(self, delay=0.0, retries=6, base=API, user_agent="satoshi-tracker/2.0"):
        self.delay = delay          # pause after every request, to stay polite and avoid rate limits
        self.retries = retries
        self.base = base
        self.user_agent = user_agent

    def get(self, path):
        for attempt in range(self.retries):
            try:
                req = urllib.request.Request(self.base + path, headers={"User-Agent": self.user_agent})
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.loads(r.read())
                time.sleep(self.delay)
                return data
            except (urllib.error.URLError, TimeoutError) as e:
                wait = 2 ** attempt * 5
                print(f"\n  error on {path} ({e}), retrying in {wait}s")
                time.sleep(wait)
        raise ApiError(f"Failed to fetch {path}, run again to resume.")

    def blocks_down_from(self, height):
        """Blocks height, height-1, ..., height-9."""
        return self.get(f"/v1/blocks/{height}")

    def coinbase_tx(self, block_hash):
        return self.get(f"/block/{block_hash}/txs/0")[0]

    def tx(self, txid):
        return self.get(f"/tx/{txid}")

    def outspends(self, txid):
        return self.get(f"/tx/{txid}/outspends")

    def address(self, address):
        return self.get(f"/address/{address}")

    def address_txs(self, address):
        return self.get(f"/address/{address}/txs")

    def prices(self):
        return self.get("/v1/prices")


class CachedMempoolClient(MempoolClient):
    """Keeps every response in a JSON file; only cache misses hit the API (and pay the delay)."""

    def __init__(self, cache_path, **kwargs):
        super().__init__(**kwargs)
        self.cache_path = cache_path
        self.cache = {}
        if os.path.exists(cache_path):
            with open(cache_path) as f:
                self.cache = json.load(f)

    def get(self, path):
        if path not in self.cache:
            self.cache[path] = super().get(path)
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            with open(self.cache_path, "w") as f:
                json.dump(self.cache, f)
        return self.cache[path]
