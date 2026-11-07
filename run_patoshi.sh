#!/usr/bin/env bash
# Pipeline Patoshi, dijalankan pelan per batch. Dua tahap terpisah:
#   ./run_patoshi.sh         unduh blok 0..54316 lalu analisa pola Patoshi
#   ./run_patoshi.sh saldo   cek isi (saldo BTC) alamat di alamat_patoshi.csv
#                            (default hanya keyakinan "tinggi"; tambah "sedang" dengan
#                            PATOSHI_KEYAKINAN=tinggi,sedang ./run_patoshi.sh saldo)
#
# Jalankan di background (tetap jalan walau terminal ditutup):
#   nohup ./run_patoshi.sh > patoshi.log 2>&1 &
#   nohup ./run_patoshi.sh saldo > patoshi_saldo.log 2>&1 &
# Lihat progres:   tail -f patoshi.log
# Hentikan:        pkill -f run_patoshi.sh; pkill -f patoshi_scan.py
# Aman dihentikan kapan saja; jalankan ulang untuk melanjutkan dari blok terakhir.
#
# Tahap unduh : 500 blok per batch (50 request), jeda 3 detik, istirahat 10 menit
#               =>  ~109 batch, sekitar 24 jam.
# Tahap saldo  : 1000 blok per batch, 3 request per alamat, jeda 3 detik, istirahat 10 menit
#               =>  ~19.800 alamat "tinggi" (~59.000 request), sekitar 2,5 hari.
# Ubah lewat environment, misal:  BATCH=300 ISTIRAHAT=1800 ./run_patoshi.sh

set -u
cd "$(dirname "$0")"

AWAL=${AWAL:-0}
AKHIR=${AKHIR:-54316}
BATCH=${BATCH:-500}          # blok per batch (kelipatan 10)
ISTIRAHAT=${ISTIRAHAT:-600}  # detik istirahat antar batch
BATCH_SALDO=${BATCH_SALDO:-1000}  # blok per batch di tahap saldo
export PATOSHI_JEDA=${PATOSHI_JEDA:-3}

# cegah dua proses berjalan bersamaan
exec 9> .run_patoshi.lock
if ! flock -n 9; then
    echo "run_patoshi.sh sudah berjalan, keluar."
    exit 1
fi

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

sudah_ada() {
    # cek apakah semua blok di rentang $1..$2 sudah ada di blok_awal.csv
    [ -f blok_awal.csv ] || return 1
    local n
    n=$(awk -F, -v a="$1" -v b="$2" 'NR>1 && $1>=a && $1<=b' blok_awal.csv | wc -l)
    [ "$n" -ge $(( $2 - $1 + 1 )) ]
}

TAHAP=${1:-unduh}
case "$TAHAP" in
    unduh|saldo) ;;
    *) echo "Pemakaian: $0 [unduh|saldo]"; exit 1 ;;
esac

if [ "$TAHAP" = unduh ]; then
log "Mulai: blok $AWAL-$AKHIR, batch $BATCH, jeda ${PATOSHI_JEDA}s/request, istirahat ${ISTIRAHAT}s"

for (( a=AWAL; a<=AKHIR; a+=BATCH )); do
    b=$(( a + BATCH - 1 ))
    (( b > AKHIR )) && b=$AKHIR

    if sudah_ada "$a" "$b"; then
        continue
    fi

    log "Batch $a-$b"
    until python3 -u patoshi_scan.py unduh "$a" "$b"; do
        log "Batch $a-$b gagal, coba lagi dalam 30 menit"
        sleep 1800
    done

    (( b < AKHIR )) && { log "Istirahat ${ISTIRAHAT}s"; sleep "$ISTIRAHAT"; }
done

log "Unduhan selesai, menganalisa..."
python3 patoshi_scan.py analisa "$AWAL" "$AKHIR"
log "Selesai. Lanjutkan dengan: ./run_patoshi.sh saldo"
exit 0
fi

[ -f alamat_patoshi.csv ] || { log "alamat_patoshi.csv belum ada, jalankan tahap unduh dulu"; exit 1; }
log "Mulai cek saldo alamat Patoshi"
for (( a=AWAL; a<=AKHIR; a+=BATCH_SALDO )); do
    b=$(( a + BATCH_SALDO - 1 ))
    (( b > AKHIR )) && b=$AKHIR

    # exit code 2 = semua alamat di batch ini sudah dicek, lewati tanpa istirahat
    while true; do
        python3 -u patoshi_scan.py saldo "$a" "$b"
        rc=$?
        { [ "$rc" -eq 0 ] || [ "$rc" -eq 2 ]; } && break
        log "Saldo batch $a-$b gagal, coba lagi dalam 30 menit"
        sleep 1800
    done
    [ "$rc" -eq 2 ] && continue

    (( b < AKHIR )) && { log "Istirahat ${ISTIRAHAT}s"; sleep "$ISTIRAHAT"; }
done

python3 patoshi_scan.py analisa "$AWAL" "$AKHIR"
log "Selesai."
