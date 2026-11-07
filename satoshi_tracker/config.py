"""File locations and tunables. Every value can be overridden through the environment."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("SATOSHI_DATA_DIR", os.path.join(ROOT, "data"))
OUTPUT_DIR = os.environ.get("SATOSHI_OUTPUT_DIR", os.path.join(ROOT, "output"))

BLOCKS_CSV = os.path.join(DATA_DIR, "blocks.csv")
PATOSHI_CSV = os.path.join(DATA_DIR, "patoshi_addresses.csv")
BALANCES_CSV = os.path.join(DATA_DIR, "balances.csv")
WALLETS_CSV = os.path.join(DATA_DIR, "satoshi_wallets.csv")
BALANCE_HISTORY_CSV = os.path.join(DATA_DIR, "balance_history.csv")

PLOT_PNG = os.path.join(OUTPUT_DIR, "plot_extranonce.png")
BUBBLE_HTML = os.path.join(OUTPUT_DIR, "bubble_satoshi.html")
FLOW_HTML = os.path.join(OUTPUT_DIR, "fund_flow.html")
FLOW_CACHE = os.path.join(OUTPUT_DIR, "flow_cache.json")
KAGGLE_DIR = os.path.join(OUTPUT_DIR, "kaggle_dataset")

LAST_BLOCK = 54316                                              # around the end of Patoshi mining
DELAY = float(os.environ.get("PATOSHI_DELAY", 0.35))            # seconds between API requests
CONFIDENCE = os.environ.get("PATOSHI_CONFIDENCE", "high").split(",")

FLOW_HOP = int(os.environ.get("FLOW_HOP", 2))
FLOW_MIN_BTC = float(os.environ.get("FLOW_MIN_BTC", 1))
FLOW_MAX_TX = int(os.environ.get("FLOW_MAX_TX", 400))
FLOW_BALANCE = os.environ.get("FLOW_BALANCE", "1") != "0"
FLOW_DELAY = 3  # same as the balance stage, which may be running at the same time


def transactions_csv(address):
    return os.path.join(DATA_DIR, f"transactions_{address}.csv")
