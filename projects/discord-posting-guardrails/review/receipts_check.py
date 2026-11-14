#!/usr/bin/env python3
"""Match TradingViewBot Discord posts to post_webhook.py receipts. Read-only.
Usage: receipts_check.py [--since 'YYYY-MM-DD HH:MM']
Per slot: posted receipts (must be exactly 1), failed attempts, lock present, content sha vs file on disk now.
Also: update_MMDD_HHMM.md / earnings captions written since --since without a posted receipt.
(Cannot see Discord itself: a post made outside post_webhook.py shows up only via the browser-history check in discord_guard.py.)"""
import argparse, collections, datetime as dt, glob, hashlib, json, os, re
P = os.environ.get("NDTL_PIPELINE_ROOT", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "pipeline"))); D = os.environ.get("NDTL_DISCORD_ROOT", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "poster")))
ap = argparse.ArgumentParser(); ap.add_argument("--since"); a = ap.parse_args()
since = dt.datetime.strptime(a.since, "%Y-%m-%d %H:%M").astimezone() if a.since else dt.datetime.now().astimezone() - dt.timedelta(hours=24)
slots = collections.defaultdict(list)
for f in glob.glob(f"{P}/receipts/*/*.json"):
    r = json.load(open(f)); ts = dt.datetime.fromisoformat(r["timestamp"])
    if ts < since: continue
    slots[r.get("slot") or os.path.basename(f)].append((ts, r, f))
issues = []; rows = []
posted_files = set()
for s, lst in sorted(slots.items(), key=lambda x: min(t for t, _, _ in x[1])):
    posted = [x for x in lst if x[1]["status"] == "posted"]; failed = [x for x in lst if x[1]["status"] != "posted"]
    lock = os.path.exists(f"{P}/slots/{s}.lock")
    for _, r, _ in posted: posted_files.add(r["file"])
    sha_ok = None
    if posted:
        r = posted[-1][1]
        try: sha_ok = hashlib.sha256(open(r["file"], encoding="utf-8").read().strip().encode()).hexdigest() == r["content_sha256"]
        except Exception: sha_ok = "file missing"
    rows.append(f"{s:32} posted={len(posted)} failed={len(failed)} lock={'y' if lock else 'n'} file_unchanged={sha_ok} "
                f"at={','.join(t.strftime('%m-%d %H:%M') for t,_,_ in posted)} msg={','.join(str(x[1]['message_id']) for x in posted)} thread={','.join(str(x[1]['thread_id']) for x in posted)}")
    if len(posted) > 1: issues.append(f"DUPLICATE: slot {s} has {len(posted)} posted receipts")
    if not posted: issues.append(f"NOT POSTED: slot {s} only failed attempts ({[x[1]['error'][:80] if x[1]['error'] else x[1]['status'] for x in failed]})")
    if failed and posted: issues.append(f"NOTE: slot {s} had {len(failed)} failed attempt(s) before posting: {[ (x[1]['error'] or '')[:90] for x in failed]}")
    if posted and not lock: issues.append(f"NOTE: slot {s} posted but no lock file")
    if "dryrun" in s and any(not x[1]["dry_run"] for x in posted): issues.append(f"WARN: slot {s} is named dryrun but was a REAL post (dry_run=false)")
cands = [f for f in glob.glob(f"{D}/update_*.md") + glob.glob(f"{D}/earnings_*/*_caption.md") if dt.datetime.fromtimestamp(os.path.getmtime(f)).astimezone() >= since]
for f in sorted(cands):
    if f not in posted_files: issues.append(f"NO RECEIPT: {f} written {dt.datetime.fromtimestamp(os.path.getmtime(f)):%m-%d %H:%M} has no posted receipt")
locks = [os.path.basename(x)[:-5] for x in glob.glob(f"{P}/slots/*.lock") if dt.datetime.fromtimestamp(os.path.getmtime(x)).astimezone() >= since]
for l in locks:
    if l not in slots: issues.append(f"LOCK WITHOUT RECEIPT: {l}")
print(f"since {since:%Y-%m-%d %H:%M %Z}"); print("\n".join(rows)); print("ISSUES:" if issues else "ISSUES: none"); print("\n".join(issues))
