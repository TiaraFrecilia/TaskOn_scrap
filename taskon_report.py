#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TaskOn Quest Report — laporan rapi + kirim otomatis ke Telegram.

Alur:
  1. Jalankan taskon_scraper.py (fetch data terbaru ke ./results/*.json)
  2. Baca file JSON terbaru
  3. Susun laporan rapi
  4. Kirim ke channel Telegram via Bot API

Kredensial (diutamakan dari environment, fallback ke file .env):
  TELEGRAM_BOT_TOKEN  — token bot (dari @BotFather)
  TELEGRAM_CHAT_ID    — channel/chat tujuan (mis. @TaskOnQuests atau -100xxxx)

Pemakaian:
  python taskon_report.py                 # fetch + kirim ke Telegram
  python taskon_report.py --dry-run       # fetch + cetak saja (tanpa kirim)
  python taskon_report.py results/xxx.json --dry-run  # dari file yang ada
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(BASE, "results")

HARI_ID = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN_ID = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
            "Juli", "Agustus", "September", "Oktober", "November", "Desember"]

EMOJI_PLATFORM = {
    "Twitter": "🐦",
    "Telegram": "✈️",
    "Youtube": "▶️",
    "Discord": "🎮",
    "WebPage": "🌐",
    "Web": "🌐",
    "Visit Website": "🌐",
    "Galxe": "⭐",
    "Zealy": "⚡",
}
EMOJI_DEFAULT = "📋"

SEP = "━━━━━━━━━━━━━━━━━━━━"

# emoji nomor 1..10
NOMOR = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

API_TG = "https://api.telegram.org/bot{token}/sendMessage"


def load_env() -> dict:
    """Baca file .env (kalau ada) jadi dict. Environment asli lebih diutamakan."""
    env = {}
    path = os.path.join(BASE, ".env")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for baris in f:
                baris = baris.strip()
                if not baris or baris.startswith("#") or "=" not in baris:
                    continue
                k, v = baris.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def get_cred() -> tuple:
    """Kembalikan (token, list chat_id). Prioritas: env > file .env.

    TELEGRAM_CHAT_ID bisa berisi beberapa target dipisah koma:
      TELEGRAM_CHAT_ID=497306949,@TaskOnQuests
    """
    file_env = load_env()
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or file_env.get("TELEGRAM_BOT_TOKEN", "")
    raw = os.environ.get("TELEGRAM_CHAT_ID") or file_env.get("TELEGRAM_CHAT_ID", "@TaskOnQuests")
    chats = [c.strip() for c in raw.split(",") if c.strip()]
    return token, chats


def kirim_telegram(teks: str, token: str, chat: str) -> bool:
    """Kirim pesan ke Telegram. Coba parse_mode=Markdown, fallback plain text."""
    if not token:
        print("SKIP: TELEGRAM_BOT_TOKEN kosong — tidak kirim ke Telegram", file=sys.stderr)
        return False

    payload = {
        "chat_id": chat,
        "text": teks,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_TG.format(token=token), data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            res = json.loads(r.read().decode("utf-8", "replace"))
        if res.get("ok"):
            print(f"✓ Terkirim ke {chat} (message_id={res['result'].get('message_id')})")
            return True
        print(f"✗ Telegram API: {res.get('description')}", file=sys.stderr)
        return False
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        # parse_mode Markdown bisa gagal jika ada karakter khusus — coba tanpa markdown
        if e.code == 400 and "parse" in body.lower():
            print("⚠ Markdown ditolak — kirim ulang sebagai teks biasa", file=sys.stderr)
            payload.pop("parse_mode", None)
            req2 = urllib.request.Request(
                API_TG.format(token=token),
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST",
            )
            try:
                with urllib.request.urlopen(req2, timeout=30) as r2:
                    res2 = json.loads(r2.read().decode("utf-8", "replace"))
                if res2.get("ok"):
                    print(f"✓ Terkirim (plain) ke {chat} (message_id={res2['result'].get('message_id')})")
                    return True
                print(f"✗ Telegram API (plain): {res2.get('description')}", file=sys.stderr)
            except Exception as e2:
                print(f"✗ Gagal kirim (plain): {e2}", file=sys.stderr)
            return False
        print(f"✗ Telegram API error {e.code}: {body[:200]}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"✗ Gagal kirim: {e}", file=sys.stderr)
        return False


def tanggal_id(dt: datetime) -> str:
    return f"{HARI_ID[dt.weekday()]}, {dt.day} {BULAN_ID[dt.month]} {dt.year}"


def emoji_platform(platform: str) -> str:
    return EMOJI_PLATFORM.get(platform, EMOJI_DEFAULT)


def fmt_task(t: dict) -> str:
    """Satu baris task."""
    nama = t.get("task") or t.get("platform") or "Task"
    plat = t.get("platform") or ""
    det = t.get("detail") or ""
    pts = t.get("points") or 0
    opt = "opsional" if t.get("optional") else "wajib"

    emoji = emoji_platform(plat)
    garis = f"{emoji} **{nama}**"
    if det:
        garis += f" → `{det}`"
    bagian_pts = f" — {pts} pts" if pts and pts > 0 else ""
    garis += f"{bagian_pts} — _{opt}_"
    return garis


def fmt_reward_sep(rew: str) -> str:
    return f"🎁 {rew}" if rew and rew != "?" else "🎁 (reward tidak ter-parse)"


def format_quest(idx: int, q: dict) -> str:
    nomor = NOMOR[idx] if idx < len(NOMOR) else f"{idx + 1}."
    baris = []
    baris.append(f"{nomor} **{q.get('title', 'Untitled')}**")
    baris.append(f"🆔 ID: `{q.get('id')}`")
    periode = f"{q.get('start')} → {q.get('end')}"
    status = q.get("status") or "OnGoing"
    baris.append(f"📅 Periode: {periode} ({status})")
    komunitas = q.get("community") or "-"
    cstat = q.get("community_status") or ""
    baris.append(f"👥 Komunitas: {komunitas} ({cstat})" if cstat else f"👥 Komunitas: {komunitas}")
    url = q.get("share_url") or ""
    if url:
        baris.append(f"🔗 Link: [{url}]({url})")

    tasks = q.get("tasks") or []
    if tasks:
        baris.append("")
        baris.append("📋 **Tasks:**")
        for t in tasks:
            baris.append(f"• {fmt_task(t)}")

    rewards = q.get("rewards") or []
    if rewards:
        baris.append("")
        baris.append("🎁 **Rewards:**")
        for r in rewards:
            baris.append(f"• {fmt_reward_sep(r)}")

    return "\n".join(baris)


def build_report(data: dict) -> str:
    items = data.get("items") or []
    if not items:
        return "📭 **TASKON QUEST MONITORING**\n\nTidak ada quest OnGoing saat ini, atau API gagal."

    now = datetime.now()
    baris = []
    baris.append(SEP)
    baris.append("📊 **TASKON QUEST MONITORING**")
    baris.append(f"📅 {tanggal_id(now)}")
    baris.append(SEP)
    baris.append("")

    # batasi panjang pesan (Telegram max ~4096 char)
    max_total = 3900
    ditampilkan = 0
    for idx, q in enumerate(items):
        blok = format_quest(idx, q)
        if ditampilkan > 0 and len("\n".join(baris)) + len(blok) > max_total:
            break
        if ditampilkan > 0:
            baris.append("")
            baris.append(SEP)
            baris.append("")
        baris.append(blok)
        ditampilkan += 1

    sisa = len(items) - ditampilkan
    if sisa > 0:
        baris.append("")
        baris.append(f"_…dan {sisa} quest lainnya._")

    baris.append("")
    baris.append(SEP)
    baris.append("_Sumber: taskon.xyz_")
    return "\n".join(baris)


def fetch_latest() -> str:
    """Jalankan scraper, lalu kembalikan path JSON terbaru."""
    scraper = os.path.join(BASE, "taskon_scraper.py")
    cmd = [sys.executable, scraper, "--pages", "2", "--size", "30", "--status", "OnGoing"]
    proc = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise RuntimeError(f"taskon_scraper.py gagal (exit {proc.returncode})")
    return latest_json()


def latest_json() -> str:
    """File hasil terbaru: satu file tetap taskon_latest.json (overwrite tiap run)."""
    path = os.path.join(RESULTS, "taskon_latest.json")
    if not os.path.exists(path):
        # fallback: file lama (kalau belum pernah pakai versi baru)
        files = sorted(glob.glob(os.path.join(RESULTS, "taskon_*.json")))
        if not files:
            raise RuntimeError("Tidak ada file hasil di results/")
        return files[-1]
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="Laporan TaskOn + kirim ke Telegram")
    ap.add_argument("--dry-run", action="store_true",
                    help="jangan kirim ke Telegram, hanya cetak laporan")
    ap.add_argument("--no-fetch", action="store_true",
                    help="jangan jalankan scraper, pakai hasil terbaru yang ada")
    ap.add_argument("json_path", nargs="?", help="path file JSON (opsional)")
    args = ap.parse_args()

    try:
        path = args.json_path
        if not path:
            if args.no_fetch:
                path = latest_json()
            else:
                path = fetch_latest()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 1

    laporan = build_report(data)
    print(laporan)

    if args.dry_run:
        print("\n[dry-run] laporan tidak dikirim ke Telegram.", file=sys.stderr)
        return 0

    token, chats = get_cred()
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN tidak ditemukan (env atau .env)", file=sys.stderr)
        return 2
    if not chats:
        print("ERROR: TELEGRAM_CHAT_ID tidak ditemukan (env atau .env)", file=sys.stderr)
        return 2

    semua_ok = True
    for chat in chats:
        ok = kirim_telegram(laporan, token, chat)
        semua_ok = semua_ok and ok
    return 0 if semua_ok else 1


if __name__ == "__main__":
    sys.exit(main())
