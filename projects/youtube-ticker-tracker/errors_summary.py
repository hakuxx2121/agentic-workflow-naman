#!/usr/bin/env python3
"""Print one plain-English error line for the morning note, or nothing.
Mentions errors only when more than half of the tracked channels errored, or a channel
errored that didn't error the previous night. Members-only and no-transcript skips alone
don't count. Previous night: data/prev_fetch.json, else the '## Channel errors' bullets
of the latest earlier reports/YYYY-MM-DD.md. Always exits 0."""
import json, os, re, glob, sys
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
IGNORE = re.compile(r"members[- ]only|no transcript|join this channel", re.I)

def errored(fetch):
    return {ch for ch, info in fetch.get("channels", {}).items()
            if any(not IGNORE.search(e) for e in info.get("errors", []))}

def prev_errored(run_date):
    pf = os.path.join(BASE, "data", "prev_fetch.json")
    if os.path.exists(pf):
        d = json.load(open(pf))
        if d.get("run", "")[:10] < run_date: return errored(d)
    reps = sorted(r for r in glob.glob(os.path.join(BASE, "reports", "????-??-??.md"))
                  if os.path.basename(r)[:10] < run_date)
    if not reps: return None
    m = re.search(r"^## Channel errors.*?(?=^## |\Z)", open(reps[-1]).read(), re.M | re.S)
    if not m: return None  # unknown: only the majority rule applies
    return {b for b in re.findall(r"^- \*\*(\w+)\*\*", m.group(0), re.M)}

def main():
    try:
        from fetch import CHANNELS
        cur = json.load(open(os.path.join(BASE, "data", "last_fetch.json")))
    except Exception:
        return
    run_date = cur.get("run", "")[:10]
    bad = [c for c in CHANNELS if c in errored(cur)]
    prev = prev_errored(run_date)
    new = [c for c in bad if prev is not None and c not in prev]
    if not (len(bad) > len(CHANNELS) / 2 or new): return
    line = (f"Fetch errors hit {len(bad)} of {len(CHANNELS)} channels, so these may have missed "
            f"uploads: {', '.join(bad)}.")
    if new: line = line[:-1] + f" (new since last night: {', '.join(new)})."
    print(line)

if __name__ == "__main__":
    try: main()
    except Exception: pass
    sys.exit(0)
