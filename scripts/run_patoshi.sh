#!/usr/bin/env bash
# Patoshi pipeline, run slowly in batches. Two separate stages:
#   scripts/run_patoshi.sh           download blocks 0..54316, then analyze the Patoshi pattern
#   scripts/run_patoshi.sh balance   check what each address in data/patoshi_addresses.csv holds (BTC)
#                                    (default "high" confidence only; add "medium" with
#                                    PATOSHI_CONFIDENCE=high,medium scripts/run_patoshi.sh balance)
#
# Run in the background (keeps running after the terminal is closed):
#   nohup scripts/run_patoshi.sh > output/patoshi.log 2>&1 &
#   nohup scripts/run_patoshi.sh balance > output/patoshi_balance.log 2>&1 &
# Progress:  tail -f output/patoshi.log
# Stop:      pkill -f run_patoshi.sh; pkill -f satoshi_tracker
# Safe to stop at any time; run again to resume from the last block.
#
# Download stage: 500 blocks per batch (50 requests), 3 s delay, 10-minute rest
#                 =>  ~109 batches, about 24 hours.
# Balance stage:  1000 blocks per batch, 3 requests per address, 3 s delay, 10-minute rest
#                 =>  ~19,800 "high" addresses (~59,000 requests), about 2.5 days.
# Override via environment, e.g.:  BATCH=300 REST=1800 scripts/run_patoshi.sh

set -u
cd "$(dirname "$0")/.."

START=${START:-0}
END=${END:-54316}
BATCH=${BATCH:-500}          # blocks per batch (multiple of 10)
REST=${REST:-600}            # seconds of rest between batches
BATCH_BALANCE=${BATCH_BALANCE:-1000}  # blocks per batch in the balance stage
export PATOSHI_DELAY=${PATOSHI_DELAY:-3}

# prevent two runs at the same time
exec 9> .run_patoshi.lock
if ! flock -n 9; then
    echo "run_patoshi.sh is already running, exiting."
    exit 1
fi

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

have_range() {
    # are all blocks in $1..$2 already in data/blocks.csv
    [ -f data/blocks.csv ] || return 1
    local n
    n=$(awk -F, -v a="$1" -v b="$2" 'NR>1 && $1>=a && $1<=b' data/blocks.csv | wc -l)
    [ "$n" -ge $(( $2 - $1 + 1 )) ]
}

STAGE=${1:-download}
case "$STAGE" in
    download|balance) ;;
    *) echo "Usage: $0 [download|balance]"; exit 1 ;;
esac

if [ "$STAGE" = download ]; then
log "Start: blocks $START-$END, batch $BATCH, delay ${PATOSHI_DELAY}s/request, rest ${REST}s"

for (( a=START; a<=END; a+=BATCH )); do
    b=$(( a + BATCH - 1 ))
    (( b > END )) && b=$END

    if have_range "$a" "$b"; then
        continue
    fi

    log "Batch $a-$b"
    until python3 -u -m satoshi_tracker download "$a" "$b"; do
        log "Batch $a-$b failed, retrying in 30 minutes"
        sleep 1800
    done

    (( b < END )) && { log "Resting ${REST}s"; sleep "$REST"; }
done

log "Download finished, analyzing..."
python3 -m satoshi_tracker analyze "$START" "$END"
log "Done. Continue with: scripts/run_patoshi.sh balance"
exit 0
fi

[ -f data/patoshi_addresses.csv ] || { log "data/patoshi_addresses.csv not found, run the download stage first"; exit 1; }
log "Start checking Patoshi address balances"
for (( a=START; a<=END; a+=BATCH_BALANCE )); do
    b=$(( a + BATCH_BALANCE - 1 ))
    (( b > END )) && b=$END

    # exit code 2 = every address in this batch is already checked, skip without resting
    while true; do
        python3 -u -m satoshi_tracker balance "$a" "$b"
        rc=$?
        { [ "$rc" -eq 0 ] || [ "$rc" -eq 2 ]; } && break
        log "Balance batch $a-$b failed, retrying in 30 minutes"
        sleep 1800
    done
    [ "$rc" -eq 2 ] && continue

    (( b < END )) && { log "Resting ${REST}s"; sleep "$REST"; }
done

python3 -m satoshi_tracker analyze "$START" "$END"
log "Done."
