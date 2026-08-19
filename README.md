# TaskOn Quest Bot 🤖

Monitor quest **TaskOn** (https://taskon.xyz) otomatis — scrape data quest yang sedang berjalan, susun laporan rapi, dan kirim ke channel Telegram setiap hari.

## Cara kerja

```
GitHub Actions (cron 10:00 WIB)
        │
        ▼
taskon_scraper.py ──► results/taskon_latest.json ──► taskon_report.py
                                                         │
                                                         ▼
                                              Telegram Bot API ──► channel @TaskOnQuests
```

- **Tanpa LLM**: laporan digenerate langsung dari data JSON oleh Python — formatnya konsisten, tidak ada AI yang mengarang.
- **Tanpa dependensi eksternal**: murni Python stdlib (`urllib`, `json`, `subprocess`). Tidak perlu pip install apa pun di GitHub Actions.

## Setup

### 1. Kredensial Telegram

- **Token bot**: bikin bot di [@BotFather](https://t.me/BotFather) → `/newbot` → dapat token.
- **Chat ID**: nama channel kamu (mis. `@TaskOnQuests`) atau ID numerik (mis. `-1001234567890`). Bot harus **jadi admin** di channel tujuan.

### 2. GitHub Actions (otomatis tiap hari)

1. Push repo ini ke GitHub.
2. Buka repo → **Settings → Secrets and variables → Actions**.
3. Tambah 2 secrets:
   - `TELEGRAM_BOT_TOKEN` → token bot kamu
   - `TELEGRAM_CHAT_ID` → `@TaskOnQuests` (atau ID numerik channel)

Workflow sudah ada: `.github/workflows/taskon-report.yml` — jalan **setiap hari 10:00 WIB** (cron `0 3 * * *` UTC). Bisa juga dijalankan manual via tab **Actions → TaskOn Quest Report → Run workflow**.

### 3. Lokal (coba-coba dulu)

```bash
# salin & isi .env
cp .env.example .env

# dry-run: fetch data + cetak laporan (tanpa kirim)
python taskon_report.py --dry-run

# kirim beneran ke Telegram
python taskon_report.py

# pakai hasil JSON yang sudah ada, tanpa fetch ulang
python taskon_report.py --no-fetch --dry-run
```

## Isi laporan

- Judul quest, ID, periode, komunitas, **link quest**
- Daftar task (platform, target, poin, wajib/opsional)
- Daftar reward (EXP/token, jumlah, chain)

## Catatan

- Hasil scrape disimpan ke **satu file tetap** `results/taskon_latest.json` (di-overwrite tiap run, bukan ditambah-tambah) — biar ukuran repo GitHub tetap kecil.
- Folder `results/` ikut di-ignore git (tidak di-push).
- `.env` berisi token — JANGAN commit (sudah di-ignore).
- Script scraper menggunakan API publik TaskOn tanpa login (read-only).