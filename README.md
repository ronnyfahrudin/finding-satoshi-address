# Finding Satoshi's Wallet

A set of tools to:

1. **Monitor a Bitcoin address** (default: Satoshi's genesis address): its balance and transaction history.
2. **Replicate the "Patoshi pattern" analysis** to estimate which blocks and addresses Satoshi Nakamoto mined in 2009–2010, and **how much BTC each address holds**.

All data comes from the **public [mempool.space](https://mempool.space) API**. No full node, login or API key is needed. Python 3 (standard library only) and bash are enough.

> **Note:** all of this is **public, read-only data**. Knowing an address does **not** give access to its coins; that requires the private key. Beware of "tools" claiming to unlock Satoshi's wallet or other old wallets. They are all scams.

---

## Architecture (Domain-Driven Design)

```
finding-satoshi-address/
├── satoshi_tracker/                 Python package (standard library only; matplotlib for figures)
│   ├── domain/                      pure business rules, no I/O
│   │   ├── bitcoin.py               amounts, Base58Check / P2PKH address derivation, coinbase ExtraNonce parsing
│   │   ├── block.py                 Block entity
│   │   ├── patoshi.py               nonce LSB rule, ExtraNonce line classifier, Confidence, statistical estimate
│   │   ├── balance.py               RewardBalance value object, RewardStatus (no / yes / genesis)
│   │   └── flow.py                  FundFlowGraph aggregate, known addresses
│   ├── application/                 use cases (one per module), adapters injected
│   │   ├── download_blocks.py       download block features for a height range (resumable)
│   │   ├── classify_patoshi.py      apply both signals, store graded candidates
│   │   ├── check_balances.py        3-request balance check per address
│   │   ├── wallet_list.py           compact attributed-address list
│   │   ├── trace_fund_flow.py       follow moved rewards through later transactions
│   │   └── monitor_address.py       snapshot one address
│   ├── infrastructure/              adapters
│   │   ├── mempool.py               MempoolClient (retry, delay) and CachedMempoolClient (JSON cache)
│   │   └── csv_repositories.py      Block / Patoshi / Balance / WalletList / AddressHistory repositories
│   ├── interfaces/                  presentation
│   │   ├── cli.py                   `python3 -m satoshi_tracker <command>`
│   │   ├── plots.py                 ExtraNonce vs height figure
│   │   ├── pages.py                 bubble plot + fund-flow HTML pages
│   │   ├── kaggle_export.py         Kaggle dataset package
│   │   └── templates/               bubble.html, flow.html
│   └── config.py                    paths and settings (all overridable by environment)
├── scripts/run_patoshi.sh           slow, resumable, lock-protected batch runner
├── tests/test_domain.py             domain tests against ground truth (genesis, block 9, ...)
├── data/                            CSV datasets (committed)
└── output/                          generated figures, HTML, cache, logs, Kaggle package (not committed)
```

Dependencies point inwards only: `interfaces → application → domain`, with `infrastructure` implementing the
storage and API access that the use cases receive as arguments. The domain has no knowledge of HTTP or CSV.

### Commands

| Command | Does |
|---|---|
| `python3 -m satoshi_tracker scan [start end]` | download + analyze (default blocks 0–54,316) |
| `python3 -m satoshi_tracker download [start end]` | download block features only |
| `python3 -m satoshi_tracker analyze [start end]` | classify Patoshi candidates -> `data/patoshi_addresses.csv` |
| `python3 -m satoshi_tracker balance [start end]` | check balances (levels from `PATOSHI_CONFIDENCE`, default `high`) |
| `python3 -m satoshi_tracker list` | `data/satoshi_wallets.csv` |
| `python3 -m satoshi_tracker plot` | `output/plot_extranonce.png` |
| `python3 -m satoshi_tracker bubble` | `output/bubble_satoshi.html` |
| `python3 -m satoshi_tracker flow` | `output/fund_flow.html` |
| `python3 -m satoshi_tracker kaggle [--article ARTICLE.md]` | `output/kaggle_dataset/` |
| `python3 -m satoshi_tracker monitor [address] [n]` | balance and recent transactions of one address |
| `python3 -m unittest discover tests` | run the tests |

Exit codes: `0` ok, `1` API error after all retries, `2` nothing to do (used by the runner to skip a batch).

### Data files (`data/`)

| File | Content |
|---|---|
| `blocks.csv` | Raw features of every block 0–54,316 |
| `patoshi_addresses.csv` | Blocks and addresses matching the Patoshi pattern, with confidence level and balance columns |
| `balances.csv` | Balance check cache per Patoshi address (append-only) |
| `satoshi_wallets.csv` | Compact list of high + medium confidence addresses with their BTC balance |
| `balance_history.csv` | Balance history, one row per `monitor` run |
| `transactions_<address>.csv` | Recent transactions from the latest `monitor` run |

---

## Pipeline 1: Address monitor (`monitor`)

### Flow

```
mempool.space /api/address/<address>       ──► balance, total received/sent, tx count
mempool.space /api/v1/prices               ──► BTC price (USD)
mempool.space /api/address/<address>/txs   ──► recent transactions
                     │
                     ├──► printed to the terminal
                     ├──► data/balance_history.csv          (appended, one row per run)
                     └──► data/transactions_<address>.csv   (overwritten each run)
```

### Usage

```bash
python3 -m satoshi_tracker monitor                   # genesis address 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa
python3 -m satoshi_tracker monitor <address> 20      # another address, show the 20 most recent transactions
```

The API only returns the first page of history (about 25 recent transactions), so `n` above 25 adds nothing.

### CSV format

**`balance_history.csv`** (one row appended per run, useful to track balance changes over time)

| Column | Content |
|---|---|
| `checked_utc` | When the script ran (UTC) |
| `address` | The address checked |
| `balance_btc` | Confirmed balance |
| `pending_btc` | Net amount from unconfirmed transactions |
| `total_received_btc` / `total_sent_btc` | All-time totals in and out |
| `tx_count` | Number of confirmed transactions |
| `btc_price_usd` / `value_usd` | BTC price and balance value in USD (empty if the price API fails) |

**`transactions_<address>.csv`** (overwritten each run)

| Column | Content |
|---|---|
| `time_utc` | Block time (empty for pending transactions) |
| `delta_btc` | `+` means BTC came into the address, `-` means BTC left it |
| `status` | `confirmed` or `pending` |
| `txid` | Transaction ID; view it at `https://mempool.space/tx/<txid>` |

All times are **UTC**.

---

## Pipeline 2: Patoshi analysis and balances (`scan` / `balance` and `scripts/run_patoshi.sh`)

### Background

In 2009–2010, block rewards were paid directly to a *public key* (P2PK format), and the early Bitcoin software generated a new key for every block. So **every block Satoshi mined = 1 address holding 50 BTC**.

Sergio Demian Lerner (2013) found that about 22 thousand early blocks share a pattern that fits only one miner, called the **Patoshi pattern**:

- **Nonce LSB**: the last byte of the nonce only falls in the ranges **0–9** and **19–58**.
- **ExtraNonce**: its value rises in consistent sequences, separate from other miners.
- Coins from these blocks have almost never moved. The famous exception is block 9, sent to Hal Finney in block 170.

The "Satoshi Nakamoto" label at Arkham Intelligence (about 22 thousand addresses, about 1.1 million BTC) comes from this kind of analysis.

### Flow

```
                    ┌──────────────────── run_patoshi.sh ────────────────────┐
                    │  for each batch (default 500 blocks):                  │
                    │    - skip if every block is already in the CSV         │
                    │    - satoshi_tracker download <start> <end>            │
                    │    - on failure: wait 30 minutes, retry                │
                    │    - rest (default 10 minutes)                         │
                    │  when all done: satoshi_tracker analyze                │
                    └────────────────────────────────────────────────────────┘
                    ┌────────────── run_patoshi.sh balance ──────────────────┐
                    │  for each balance batch (default 1000 blocks):         │
                    │    - skip if every address is already in the cache     │
                    │    - satoshi_tracker balance <start> <end>             │
                    │    - on failure: wait 30 minutes; then rest            │
                    │  finally: satoshi_tracker analyze (final merge)        │
                    └────────────────────────────────────────────────────────┘

STAGE 1: DOWNLOAD
mempool.space /api/v1/blocks/<h>   (1 request = 10 blocks: h, h-1, ..., h-9)
        │
        ├─ nonce               ──► nonce_lsb = nonce & 0xFF
        ├─ extras.coinbaseRaw  ──► extranonce (2nd data push of the coinbase scriptSig, little-endian)
        └─ extras.coinbaseSignature "OP_PUSHBYTES_65 <pubkey> OP_CHECKSIG"
                               ──► pubkey ──► SHA256 ──► RIPEMD160 ──► Base58Check ──► 1xxx address
        │
        ▼
data/blocks.csv   (appended; blocks already present are not downloaded again)

STAGE 2: ANALYZE
blocks.csv ──► filter nonce_lsb in 0–9 or 19–58 (28,746 blocks)
           ──► ExtraNonce line analysis ──► confidence high / medium / low
           ──► patoshi_addresses.csv

STAGE 3: BALANCE (3 requests per Patoshi address)
/api/block/<hash>/txs/0       ──► coinbase txid + reward value (vout[0])
/api/tx/<txid>/outspends      ──► has the P2PK reward been spent, and by which tx
/api/address/<1xxx address>   ──► P2PKH balance (other payments to the address of the same pubkey)
        │
        ▼
balances.csv (cache, appended) ──► merged into patoshi_addresses.csv
                                   total_btc = reward (if unspent) + p2pkh_balance
```

**Why 3 requests?** The 50 BTC reward was paid in **P2PK** format (straight to the public key). Querying the `1xxx` address only counts **P2PKH** outputs, so the 50 BTC reward is **not included**. For example, block 9's address (`12cbQLTF...`) shows only about 0.44 BTC in explorers, although its reward was 50 BTC (already moved to Hal Finney). That is why the reward status is checked directly on the coinbase output.

### Usage

**Recommended: run each stage slowly in the background**

```bash
cd finding-satoshi-address
mkdir -p output

# 1. Download blocks + analyze the pattern (about 1 day)
nohup scripts/run_patoshi.sh > output/patoshi.log 2>&1 &

# 2. (optional) plot for visual verification
python3 -m satoshi_tracker plot

# 3. Check balances of "high" confidence addresses (about 2.5 days)
nohup scripts/run_patoshi.sh balance > output/patoshi_balance.log 2>&1 &

#    ...or include "medium" as well (about 2.8 days)
PATOSHI_CONFIDENCE=high,medium nohup scripts/run_patoshi.sh balance > output/patoshi_balance.log 2>&1 &
```

The two stages are deliberately separate. The balance stage needs 3 requests per address, so it is best run once the address list is clean.

| Action | Command |
|---|---|
| Watch progress | `tail -f output/patoshi.log` (or `output/patoshi_balance.log`) |
| Stop | `pkill -f run_patoshi.sh; pkill -f satoshi_tracker` |
| Resume | run the same `nohup ...` command again |
| Process status | `pgrep -af "run_patoshi\|satoshi_tracker"` |
| Count saved blocks | `echo $(( $(wc -l < data/blocks.csv) - 1 ))` |

**`scripts/run_patoshi.sh` settings** (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `START` | `0` | First block |
| `END` | `54316` | Last block (around the end of Patoshi activity) |
| `BATCH` | `500` | Blocks per batch (use a multiple of 10) |
| `PATOSHI_DELAY` | `3` | Seconds between requests |
| `REST` | `600` | Seconds of rest between batches (both stages) |
| `BATCH_BALANCE` | `1000` | Blocks per batch in the balance stage (about 400 Patoshi addresses, about 1,200 requests) |

Other settings: `PATOSHI_CONFIDENCE` (levels to check), `SATOSHI_DATA_DIR` / `SATOSHI_OUTPUT_DIR` (file locations).

Estimated duration:

| Stage | Setting | Total requests | Duration |
|---|---|---|---|
| Download | default | ~5,400 | **~24 hours** |
| Balance | `high` confidence (default) | ~59,000 | **~2.5 days** |
| Balance | `high,medium` | ~67,000 | ~2.8 days (took ~4 days in practice) |
| Download | `BATCH=300 REST=2700` | ~5,400 | ~3 days |

**Running the CLI directly (fast, no rests)**

```bash
python3 -m satoshi_tracker scan                  # download + analyze blocks 0–54316 (0.35 s delay, ~1 hour)
python3 -m satoshi_tracker scan 0 5000           # a specific range
python3 -m satoshi_tracker download 0 5000       # download only
python3 -m satoshi_tracker analyze               # analyze existing data only
python3 -m satoshi_tracker balance 0 999         # check balances of Patoshi addresses in blocks 0–999
PATOSHI_DELAY=3 python3 -m satoshi_tracker download 0 999
```

If `download` runs on a partial range, `analyze` with that range only analyzes it. Run `python3 -m satoshi_tracker analyze` (no range) to analyze all blocks 0–54,316.

### Safety features

- **Resume**: blocks already in `data/blocks.csv` are skipped. The script is safe to stop at any time.
- **Lock**: `flock` on `.run_patoshi.lock` prevents two `run_patoshi.sh` runs at once.
- **Retry**: each request is tried up to 6 times with backoff of 5, 10, 20, 40, 80 and 160 seconds. If it still fails, `run_patoshi.sh` waits 30 minutes and retries that batch.
- **Low load**: on average about 15–17 requests per minute (3 s delay plus rests between batches), read-only public data.
- **Balance cache**: checked addresses are stored in `data/balances.csv` and not checked again. Running `analyze` again does not remove the balance columns.

### CSV format

**`blocks.csv`** (and the first 8 columns of `patoshi_addresses.csv`):

| Column | Content |
|---|---|
| `height` | Block number |
| `hash` | Block hash |
| `time_utc` | Block timestamp (UTC) |
| `nonce` | Block header nonce |
| `nonce_lsb` | `nonce & 0xFF`, the basis of the Patoshi filter |
| `extranonce` | ExtraNonce from the coinbase scriptSig |
| `pubkey` | Public key receiving the reward (P2PK) |
| `address` | Bitcoin address derived from `pubkey` |
| `confidence` | Only in `patoshi_addresses.csv`: `high` / `medium` / `low`, see "ExtraNonce filter" |

**Balance columns** (in `balances.csv` and added to `patoshi_addresses.csv`; empty if the address has not been checked):

| Column | Content |
|---|---|
| `coinbase_txid` | ID of the block's coinbase (reward) transaction |
| `reward_btc` | Block reward value (usually 50 BTC) |
| `reward_spent` | `no` = still untouched; `yes` = spent; `genesis` = the block 0 reward, which the protocol makes unspendable |
| `reward_spent_txid` | Transaction that spent the reward (if `yes`) |
| `p2pkh_balance_btc` | Balance of other payments to the `1xxx` address of the same pubkey (mostly donations or "tributes") |
| `total_btc` | Wallet content = reward (if unspent) + `p2pkh_balance_btc` |
| `checked_utc` | When the balance was checked; it can change afterwards |

**`satoshi_wallets.csv`**: `address`, `balance_btc`, `reward_spent`, `status` (`checked` / `unchecked`), `height`, `block_time_utc`, `confidence`.

`blocks.csv` is not always sorted by `height` (the API returns blocks newest-first within each request). `patoshi_addresses.csv` is always sorted ascending.

### Verification performed

| Block | Address from the script | Note |
|---|---|---|
| 0 | `1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa` | Genesis address, matches |
| 9 | `12cbQLTFMXRnSzktFkuoG3eHoMeFtpTu3S` | Satoshi's address that sent BTC to Hal Finney, matches |
| 9 (balance) | `reward_spent = yes`, tx `f4184fc5...` | The Hal Finney tx in block 170, matches |
| 0 (balance) | reward 50 + P2PKH 57.7 = 107.7 BTC | The 50 BTC genesis reward is flagged `genesis` (unspendable) |

### Limitations

- The nonce LSB filter alone lets other miners in with a probability of about 50/256 (about 20%), which is why the ExtraNonce line filter below is needed.
- Above block ~30,000, Patoshi blocks become sparse and their ExtraNonce lines fragment. Some genuine Patoshi blocks from this era end up in the `low` class.
- The line filter parameters were chosen empirically. The result is close to, but **not identical** with, the Lerner/Arkham list.
- `reward_btc` is read from the first coinbase output. Early blocks have a single output, so this covers the full reward.
- The attribution is **statistical**, not proof of ownership.

---

## ExtraNonce filter and confidence levels

When ExtraNonce is plotted against height (`output/plot_extranonce.png`), Patoshi blocks form **steep lines**: ExtraNonce rises fast because it comes from one machine running continuously. Other miners form **shallow lines**. About 20% of other miners' blocks pass the LSB filter by chance, and those points sit on shallow lines.

How it works (`classify` in `satoshi_tracker/domain/patoshi.py`), on blocks that pass the LSB filter only:

1. **Anchors**: points with neighbours both before *and* after (within 15 blocks) that are collinear and steep (slope ≥ 3 ExtraNonce per block, step ≤ 80, slope ratio of both sides ≤ 2.5).
2. **High**: starting from the anchors, lines are grown repeatedly until stable. A point joins when it lies between two collinear anchor points (window 100 blocks, slope ≥ 2, step ≤ 600, ratio ≤ 3).
3. **Medium**: not high, but has at least one steep anchor neighbour (window 60, step ≤ 300).
4. **Low**: everything else.

**Results (blocks 0–54,316)**

| | Addresses | Est. false positives | Precision | Est. true Patoshi |
|---|---|---|---|---|
| Passes LSB filter | 28,746 | ~6,200 | ~78% | ~22,539 (statistical) |
| **High** confidence | **19,815** | ~196 | **~99%** | ~19,619 |
| **Medium** confidence | 2,522 | ~525 | ~79% | ~1,997 |
| **High + medium** | **22,337** | ~721 | ~97% | **~21,616** |
| Low confidence | 6,409 | most | | ~900 |

For comparison, Arkham lists about 21.9 thousand addresses and Lerner about 22 thousand blocks (about 1.1 million BTC).

**How false positives are measured**: blocks whose nonce LSB lies outside the Patoshi range (206 of 256 values) are certainly not Satoshi's. The same line filter is run on those blocks. The share that passes is multiplied by the estimated number of non-Patoshi blocks that pass the LSB filter by chance (`non-LSB blocks × 50/206`).

---

## Final results (balance snapshot 3–7 Nov 2026)

| | High | Medium | High + medium |
|---|---|---|---|
| Addresses | 19,815 | 2,522 | 22,337 |
| Reward ever spent | 207 (1.0%) | 460 (18.2%) | 667 (3.0%) |
| Total balance (BTC) | 980,409.27 | 103,170.80 | **1,083,580.07** |

- **21,669 rewards (97%) have never moved.** The total includes 77.58 BTC of P2PKH tributes (mostly on the genesis address) and the unspendable genesis reward.
- The number of spent rewards is close to the estimated false positives (207 vs ~196 in the high class, 460 vs ~525 in the medium class). This fits the idea that spent rewards mostly belong to other miners who slipped through the filter, which makes it an independent validation of the ExtraNonce filter.

---

## Interactive visualizations

```bash
python3 -m satoshi_tracker bubble    # -> output/bubble_satoshi.html
python3 -m satoshi_tracker flow      # -> output/fund_flow.html (slow: one request per new tx/address)
```

**`bubble`**: one bubble per high + medium address. x axis = block time, y axis = ExtraNonce or balance (log scale), size = balance. Color shows the reward status (untouched / moved / genesis). Includes an address search box, and clicking a bubble opens the address on mempool.space.

**`flow`**: traces every Patoshi reward that was ever moved (`reward_spent = yes` in `data/balances.csv`) and follows its transactions for a few hops. The result is a node graph (vis-network):
- circle nodes = addresses (orange = Patoshi, yellow = known recipient such as Hal Finney, blue = other address); circle size = current balance
- diamond nodes = transactions, labelled with their date (UTC); a side panel lists the transactions by date
- arrows = BTC flowing; orange when leaving a Patoshi address

| Env variable | Default | Purpose |
|---|---|---|
| `FLOW_HOP` | 2 | Trace depth |
| `FLOW_MIN_BTC` | 1 | Outputs below this value are not followed |
| `FLOW_MAX_TX` | 400 | Maximum number of transactions |
| `FLOW_BALANCE` | 1 | `0` = skip the address balance check (faster) |

API responses are cached in `output/flow_cache.json`. Delete that file to fetch fresh balances.

---

## Kaggle dataset

```bash
KAGGLE_USER=<username> python3 -m satoshi_tracker kaggle --article ARTICLE.md
kaggle datasets create -p output/kaggle_dataset                       # first upload
kaggle datasets version -p output/kaggle_dataset -m "add balances"    # later versions
```

The `kaggle` command needs an article file (`--article`, default `ARTICLE.md` in the repository root) as the dataset description; the article is not included in this repository. The command renames columns for the dataset (`block_hash`, `timestamp_utc`, `coinbase_pubkey`, ...), draws the pipeline and histogram figures, and computes `SHA256SUMS`. Balance columns in `patoshi_addresses.csv` are included automatically once every high + medium address has been checked.

---

## References

- Sergio Demian Lerner, *The Well Deserved Fortune of Satoshi Nakamoto* (2013) and follow-up "Patoshi pattern" research, at bitslog.com
- mempool.space API: https://mempool.space/docs/api/rest
