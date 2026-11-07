"""Command-line interface: wires the adapters into the use cases and prints the results.

    python3 -m satoshi_tracker scan [start end]       download + analyze (blocks 0..54316)
    python3 -m satoshi_tracker download [start end]   download block features only
    python3 -m satoshi_tracker analyze [start end]    classify Patoshi candidates
    python3 -m satoshi_tracker balance [start end]    check balances (PATOSHI_CONFIDENCE, default high)
    python3 -m satoshi_tracker list                   data/satoshi_wallets.csv
    python3 -m satoshi_tracker plot                   output/plot_extranonce.png
    python3 -m satoshi_tracker bubble                 output/bubble_satoshi.html
    python3 -m satoshi_tracker flow                   output/fund_flow.html (FLOW_* settings)
    python3 -m satoshi_tracker kaggle [--article A]   output/kaggle_dataset/
    python3 -m satoshi_tracker monitor [address] [n]  balance + recent transactions of one address

Exit codes: 0 ok, 1 error, 2 nothing to do (balance: every address in the range is already checked).
"""
import argparse
import os
import sys

from .. import config
from ..application.check_balances import check_balances, pending_targets, summarize
from ..application.classify_patoshi import classify_patoshi
from ..application.download_blocks import download_blocks
from ..application.monitor_address import monitor_address
from ..application.trace_fund_flow import trace_fund_flow
from ..application.wallet_list import attributed_with_balance, build_wallet_list
from ..domain.bitcoin import GENESIS_ADDRESS, SATS
from ..domain.patoshi import BLOCK_REWARD_BTC
from ..infrastructure.csv_repositories import (AddressHistoryRepository, BalanceRepository, BlockRepository,
                                               PatoshiRepository, WalletListRepository)
from ..infrastructure.mempool import ApiError, CachedMempoolClient, MempoolClient

NOTHING_TO_DO = 2


def btc(sats):
    return f"{sats / SATS:,.8f} BTC"


def counter(unit):
    def show(done, total):
        print(f"\r  {done:,}/{total:,} {unit}", end="", flush=True)
    return show


def repos():
    return (BlockRepository(config.BLOCKS_CSV), PatoshiRepository(config.PATOSHI_CSV),
            BalanceRepository(config.BALANCES_CSV))


def print_summary(s):
    if s.checked:
        print(f"Balances checked : {s.checked:,}/{s.candidates:,} addresses")
        print(f"Reward unspent   : {s.unspent:,} addresses")
        print(f"Total held       : {s.total_sats / SATS:,.8f} BTC (checked addresses only)")


def cmd_download(a):
    blocks, _, _ = repos()
    print(f"Downloading blocks {a.start}-{a.end} from mempool.space ...")
    download_blocks(MempoolClient(delay=config.DELAY), blocks, a.start, a.end, counter("blocks"))
    print()


def cmd_analyze(a):
    blocks, candidates, balances = repos()
    r = classify_patoshi(blocks, candidates, balances, a.start, a.end)
    print(f"Blocks analyzed  : {r.blocks:,} (blocks {a.start}-{a.end})")
    print(f"Nonce LSB match  : {r.lsb_matches:,} blocks / addresses")
    print(f"Estimated true Patoshi (statistical): ~{r.estimated_patoshi:,.0f} blocks "
          f"(~{r.estimated_patoshi * BLOCK_REWARD_BTC:,.0f} BTC)")
    for level, n in r.by_confidence.items():
        print(f"  confidence {level.value:<6}: {n:>6,} addresses ({n * BLOCK_REWARD_BTC:,} BTC)")
    print_summary(summarize(candidates.all(), balances.by_height()))
    print(f"Saved            : {config.PATOSHI_CSV}")


def cmd_scan(a):
    cmd_download(a)
    cmd_analyze(a)


def cmd_balance(a):
    _, candidates, balances = repos()
    targets = pending_targets(candidates.all(), balances.by_height(), a.start, a.end, config.CONFIDENCE)
    if not targets:
        return NOTHING_TO_DO
    print(f"Checking balances of {len(targets):,} {'/'.join(config.CONFIDENCE)} confidence addresses "
          f"(blocks {a.start}-{a.end}) ...")
    summary = check_balances(MempoolClient(delay=config.DELAY), candidates, balances, targets, counter("addresses"))
    print()
    print_summary(summary)
    return 0


def cmd_list(a):
    _, candidates, balances = repos()
    entries = build_wallet_list(candidates, balances, WalletListRepository(config.WALLETS_CSV))
    checked = [s for _, s in entries if s]
    print(f"Addresses (high+medium): {len(entries):,}")
    print(f"Balances checked       : {len(checked):,} ({len(checked) / len(entries):.1%})")
    print(f"Total checked balance  : {sum(s.total_sats for s in checked) / SATS:,.8f} BTC")
    print(f"Saved                  : {config.WALLETS_CSV}")


def cmd_plot(a):
    from .plots import extranonce_plot
    blocks, candidates, _ = repos()
    extranonce_plot(blocks.all(), candidates.all(), config.PLOT_PNG)
    print(f"Saved            : {config.PLOT_PNG}")


def cmd_bubble(a):
    from .pages import bubble_page
    _, candidates, balances = repos()
    data = bubble_page(attributed_with_balance(candidates, balances), config.BUBBLE_HTML)
    print(f"Addresses : {len(data):,} ({sum(d['s'] != 'unchecked' for d in data):,} balances checked)")
    print(f"File size : {os.path.getsize(config.BUBBLE_HTML) / 1e6:.2f} MB")
    print(f"Saved     : {config.BUBBLE_HTML}")


def cmd_flow(a):
    from .pages import flow_page
    _, candidates, balances = repos()
    client = CachedMempoolClient(config.FLOW_CACHE, delay=config.FLOW_DELAY)

    def progress(what, done, total):
        print(f"\r  {what}: {done:,}" + (f"/{total:,}" if total else ""), end="", flush=True)

    graph, meta = trace_fund_flow(client, candidates, balances, config.FLOW_HOP, config.FLOW_MIN_BTC,
                                  config.FLOW_MAX_TX, config.FLOW_BALANCE, progress)
    print()
    flow_page(graph, meta, config.FLOW_HTML)
    print(f"Moved rewards : {meta['spent_rewards']} (out of {meta['checked']:,} checked addresses)")
    print(f"Nodes         : {len(graph.nodes):,} {graph.kinds()}")
    print(f"Edges         : {len(graph.edges):,}")
    print(f"Saved         : {config.FLOW_HTML}")


def cmd_kaggle(a):
    from .kaggle_export import export
    blocks, candidates, balances = repos()
    complete, base = export(blocks.all(), candidates.all(), balances.by_height(), config.PLOT_PNG,
                            a.article, config.KAGGLE_DIR, os.environ.get("KAGGLE_USER", "<username-kaggle>"))
    print(f"Folder         : {config.KAGGLE_DIR}")
    print(f"Balance columns: {'included' if complete else 'not yet (balance stage not finished)'}")
    print(f"LSB background : {base:.1f} blocks per value")
    for name in sorted(os.listdir(config.KAGGLE_DIR)):
        print(f"  {os.path.getsize(os.path.join(config.KAGGLE_DIR, name)) / 1e6:8.2f} MB  {name}")


def cmd_monitor(a):
    history = AddressHistoryRepository(config.BALANCE_HISTORY_CSV, config.transactions_csv)
    s = monitor_address(MempoolClient(), history, a.address, a.n)
    print(f"Address         : {s.address}")
    print(f"Balance         : {btc(s.balance_sats)}")
    if s.pending_sats:
        print(f"Pending mempool : {btc(s.pending_sats)}")
    print(f"Total received  : {btc(s.received_sats)}")
    print(f"Total sent      : {btc(s.sent_sats)}")
    print(f"Transactions    : {s.tx_count:,}")
    if s.usd:
        print(f"Current value   : ${s.balance_sats / SATS * s.usd:,.2f} (1 BTC = ${s.usd:,})")
    print(f"\n{len(s.transactions)} most recent transactions:")
    for t in s.transactions:
        print(f"  {t['time_utc'] or 'unconfirmed':<16}  {t['delta_btc']} BTC  {t['txid']}")
    print(f"\nSaved: {s.history_path}")
    print(f"Saved: {s.transactions_path}")


def parser():
    p = argparse.ArgumentParser(prog="satoshi_tracker", description="Patoshi pattern attribution of early Bitcoin blocks")
    sub = p.add_subparsers(dest="command", required=True)

    def ranged(name, func, help):
        s = sub.add_parser(name, help=help)
        s.add_argument("start", type=int, nargs="?", default=0)
        s.add_argument("end", type=int, nargs="?", default=config.LAST_BLOCK)
        s.set_defaults(func=func)

    ranged("scan", cmd_scan, "download + analyze")
    ranged("download", cmd_download, "download block features")
    ranged("analyze", cmd_analyze, "classify Patoshi candidates")
    ranged("balance", cmd_balance, "check balances of Patoshi addresses")
    for name, func, help in [("list", cmd_list, "write data/satoshi_wallets.csv"),
                             ("plot", cmd_plot, "ExtraNonce vs height figure"),
                             ("bubble", cmd_bubble, "interactive bubble plot"),
                             ("flow", cmd_flow, "interactive fund-flow graph")]:
        sub.add_parser(name, help=help).set_defaults(func=func)
    k = sub.add_parser("kaggle", help="build the Kaggle dataset package")
    k.add_argument("--article", default=os.path.join(config.ROOT, "ARTICLE.md"), help="dataset description (markdown)")
    k.set_defaults(func=cmd_kaggle)
    m = sub.add_parser("monitor", help="balance and recent transactions of one address")
    m.add_argument("address", nargs="?", default=GENESIS_ADDRESS)
    m.add_argument("n", type=int, nargs="?", default=10, help="number of recent transactions (max ~25)")
    m.set_defaults(func=cmd_monitor)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return args.func(args) or 0
    except ApiError as e:
        print(f"\n{e}", file=sys.stderr)
        return 1
