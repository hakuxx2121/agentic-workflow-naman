#!/usr/bin/env python3
"""Regenerate data/page_data.js (MENTIONS, VIDEOS, UPDATED) for the Ticker Tracker Page.
MENTIONS = data/mentions.json (non-skipped videos only); VIDEOS = analyzed, non-skipped videos from state.json + meta, newest first."""
import json, os, glob, datetime
from zoneinfo import ZoneInfo
B = os.path.dirname(os.path.abspath(__file__))
state = json.load(open(f"{B}/state.json"))["processed"]
skipped = {v for v, s in state.items() if s.get("skipped")}
mentions = [m for m in json.load(open(f"{B}/data/mentions.json")) if m["video_id"] not in skipped]
videos = []
for vid, s in state.items():
    if s.get("skipped") or not s.get("analyzed"): continue
    mf = glob.glob(f"{B}/meta/*/{vid}.json")
    if not mf: continue
    m = json.load(open(mf[0])); d = m["upload_date"]
    videos.append({"id": vid, "channel": m["channel"], "title": m["title"], "date": f"{d[:4]}-{d[4:6]}-{d[6:]}",
                   "url": m["url"], "duration": m.get("duration"), "live_status": m.get("live_status"), "analyzed": True})
videos.sort(key=lambda v: v["date"], reverse=True)
now = datetime.datetime.now(ZoneInfo("America/New_York"))
updated = now.strftime("%b %-d, %Y, %-I:%M %p ET")
with open(f"{B}/data/page_data.js", "w") as f:
    f.write("const MENTIONS = " + json.dumps(mentions, indent=1) + ";\n")
    f.write("const VIDEOS = " + json.dumps(videos, indent=1) + ";\n")
    f.write(f"const UPDATED = {json.dumps(updated)};\n")
print(len(mentions), "mentions;", len(videos), "videos;", updated)
