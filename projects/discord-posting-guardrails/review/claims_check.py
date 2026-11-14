#!/usr/bin/env python3
"""Independent check of an Earnings Call Bot claims.json (Manager Bot). Read-only.
Usage: claims_check.py <earnings_dir> [<earnings_dir> ...]
 1 PRICES  every {bar, field, value} anywhere in claims.json is recomputed from the raw price CSV
           (price_csv key, else tv_30s.csv, else *_tv.csv; epoch UTC -> ET; or ET strings). Tol 0.006.
 2 QUOTES  every exact_words is searched (normalised) in the transcripts; the timestamped whisper file
           (et.txt "HH:MM:SS text") is used to find when its first words were spoken vs said_at_et (flag >60 s).
 3 ARROWS  labels with link.keep=true: the move must start in a bar that begins after the quote/event
           and the end bar ("to") must be <= 3 min (+bar) after it.
 3b NOISE  WARN when the 3-min move stays inside the prior 10-min range on < 1.5x avg volume (judgment, not a FAIL).
 4 SOURCES numeric leaves without a source/src on themselves or an ancestor; estimates must name a publisher.
 5 TEXT    literal $/% numbers typed into chart text (not {template}) are listed for manual check.
Exit 0 if no FAIL."""
import csv, datetime as dt, glob, json, os, re, sys
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")
PUBS = re.compile(r"LSEG|Zacks|FactSet|Visible Alpha|S&P|Bloomberg|Investing\.com|Earnings ?Whispers|TradingView|Refinitiv|Yahoo|Nasdaq|Estimize|Koyfin|StreetAccount", re.I)
norm = lambda s: re.sub(r"[^a-z0-9%$.]+", " ", s.lower().replace("’", "'")).strip()

def tsec(s): h, m, x = s.split(":"); return int(h) * 3600 + int(m) * 60 + float(x)

def load_prices(d, c):
    cands = [c.get("price_csv")] if c.get("price_csv") else []
    cands += ["tv_30s.csv"] + [os.path.basename(x) for x in glob.glob(d + "/*_tv.csv")] + ["tv30_et.csv"]
    for name in cands:
        p = os.path.join(d, name)
        if not os.path.exists(p): continue
        bars = {}
        for r in csv.DictReader(open(p)):
            t = r["time"]
            if t.isdigit(): t = dt.datetime.fromtimestamp(int(t), dt.timezone.utc).astimezone(ET)
            else: t = dt.datetime.fromisoformat(t[:19])
            if (c.get("date") or (re.search(r"\d{4}-\d\d-\d\d", d) or [None])[0]) and t.strftime("%Y-%m-%d") != (c.get("date") or re.search(r"\d{4}-\d\d-\d\d", d)[0]): continue
            g = lambda *k: next(float(r[x]) for x in k if x in r and r[x] != "")
            bars[t.strftime("%H:%M:%S")] = {"o": g("open", "o"), "h": g("high", "h"), "l": g("low", "l"), "c": g("close", "c"), "v": g("Volume", "volume", "v")}
        return name, bars
    return None, {}

def walk(o, path="", src=False):
    if isinstance(o, dict):
        s = src or any(k in o for k in ("source", "sources", "src", "publisher", "event_source", "words_source", "calc", "formula", "evidence"))
        yield path, o, s
        for k, v in o.items(): yield from walk(v, f"{path}.{k}", s)
    elif isinstance(o, list):
        for i, v in enumerate(o): yield from walk(v, f"{path}[{i}]", src)

def timed_lines(d):
    out = []
    for f in ("et.txt",):
        p = os.path.join(d, f)
        if os.path.exists(p):
            for ln in open(p, errors="replace"):
                m = re.match(r"(\d{1,2}):(\d\d:\d\d)\s+(?:\[[^\]]*\]\s*)?(.*)", ln)
                if m:
                    h = int(m.group(1)); h = h + 12 if h < 12 else h
                    out.append((tsec(f"{h}:{m.group(2)}"), norm(m.group(3))))
    return out

def check(d):
    out, fails = [], 0
    c = json.load(open(os.path.join(d, "claims.json")))
    name, bars = load_prices(d, c)
    out.append(f"## {d}  (chart {c.get('output','?')}, prices {name}, {len(bars)} bars on {c.get('date','?')})")
    def add(level, msg):
        nonlocal fails; fails += level == "FAIL"; out.append(f"- {level}: {msg}")
    # 1 prices
    n = 0
    for p, o, _ in walk(c):
        if {"bar", "field", "value"} <= set(o) and isinstance(o["value"], (int, float)):
            n += 1; b = bars.get(o["bar"])
            if not b: add("FAIL", f"{p}: bar {o['bar']} not in CSV"); continue
            if abs(b[o["field"]] - o["value"]) > (0.5 if o["field"] == "v" else 0.006):
                add("FAIL", f"{p}: {o['bar']} {o['field']} CSV {b[o['field']]} vs claim {o['value']}")
    out.append(f"- prices: {n} bar-referenced values checked")
    # 2 quotes
    tx = ""
    for f in set(c.get("transcripts", []) + ["eh_transcript.txt", "transcript.txt", "et.txt"]):
        if os.path.exists(os.path.join(d, f)): tx += " " + norm(open(os.path.join(d, f), errors="replace").read())
    tl = timed_lines(d)
    tx += " " + " ".join(x[1] for x in tl)  # et.txt without its timestamp prefixes
    for p, o, _ in walk(c):
        q = o.get("exact_words") or (o.get("verbatim") if "speaker" in o or "quote_time" in o else None)
        if q:
            w = norm(q); ok = w in tx
            add("OK" if ok else "FAIL", f"{p}: quote {'verbatim' if ok else 'NOT FOUND'} in transcripts: \"{q[:70]}\"")
            sa = o.get("said_at_et") or o.get("time") or o.get("quote_time")
            if sa:
                sa = sa.split("-")[0].strip()
                hh = int(sa.split(":")[0])
                if hh < 12: sa = f"{hh+12}:{sa.split(':',1)[1]}"  # chart times are PM
            if sa and tl:
                key = " ".join(w.split()[:4]); hit = None
                for i in range(len(tl)):
                    joined = " ".join(x[1] for x in tl[i:i + 3])
                    if key in joined: hit = tl[i][0]; break
                if hit is None: add("WARN", f"{p}: first words \"{key}\" not located in et.txt (whisper wording differs) - time unverified")
                else:
                    diff = tsec(sa) - hit
                    add("OK" if abs(diff) <= 60 else "FAIL", f"{p}: said_at {sa} vs et.txt line {dt.timedelta(seconds=int(hit))} (diff {diff:+.0f}s)")
    # 3 arrows
    bm = (c.get("bar_minutes") or 0.5) * 60
    for i, l in enumerate(c.get("labels", [])):
        lk = l.get("link") or {}
        if not lk.get("keep"): continue
        t0 = tsec((l.get("quote") or {}).get("said_at_et") or l["marker_time"])
        to = lk.get("to") or (lk.get("to_price") or {}).get("bar")
        frm = [x["bar"] for x in l.get("prices", []) if "bar" in x] or [(lk.get("from_price") or {}).get("bar")]
        q = l.get("quote") or {}
        sa = q.get("said_at_et") or (q.get("time") or "").split("-")[0].strip() or l["marker_time"]
        if int(sa.split(":")[0]) < 12: sa = f"{int(sa.split(':')[0])+12}:{sa.split(':',1)[1]}"
        t0 = tsec(sa)
        # first bar that STARTS after the event, from the raw CSV
        after = sorted(b for b in bars if tsec(b) > t0 - 1e-6)
        first = after[0] if after else None
        prev = max((b for b in bars if first and tsec(b) < tsec(first)), default=None)
        msg = f"labels[{i}] {l.get('id')}: cause arrow, event {sa}; first bar after = {first}"
        if first and prev:
            pb, fb = bars[prev], bars[first]
            mvp = (fb["c"] / pb["c"] - 1) * 100
            vr = fb["v"] / max(pb["v"], 1)
            msg += f" (close {pb['c']:.2f}->{fb['c']:.2f}, {mvp:+.2f}%, vol x{vr:.1f}); starts {tsec(first)-t0:.0f}s after"
            if tsec(first) - t0 > 180: add("FAIL", msg + " > 3 min"); continue
        if to: msg += f"; arrow ends {to} ({tsec(to)-t0:.0f}s after)"
        # noise test: does the move (first bar .. 3 min) leave the prior 10-min range, on >= prior volume?
        if first and prev:
            win = [b for b in bars if t0 - 600 <= tsec(b) < tsec(first)]
            post = [b for b in bars if tsec(first) <= tsec(b) <= t0 + 180]
            if win and post:
                lo, hi = min(bars[b]["l"] for b in win), max(bars[b]["h"] for b in win)
                plo, phi = min(bars[b]["l"] for b in post), max(bars[b]["h"] for b in post)
                avgv = sum(bars[b]["v"] for b in win) / len(win)
                pv = sum(bars[b]["v"] for b in post) / len(post)
                if lo <= plo and phi <= hi and pv < 1.5 * avgv:
                    add("WARN", msg + f"; NOISE? 3-min move stays inside prior-10-min range {lo:.2f}-{hi:.2f}, vol {pv/avgv:.1f}x 10-min avg: consider grey / no arrow")
                    continue
        add("OK", msg)
    # 4 sources
    for p, o, s in walk(c):
        for k, v in o.items():
            if k in ("est", "estimate", "consensus") or k.endswith("_est"):
                extra = ""
                if isinstance(v, dict): extra = " ".join(str(v.get(x, "")) for x in ("src", "source", "publisher", "url")); v = v.get("value", v)
                srcs = " ".join(str(o.get(x, "")) for x in ("src", "source", "publisher", "url")) + " " + str(v) + " " + extra
                foot = " ".join(c.get("footer", [])) if isinstance(c.get("footer"), list) else str(c.get("footer", ""))
                if not PUBS.search(srcs): add("WARN" if PUBS.search(foot) else "FAIL", f"{p}.{k}={v}: estimate without a named publisher in its src" + (" (footer names one)" if PUBS.search(foot) else ""))
        if "value" in o and isinstance(o["value"], (int, float)) and not s and "bar" not in o:
            add("FAIL", f"{p}: value {o['value']} has no source")
    # 5 literal numbers in chart text
    lits = []
    for p, o, _ in walk({k: c.get(k) for k in ("headline", "labels", "cliffnotes", "strip")}):
        for k, v in o.items():
            if isinstance(v, str) and k in ("line1", "line2", "subline", "head", "body", "v", "sub"):
                t = re.sub(r"\{[^}]*\}", "", v)
                for m in re.findall(r"[$~+−-]?\d[\d,.]*\s?[%BMK]?", t):
                    if re.search(r"[$%BMK]", m): lits.append(m.strip())
    if lits: out.append(f"- TEXT literals to verify by hand ({len(lits)}): {', '.join(sorted(set(lits)))}")
    out.append(f"- RESULT: {'PASS' if not fails else f'{fails} FAIL'}")
    return out, fails

if __name__ == "__main__":
    tot = 0
    for d in sys.argv[1:]:
        o, f = check(d.rstrip("/")); tot += f; print("\n".join(o)); print()
    sys.exit(1 if tot else 0)
