# Tracker Satoshi

Kumpulan tool untuk:

1. **Memantau alamat Bitcoin** (default: alamat genesis Satoshi), yaitu saldo dan riwayat transaksinya.
2. **Mereplikasi analisis "Patoshi pattern"** untuk memperkirakan blok dan alamat yang ditambang Satoshi Nakamoto di tahun 2009–2010, sekaligus **isi (saldo BTC) setiap alamatnya**.

Semua data diambil dari **API publik [mempool.space](https://mempool.space)**. Tidak perlu full node, login, atau API key. Cukup Python 3 (library bawaan saja) dan bash.

> **Catatan:** semua data ini hanya **data publik untuk dibaca**. Mengetahui alamat **tidak** memberi akses ke koinnya, karena untuk itu dibutuhkan private key. Hati-hati dengan "tools" yang mengaku bisa membuka wallet Satoshi atau wallet lama. Semuanya scam.

---

## Isi folder

| File | Jenis | Fungsi |
|---|---|---|
| `cek_alamat_btc.py` | script | Cek saldo dan transaksi terbaru satu alamat, lalu simpan ke CSV |
| `patoshi_scan.py` | script | Unduh data blok awal, lalu filter pola Patoshi |
| `run_patoshi.sh` | script | Menjalankan `patoshi_scan.py` secara pelan per batch: tahap `unduh` (sekitar 1 hari) dan `saldo` (sekitar 2–3 hari), dijalankan terpisah |
| `riwayat_saldo.csv` | output | Riwayat saldo, satu baris per run `cek_alamat_btc.py` |
| `transaksi_<alamat>.csv` | output | Transaksi terbaru dari run terakhir |
| `blok_awal.csv` | output | Data mentah setiap blok 0–54.316 |
| `saldo_alamat.csv` | output | Cache hasil cek saldo per alamat Patoshi (append) |
| `alamat_patoshi.csv` | output | Blok dan alamat yang cocok dengan pola Patoshi, plus tingkat keyakinan dan kolom saldo |
| `wallet_satoshi.csv` | output | Daftar ringkas alamat keyakinan tinggi+sedang dengan saldo BTC-nya (`patoshi_scan.py daftar`) |
| `buat_bubble.py` | script | Bubble plot interaktif semua alamat -> `bubble_satoshi.html` |
| `buat_aliran.py` + `aliran_template.html` | script | Graf node aliran dana dari reward yang pernah dipindah -> `aliran_dana.html` |
| `buat_kaggle.py` | script | Membangun paket dataset Kaggle (`kaggle_dataset/`) |
| `plot_extranonce.png` | output | Plot ExtraNonce vs height, diwarnai per tingkat keyakinan |
| `patoshi.log` / `patoshi_saldo.log` | output | Log tahap unduh / saldo dari `run_patoshi.sh` |
| `.run_patoshi.lock` | internal | Lock file supaya `run_patoshi.sh` tidak berjalan dobel |

---

## Pipeline 1: Monitor alamat (`cek_alamat_btc.py`)

### Alur

```
mempool.space /api/address/<alamat>       ──► saldo, total masuk/keluar, jumlah tx
mempool.space /api/v1/prices              ──► harga BTC (USD)
mempool.space /api/address/<alamat>/txs   ──► transaksi terbaru
                     │
                     ├──► tampil di terminal
                     ├──► riwayat_saldo.csv        (append, satu baris per run)
                     └──► transaksi_<alamat>.csv   (ditimpa setiap run)
```

### Pemakaian

```bash
python3 cek_alamat_btc.py                  # alamat genesis 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa
python3 cek_alamat_btc.py <alamat> 20      # alamat lain, tampilkan 20 transaksi terbaru
```

API hanya mengembalikan halaman pertama riwayat (sekitar 25 transaksi terbaru), jadi `n` lebih dari 25 tidak menambah hasil.

### Format CSV

**`riwayat_saldo.csv`** (satu baris ditambahkan per run, berguna untuk melihat perubahan saldo dari waktu ke waktu)

| Kolom | Isi |
|---|---|
| `waktu_cek_utc` | Waktu script dijalankan (UTC) |
| `alamat` | Alamat yang dicek |
| `saldo_btc` | Saldo terkonfirmasi |
| `pending_btc` | Selisih dari transaksi yang belum terkonfirmasi |
| `total_diterima_btc` / `total_dikirim_btc` | Total masuk dan keluar sepanjang waktu |
| `jumlah_tx` | Jumlah transaksi terkonfirmasi |
| `harga_btc_usd` / `nilai_usd` | Harga BTC dan nilai saldo dalam USD (kosong kalau API harga gagal) |

**`transaksi_<alamat>.csv`** (ditimpa setiap run)

| Kolom | Isi |
|---|---|
| `waktu_utc` | Waktu blok (kosong untuk transaksi yang masih pending) |
| `selisih_btc` | `+` berarti BTC masuk ke alamat, `-` berarti BTC keluar dari alamat |
| `status` | `confirmed` atau `pending` |
| `txid` | ID transaksi; bisa dicek di `https://mempool.space/tx/<txid>` |

Semua waktu dalam **UTC** (WIB = UTC+7).

---

## Pipeline 2: Analisis Patoshi dan saldo (`patoshi_scan.py` dan `run_patoshi.sh`)

### Latar belakang

Pada 2009–2010, reward blok dikirim langsung ke sebuah *public key* (format P2PK), dan software Bitcoin awal membuat key baru untuk setiap blok. Jadi **setiap blok yang ditambang Satoshi = 1 alamat berisi 50 BTC**.

Sergio Demian Lerner (2013) menemukan bahwa sekitar 22 ribu blok awal punya pola yang hanya cocok dengan satu penambang, yang disebut **Patoshi pattern**:

- **LSB nonce**: byte terakhir nonce hanya muncul di rentang **0–9** dan **19–58**.
- **ExtraNonce**: nilainya naik dalam deretan yang konsisten dan terpisah dari penambang lain.
- Koin dari blok-blok ini hampir tidak pernah dipindahkan. Pengecualian terkenal adalah blok 9, yang dikirim ke Hal Finney di blok 170.

Label "Satoshi Nakamoto" di Arkham Intelligence (sekitar 22 ribu alamat, sekitar 1,1 juta BTC) berasal dari analisis jenis ini.

### Alur

```
                    ┌──────────────────── run_patoshi.sh ────────────────────┐
                    │  untuk setiap batch (default 500 blok):                │
                    │    - lewati kalau semua blok sudah ada di CSV           │
                    │    - patoshi_scan.py unduh <awal> <akhir>              │
                    │    - kalau gagal: tunggu 30 menit, coba lagi           │
                    │    - istirahat (default 10 menit)                      │
                    │  setelah semua selesai: patoshi_scan.py analisa        │
                    └────────────────────────────────────────────────────────┘
                    ┌────────────── run_patoshi.sh saldo ────────────────────┐
                    │  untuk setiap batch saldo (default 1000 blok):         │
                    │    - lewati kalau semua alamat sudah ada di cache      │
                    │    - patoshi_scan.py saldo <awal> <akhir>              │
                    │    - gagal: tunggu 30 menit; lalu istirahat            │
                    │  terakhir: patoshi_scan.py analisa (gabung final)      │
                    └────────────────────────────────────────────────────────┘

TAHAP 1: UNDUH
mempool.space /api/v1/blocks/<h>   (1 request = 10 blok: h, h-1, ..., h-9)
        │
        ├─ nonce               ──► nonce_lsb = nonce & 0xFF
        ├─ extras.coinbaseRaw  ──► extranonce (push data ke-2 di scriptSig coinbase, little-endian)
        └─ extras.coinbaseSignature "OP_PUSHBYTES_65 <pubkey> OP_CHECKSIG"
                               ──► pubkey ──► SHA256 ──► RIPEMD160 ──► Base58Check ──► alamat 1xxx
        │
        ▼
blok_awal.csv   (append; blok yang sudah ada tidak diunduh ulang)

TAHAP 2: ANALISA
blok_awal.csv ──► filter nonce_lsb di 0–9 atau 19–58 (28.746 blok)
              ──► analisis garis ExtraNonce ──► keyakinan tinggi / sedang / rendah
              ──► alamat_patoshi.csv

TAHAP 3: SALDO (3 request per alamat Patoshi)
/api/block/<hash>/txs/0       ──► txid coinbase + nilai reward (vout[0])
/api/tx/<txid>/outspends      ──► apakah reward P2PK sudah dibelanjakan, dan oleh tx apa
/api/address/<alamat 1xxx>    ──► saldo P2PKH (kiriman lain ke alamat dari pubkey yang sama)
        │
        ▼
saldo_alamat.csv (cache, append) ──► digabung ke alamat_patoshi.csv
                                     total_btc = reward (kalau belum dipindah) + saldo_p2pkh
```

**Kenapa perlu 3 request?** Reward 50 BTC dikirim dalam format **P2PK** (ke public key langsung). Kalau alamat `1xxx` di-query ke API, hasilnya hanya menghitung output **P2PKH**, sehingga reward 50 BTC **tidak ikut terhitung**. Contohnya alamat blok 9 (`12cbQLTF...`) di explorer hanya menunjukkan sekitar 0,44 BTC, padahal reward-nya 50 BTC (yang sudah dipindah ke Hal Finney). Karena itu status reward dicek langsung dari output coinbase-nya.

### Pemakaian

**Cara yang disarankan: jalankan setiap tahap pelan di background**

```bash
cd Finding-Satoshi-Wallet

# 1. Unduh blok + analisa pola (sekitar 1 hari)
nohup ./run_patoshi.sh > patoshi.log 2>&1 &

# 2. (opsional) lihat plot untuk verifikasi visual
python3 patoshi_scan.py plot

# 3. Cek saldo alamat keyakinan "tinggi" (sekitar 2,5 hari)
nohup ./run_patoshi.sh saldo > patoshi_saldo.log 2>&1 &

#    ...atau termasuk "sedang" (sekitar 2,8 hari)
PATOSHI_KEYAKINAN=tinggi,sedang nohup ./run_patoshi.sh saldo > patoshi_saldo.log 2>&1 &
```

Kedua tahap sengaja dipisah. Tahap saldo butuh 3 request per alamat, jadi sebaiknya dijalankan setelah daftar alamat sudah dibersihkan.

| Aksi | Perintah |
|---|---|
| Lihat progres | `tail -f patoshi.log` (atau `patoshi_saldo.log`) |
| Hentikan | `pkill -f run_patoshi.sh; pkill -f patoshi_scan.py` |
| Lanjutkan | jalankan perintah `nohup ...` yang sama lagi |
| Status proses | `pgrep -af "run_patoshi\|patoshi_scan"` |
| Cek jumlah blok tersimpan | `echo $(( $(wc -l < blok_awal.csv) - 1 ))` |

**Pengaturan `run_patoshi.sh`** (lewat environment variable)

| Variabel | Default | Arti |
|---|---|---|
| `AWAL` | `0` | Blok pertama |
| `AKHIR` | `54316` | Blok terakhir (sekitar akhir aktivitas Patoshi) |
| `BATCH` | `500` | Blok per batch (pakai kelipatan 10) |
| `PATOSHI_JEDA` | `3` | Detik jeda antar request |
| `ISTIRAHAT` | `600` | Detik istirahat antar batch (kedua tahap) |
| `BATCH_SALDO` | `1000` | Blok per batch di tahap saldo (sekitar 400 alamat Patoshi, sekitar 1.200 request) |

Perkiraan durasi:

| Tahap | Setelan | Total request | Durasi |
|---|---|---|---|
| Unduh | default | ~5.400 | **~24 jam** |
| Saldo | keyakinan `tinggi` (default) | ~59.000 | **~2,5 hari** |
| Saldo | `tinggi,sedang` | ~67.000 | ~2,8 hari |
| Unduh | `BATCH=300 ISTIRAHAT=2700` | ~5.400 | ~3 hari |

Contoh: `BATCH=300 ISTIRAHAT=2700 nohup ./run_patoshi.sh > patoshi.log 2>&1 &`

**Menjalankan `patoshi_scan.py` langsung (cepat, tanpa istirahat)**

```bash
python3 patoshi_scan.py                  # unduh + analisa blok 0–54316 (jeda 0,35 detik, ~1 jam)
python3 patoshi_scan.py 0 5000           # unduh + analisa rentang tertentu
python3 patoshi_scan.py unduh 0 5000     # hanya unduh
python3 patoshi_scan.py analisa          # hanya analisa data yang sudah ada
python3 patoshi_scan.py saldo 0 999      # cek saldo alamat Patoshi di blok 0–999
python3 patoshi_scan.py plot             # buat plot_extranonce.png
PATOSHI_JEDA=3 python3 patoshi_scan.py unduh 0 999
```

Kalau `unduh` dijalankan pada rentang sebagian, `analisa` juga hanya menganalisa rentang itu. Jalankan `python3 patoshi_scan.py analisa` (tanpa rentang) untuk menganalisa semua blok 0–54.316.

### Fitur keamanan

- **Resume**: blok yang sudah ada di `blok_awal.csv` dilewati. Script aman dihentikan kapan saja.
- **Lock**: `flock` pada `.run_patoshi.lock` mencegah dua `run_patoshi.sh` berjalan bersamaan.
- **Retry**: setiap request dicoba sampai 6 kali dengan backoff 5, 10, 20, 40, 80, dan 160 detik. Kalau tetap gagal, `run_patoshi.sh` menunggu 30 menit lalu mencoba batch itu lagi.
- **Beban rendah**: rata-rata sekitar 15–17 request per menit (jeda 3 detik plus istirahat antar batch), hanya baca data publik.
- **Cache saldo**: alamat yang sudah dicek disimpan di `saldo_alamat.csv` dan tidak dicek ulang. Menjalankan `analisa` lagi tidak menghapus kolom saldo.

### Format CSV

**`blok_awal.csv`** (dan 8 kolom pertama `alamat_patoshi.csv`):

| Kolom | Isi |
|---|---|
| `height` | Nomor blok |
| `hash` | Hash blok |
| `waktu_utc` | Timestamp blok (UTC) |
| `nonce` | Nonce di header blok |
| `nonce_lsb` | `nonce & 0xFF`, dasar filter Patoshi |
| `extranonce` | ExtraNonce dari scriptSig coinbase |
| `pubkey` | Public key penerima reward (P2PK) |
| `alamat` | Alamat Bitcoin hasil konversi dari `pubkey` |
| `keyakinan` | Hanya di `alamat_patoshi.csv`: `tinggi` / `sedang` / `rendah`, lihat "Filter ExtraNonce" |

**Kolom saldo** (ada di `saldo_alamat.csv` dan ditambahkan ke `alamat_patoshi.csv`; kosong kalau alamat belum dicek):

| Kolom | Isi |
|---|---|
| `coinbase_txid` | ID transaksi coinbase (reward) blok tersebut |
| `reward_btc` | Nilai reward blok (biasanya 50 BTC) |
| `reward_dipindah` | `tidak` = masih utuh; `ya` = sudah dibelanjakan; `genesis` = reward blok 0, yang secara protokol tidak bisa dibelanjakan |
| `reward_dipindah_txid` | Transaksi yang membelanjakan reward (kalau `ya`) |
| `saldo_p2pkh_btc` | Saldo kiriman lain ke alamat `1xxx` dari pubkey yang sama (umumnya donasi atau "tribute") |
| `total_btc` | Isi wallet = reward (kalau belum dipindah) + `saldo_p2pkh_btc` |
| `waktu_cek_utc` | Waktu saldo dicek; saldo bisa berubah setelahnya |

`blok_awal.csv` tidak selalu urut berdasarkan `height` (API mengembalikan blok dari yang terbaru ke yang lama di setiap request). `alamat_patoshi.csv` selalu urut naik.

### Verifikasi yang sudah dilakukan

| Blok | Alamat hasil script | Keterangan |
|---|---|---|
| 0 | `1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa` | Alamat genesis, cocok |
| 9 | `12cbQLTFMXRnSzktFkuoG3eHoMeFtpTu3S` | Alamat Satoshi yang mengirim BTC ke Hal Finney, cocok |
| 9 (saldo) | `reward_dipindah = ya`, tx `f4184fc5...` | Tx ke Hal Finney di blok 170, cocok |
| 0 (saldo) | reward 50 + P2PKH 57,7 = 107,7 BTC | 50 BTC genesis ditandai `genesis` (tidak bisa dibelanjakan) |

### Keterbatasan

- Filter hanya memakai **LSB nonce**. Penambang lain punya peluang sekitar 50/256 (sekitar 20%) untuk kebetulan masuk rentang yang sama, jadi hasilnya kemungkinan **lebih banyak** dari sekitar 22 ribu blok versi Lerner/Arkham. Untuk hasil lebih akurat, perlu ditambah analisis garis ExtraNonce (belum diimplementasikan).
- Di blok di atas sekitar 30.000, blok Patoshi makin jarang dan garis ExtraNonce-nya putus-putus. Sebagian blok Patoshi asli di era ini masuk keyakinan `rendah`.
- Parameter filter garis dipilih secara empiris. Hasilnya mendekati, tapi **tidak identik**, dengan daftar Lerner/Arkham.
- `reward_btc` diambil dari output pertama coinbase. Blok awal hanya punya satu output, jadi ini sudah mencakup semua reward.
- Ringkasan "Total isi wallet" hanya menjumlahkan alamat yang **sudah** dicek. Angka finalnya baru lengkap setelah tahap saldo selesai.
- Atribusi ini berbasis **probabilitas statistik**, bukan bukti kepemilikan.

---

## Filter ExtraNonce dan tingkat keyakinan

Kalau ExtraNonce diplot terhadap height (`plot_extranonce.png`), blok Patoshi membentuk **garis-garis curam**: ExtraNonce naik cepat karena berasal dari satu mesin yang berjalan terus. Penambang lain membentuk **garis landai**. Sekitar 20% blok penambang lain kebetulan lolos filter LSB, dan titik-titik itu berada di garis landai.

Cara kerja (`beri_keyakinan` di `patoshi_scan.py`), hanya pada blok yang lolos filter LSB:

1. **Jangkar**: titik yang punya tetangga sebelum *dan* sesudah (dalam 15 blok) yang segaris dan curam (kemiringan ≥ 3 ExtraNonce per blok, selisih ≤ 80, rasio kemiringan kedua sisi ≤ 2,5).
2. **Tinggi**: dari jangkar, garis dikembangkan berulang kali sampai stabil. Titik masuk kalau berada di antara dua titik jangkar yang segaris (jendela 100 blok, kemiringan ≥ 2, selisih ≤ 600, rasio ≤ 3).
3. **Sedang**: bukan tinggi, tapi punya minimal satu tetangga jangkar dengan kemiringan curam (jendela 60, selisih ≤ 300).
4. **Rendah**: sisanya.

**Hasil (blok 0–54.316)**

| | Alamat | Perkiraan false positive | Presisi | Perkiraan Patoshi asli |
|---|---|---|---|---|
| Lolos filter LSB | 28.746 | ~6.200 | ~78% | ~22.539 (statistik) |
| Keyakinan **tinggi** | **19.815** | ~196 | **~99%** | ~19.619 |
| Keyakinan **sedang** | 2.522 | ~525 | ~79% | ~1.997 |
| **tinggi + sedang** | **22.337** | ~721 | ~97% | **~21.616** |
| Keyakinan rendah | 6.409 | sebagian besar | | ~900 |

Sebagai pembanding, Arkham mencatat sekitar 21,9 ribu alamat dan Lerner sekitar 22 ribu blok (sekitar 1,1 juta BTC).

**Cara mengukur false positive**: blok yang LSB nonce-nya di luar rentang Patoshi (206 dari 256 nilai) pasti bukan milik Satoshi. Filter garis yang sama dijalankan pada blok-blok itu. Persentase yang lolos dikalikan dengan perkiraan jumlah blok non-Patoshi yang kebetulan lolos filter LSB (`jumlah blok non-LSB × 50/206`).

---

## Hasil akhir (snapshot saldo 3–7 Nov 2026)

| | Tinggi | Sedang | Tinggi + sedang |
|---|---|---|---|
| Alamat | 19.815 | 2.522 | 22.337 |
| Reward pernah dipindah | 207 (1,0%) | 460 (18,2%) | 667 (3,0%) |
| Total saldo (BTC) | 980.409,27 | 103.170,80 | **1.083.580,07** |

- **21.669 reward (97%) belum pernah dipindah.** Total sudah termasuk 77,58 BTC tribute P2PKH (sebagian besar di alamat genesis) dan reward genesis yang tidak bisa dibelanjakan.
- Jumlah reward yang dipindah hampir sama dengan perkiraan false positive (207 vs ~196 di kelas tinggi, 460 vs ~525 di kelas sedang). Ini cocok dengan dugaan bahwa reward yang dipindah kebanyakan milik penambang lain yang lolos filter, sehingga menjadi validasi independen untuk filter ExtraNonce.

---

## Visualisasi interaktif

```bash
python3 buat_bubble.py    # -> bubble_satoshi.html
python3 buat_aliran.py    # -> aliran_dana.html (butuh waktu, satu request per tx/alamat baru)
```

**`buat_bubble.py`**: satu bubble per alamat tinggi+sedang. Sumbu x = waktu blok, sumbu y = ExtraNonce atau saldo (skala log), ukuran = saldo. Warna menunjukkan status reward (utuh / dipindah / genesis). Ada kotak pencarian alamat, dan klik bubble membuka alamatnya di mempool.space.

**`buat_aliran.py`**: menelusuri setiap reward Patoshi yang pernah dipindah (`reward_dipindah = ya` di `saldo_alamat.csv`), lalu mengikuti transaksinya sampai beberapa hop. Hasilnya graf node (vis-network):
- node lingkaran = alamat (oranye = Patoshi, kuning = penerima terkenal seperti Hal Finney, biru = alamat lain); ukuran lingkaran = saldo saat ini
- node belah ketupat = transaksi, berlabel tanggal (UTC); panel samping berisi daftar transaksi per tanggal
- panah = BTC yang mengalir; oranye kalau keluar dari alamat Patoshi

| Variabel env | Default | Fungsi |
|---|---|---|
| `ALIRAN_HOP` | 2 | Kedalaman penelusuran |
| `ALIRAN_MIN_BTC` | 1 | Output di bawah nilai ini tidak diikuti |
| `ALIRAN_MAKS_TX` | 400 | Batas jumlah transaksi |
| `ALIRAN_SALDO` | 1 | `0` = lewati cek saldo alamat (lebih cepat) |

Respons API disimpan di `aliran_cache.json`. Hapus file itu untuk mengambil saldo terbaru.

---

## Dataset Kaggle

```bash
KAGGLE_USER=<username> python3 buat_kaggle.py
kaggle datasets create -p kaggle_dataset                       # upload pertama
kaggle datasets version -p kaggle_dataset -m "add balances"    # versi berikutnya
```

`buat_kaggle.py` butuh `ARTICLE.md` di folder yang sama (artikel tidak disertakan di repo ini). Script ini mengubah CSV ke kolom bahasa Inggris, membuat gambar pipeline/histogram, dan menghitung `SHA256SUMS`. Kolom saldo di `patoshi_addresses.csv` disertakan otomatis setelah semua alamat tinggi+sedang selesai dicek.

---

## Referensi

- Sergio Demian Lerner, *The Well Deserved Fortune of Satoshi Nakamoto* (2013) dan riset lanjutan "Patoshi pattern", di bitslog.com
- API mempool.space: https://mempool.space/docs/api/rest
