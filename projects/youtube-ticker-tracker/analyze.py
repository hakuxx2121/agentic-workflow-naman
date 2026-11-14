#!/usr/bin/env python3
"""Merge per-video analysis files into data/mentions.json and mark state analyzed.
Analysis files: analysis/<video_id>.json = list of {ticker, sentiment, price_talk, summary, t}
(written by the agent after reading the transcript; summaries in own words only).
Usage: python3 analyze.py            -> merge all + list videos still needing analysis
       python3 analyze.py --pending  -> just list pending video ids"""
import json, os, glob, sys
B = os.path.dirname(os.path.abspath(__file__))
state = json.load(open(f"{B}/state.json"))
pending = [v for v, s in state["processed"].items() if not s.get("skipped") and not os.path.exists(f"{B}/analysis/{v}.json")]
if "--pending" in sys.argv:
    print("\n".join(pending)); sys.exit()
out = []
for f in sorted(glob.glob(f"{B}/analysis/*.json")):
    vid = os.path.basename(f)[:-5]
    mf = glob.glob(f"{B}/meta/*/{vid}.json")
    if not mf: continue
    m = json.load(open(mf[0]))
    for r in json.load(open(f)):
        d = m["upload_date"]
        out.append({"channel": m["channel"], "video_id": vid, "title": m["title"], "url": m["url"] + (f"&t={r['t']}s" if r.get("t") else ""),
                    "video_url": m["url"], "date": f"{d[:4]}-{d[4:6]}-{d[6:]}", "ticker": r["ticker"].upper(),
                    "sentiment": r["sentiment"], "price_talk": r.get("price_talk") or "", "summary": r.get("summary") or "", "t": r.get("t")})
    if vid in state["processed"]: state["processed"][vid]["analyzed"] = True
json.dump(out, open(f"{B}/data/mentions.json", "w"), indent=1)
json.dump(state, open(f"{B}/state.json", "w"), indent=1)
print(len(out), "mentions;", "pending:", pending)
