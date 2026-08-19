#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TaskOn Quest Scraper (read-only, tanpa login, tanpa browser)
=============================================================
Menampilkan quest live dari TaskOn + detail task & reward per quest.

Gunakan:
  python taskon_scraper.py                 -> daftar quest (halaman 1, 10 item)
  python taskon_scraper.py --pages 3       -> 3 halaman (30 quest)
  python taskon_scraper.py --id 452005270  -> detail satu quest
  python taskon_scraper.py --list          -> hanya daftar (tanpa detail)

Output: stdout + file JSON di ./results/
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.taskon.xyz"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
HDRS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://taskon.xyz/",
    "Origin": "https://taskon.xyz",
    "Content-Type": "application/json",
}


def api(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        API + path,
        data=json.dumps(payload).encode(),
        headers=HDRS,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def ts(ms) -> str:
    if not ms or ms < 0:
        return ""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def parse_task_params(raw: str) -> dict:
    try:
        return json.loads(raw or "{}")
    except Exception:
        return {}


def fmt_reward_amount(r: dict) -> str:
    if r.get("reward_type") == "Exp":
        amt = (r.get("reward_params") or {}).get("per_amount", "")
        return f"{amt} EXP"
    if r.get("reward_type") == "GTCPoints":
        params = r.get("reward_params") or {}
        amt = params.get("per_amount") or params.get("amount") or ""
        nama = params.get("points_name") or "Points"
        return f"{amt} {nama}"
    params = r.get("reward_params") or {}
    # reward token: params.token_name/total_amount/per_amount/chain
    if params.get("token_name"):
        per = params.get("per_amount") or params.get("total_amount") or ""
        name = params.get("token_name") or ""
        chain = params.get("chain") or ""
        parts = [x for x in (str(per), str(name), str(chain)) if x]
        return " ".join(parts).strip() or "?"
    amt = r.get("reward_amount") or r.get("amount") or ""
    sym = r.get("reward_symbol") or r.get("symbol") or ""
    chain = r.get("chain_label") or r.get("chain") or ""
    desc = r.get("reward_desc") or ""
    parts = [x for x in (str(amt), str(sym), str(chain)) if x]
    base = " ".join(parts).strip()
    if desc:
        base = f"{base} ({desc})" if base else desc
    return base or "?"


def flatten_winner_rewards(winner_rewards) -> list:
    """winner_rewards bisa berisi layer (winner_layer_rewards[].rewards[]) atau flat."""
    flat = []
    for w in winner_rewards or []:
        layers = w.get("winner_layer_rewards")
        if layers:
            for layer in layers:
                for r in layer.get("rewards") or []:
                    flat.append(r)
        else:
            flat.append(w)
    return flat


def fmt_task(t: dict) -> dict:
    params = parse_task_params(t.get("params", ""))
    name = (t.get("custom_name") or t.get("name") or t.get("template_id") or "").strip()
    extra = ""
    if t.get("platform") == "Twitter":
        extra = params.get("user_to_follow") or params.get("project_name") or ""
    elif t.get("platform") == "Telegram":
        extra = params.get("channel_name") or params.get("group_name") or ""
    elif t.get("platform") == "Discord":
        extra = params.get("server_name") or ""
    elif t.get("platform") == "WebPage":
        extra = params.get("url") or ""
    pts = (t.get("points") or {}).get("amount") or 0
    return {
        "task": name,
        "platform": t.get("platform", ""),
        "detail": extra,
        "points": pts,
        "optional": bool(t.get("is_optional")),
        "class_type": t.get("class_type", ""),
        "recurrence": t.get("recurrence", ""),
    }


def get_quests(page_no: int = 1, size: int = 10, status: str = "OnGoing") -> dict:
    # API tidak filter OnGoing dengan benar; minta All, filter client-side
    api_status = status if status in ("Ended", "All") else "All"
    payload = {
        "page": {"page_no": page_no, "size": size},
        "options": {
            "name_like": "",
            "campaign_status": api_status,
            "campaign_type": "Campaign",
            "pageName": "AllQuest",
        },
    }
    try:
        return api("/v1/getCampaignList", payload)
    except Exception as e:
        return {"error": str(e)}


def get_quest_detail(campaign_id: int) -> dict:
    try:
        return api("/v1/getCampaignInfo", {"campaign_id": campaign_id})
    except Exception as e:
        return {"error": str(e)}


def summarize_quest(q: dict) -> dict:
    """Ringkas satu quest dari hasil getCampaignInfo (detail)."""
    rewards = []
    for r in (q.get("qualifier_rewards") or []):
        rewards.append(fmt_reward_amount(r))
    for r in flatten_winner_rewards(q.get("winner_rewards")):
        rewards.append(fmt_reward_amount(r))
    for r in (q.get("task_rewards") or []):
        rewards.append(fmt_reward_amount(r))
    tasks = [fmt_task(t) for t in (q.get("tasks") or [])]
    return {
        "id": q.get("id"),
        "title": q.get("name", ""),
        "status": q.get("campaign_status", ""),
        "start": ts(q.get("start_time")),
        "end": ts(q.get("end_time")),
        "community": q.get("community_name", ""),
        "community_status": q.get("community_status", ""),
        "share_url": q.get("share_url", ""),
        "tasks": tasks,
        "rewards": rewards,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="TaskOn quest scraper (read-only)")
    ap.add_argument("--id", type=int, help="ID quest untuk detail penuh")
    ap.add_argument("--pages", type=int, default=1, help="jumlah halaman daftar (default 1)")
    ap.add_argument("--size", type=int, default=30, help="quest per halaman (default 30)")
    ap.add_argument("--status", default="OnGoing",
                    choices=["OnGoing", "Ended", "Upcoming", "All"],
                    help="filter status (default OnGoing)")
    ap.add_argument("--list", action="store_true",
                    help="hanya daftar quest, tanpa detail task")
    ap.add_argument("--json", action="store_true", help="output JSON ke stdout")
    args = ap.parse_args()

    out = {"fetched_at": datetime.now(timezone.utc).isoformat(), "items": []}

    if args.id:
        d = get_quest_detail(args.id)
        if not d.get("result") or d.get("error"):
            print(f"ERROR: {d.get('error') or 'no result'}", file=sys.stderr)
            return 1
        out["items"].append(summarize_quest(d.get("result") or {}))
    else:
        seen = set()
        for page in range(1, args.pages + 1):
            d = get_quests(page, args.size, args.status)
            if d.get("error"):
                print(f"ERROR (page {page}): {d['error']}", file=sys.stderr)
                break
            res = d.get("result") or {}
            for q in res.get("data") or []:
                qid = q.get("id")
                if qid in seen:
                    continue
                # filter status client-side
                if args.status == "OnGoing" and q.get("campaign_status") != "OnGoing":
                    continue
                if args.status == "Upcoming" and q.get("campaign_status") != "Upcoming":
                    continue
                if args.status == "Ended" and q.get("campaign_status") != "Ended":
                    continue
                seen.add(qid)
                if args.list:
                    out["items"].append({
                        "id": qid,
                        "title": q.get("name", ""),
                        "status": q.get("campaign_status", ""),
                        "end": ts(q.get("end_time")),
                        "community": q.get("community_name", ""),
                        "rewards_preview": [
                            fmt_reward_amount(r) for r in (q.get("winner_rewards") or [])[:3]
                        ],
                    })
                else:
                    time.sleep(0.4)  # sopan: jeda antar request detail
                    d2 = get_quest_detail(qid)
                    if d2.get("result") and not d2.get("error"):
                        out["items"].append(summarize_quest(d2.get("result") or {}))
            total = res.get("total") or 0
            print(f"[page {page}] total={total} fetched={len(out['items'])}", file=sys.stderr)

    # simpan JSON — satu file tetap, di-overwrite tiap run
    # (biar repo GitHub nggak numpuk file json makin hari makin besar)
    from datetime import datetime as _dt
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)
    out["scraped_at"] = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
    fname = results_dir / "taskon_latest.json"
    fname.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    # tampilan manusia
    print()
    for it in out["items"]:
        print("=" * 72)
        print(f"[{it.get('id')}] {it.get('title')}")
        print(f"   status : {it.get('status')} | {it.get('start')} → {it.get('end')}")
        print(f"   komunitas : {it.get('community')} ({it.get('community_status')})")
        if it.get("rewards"):
            print(f"   reward : {'; '.join(it['rewards'])}")
        if it.get("tasks"):
            print("   TASK:")
            for t in it["tasks"]:
                opt = " (opsional)" if t.get("optional") else ""
                pts = f" | {t.get('points')} pts" if t.get("points") else ""
                detail = f" → {t['detail']}" if t.get("detail") else ""
                print(f"     - {t.get('task')} [{t.get('platform')}]{opt}{pts}{detail}")
        else:
            print("   (tidak ada data task/reward)")
    print()
    print(f"Tersimpan: {fname}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
