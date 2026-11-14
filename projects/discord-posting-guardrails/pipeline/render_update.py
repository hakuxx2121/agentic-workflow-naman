import os
#!/usr/bin/env python3
"""Render an NDTL trade-plan update (.md) from a fresh price snapshot + this week's levels.json.
Usage: render_update.py [--session regular|extended] [--time HHMM] [--date YYYY-MM-DD] [--levels PATH]
                        [--notes NOTES.json] [--out FILE.md] [--prev SNAPSHOT.json] [--snapshot SNAPSHOT.json]
                        [--fixture FIXTURE.json] [--earnings FILE.md] [--force]
Every run takes a price snapshot (prices.py module) and saves it to snapshots/<date>/<HHMM>.json
(--snapshot reuses an existing snapshot file instead of fetching; it is still copied there).
The previous snapshot is the newest one before <date> <HHMM> (snapshots/<date>/<HHMM>.json or legacy
snapshots/<date>_<HHMM>.json), or --prev.
Each bullet ends with the week-to-date candle read from the snapshot's "week" (prices.py), old style
". Green wk +7.8%." / ". Red wk −2.1%."; left out when the weekly fetch failed.
Bullets are fully generated. The only free text is --notes: a JSON object {"TICKER": "sentence"} rendered as
"changed: <sentence>" in that ticker's bullet.
Writes <out> (default ${NDTL_DISCORD_ROOT}/update_MMDD_HHMM.md); if over 2000 chars, splits at a bullet boundary and
writes <out stem>b.md too (post with slot <slot>b). Prints a JSON summary, also saved as snapshots/<date>/<HHMM>.summary.json.
Exit: 0 rendered, 1 bad args/levels/snapshot, 6 every price fetch failed,
      10 no change vs the previous snapshot (no section change, no level crossing): no .md written, skip the post.

Classifier (session price = extended price after hours/pre-market when --session extended, else regular):
  BREAK_TOL = 0.25 %  a support/stop level S counts as broken when price < S * (1 - BREAK_TOL);
                      a resistance/trigger level R counts as cleared when price > R * (1 + BREAK_TOL).
  AT_TOL    = 0.50 %  price is "at" a level L when |price / L - 1| <= AT_TOL.
  Order (first match wins):
    1 Weak                 price is below any support/stop level by more than BREAK_TOL (it broke a support it
                           was above, or it sits under its nearest support). Being near a lower level does not rescue it.
    2 At a level           price within AT_TOL of any level (any role).
    3 Triggered / working  price clears any resistance/trigger level by more than BREAK_TOL.
    4 In range / no change everything else, and tickers with no levels.
  Crossing: a level lies between the previous snapshot price and this one (inclusive of this side)."""
import argparse, contextlib, datetime as dt, glob, io, json, os, re, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import levels_io, prices
ROOT = os.environ.get("NDTL_PIPELINE_ROOT", HERE)
DISCORD = os.environ.get("NDTL_DISCORD_ROOT", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "poster")))
EARNINGS = os.path.join(DISCORD, "earnings_calendar.md")
BREAK_TOL = 0.25; AT_TOL = 0.50; LIMIT = 2000
SUP = {"support", "stop"}; RES = {"resistance", "trigger"}
SECTIONS = ["Triggered / working", "At a level", "Weak", "In range / no change"]
WEEKDAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
TIMING = {"BMO": "before the open", "AMC": "after the close"}
MINUS = "\u2212"

def fp(x):  # level price: 280 / 16.76 / 699.50
    return f"{x:.0f}" if float(x).is_integer() else f"{x:.2f}"

def pct(x):
    if x is None: return None
    r = round(x, 1)
    return "flat" if r == 0 else (f"+{r:.1f}%" if r > 0 else f"{MINUS}{abs(r):.1f}%")

def classify(px, levels):
    """Return (section, level_dict_or_None) for price px."""
    if not px or not levels: return SECTIONS[3], None
    broken = [L for L in levels if L["role"] in SUP and px < L["price"] * (1 - BREAK_TOL / 100)]
    if broken: return SECTIONS[2], min(broken, key=lambda L: L["price"])  # nearest broken support above price
    near = [L for L in levels if abs(px / L["price"] - 1) * 100 <= AT_TOL]
    if near: return SECTIONS[1], min(near, key=lambda L: abs(px / L["price"] - 1))
    cleared = [L for L in levels if L["role"] in RES and px > L["price"] * (1 + BREAK_TOL / 100)]
    if cleared: return SECTIONS[0], max(cleared, key=lambda L: L["price"])
    return SECTIONS[3], None

def crossings(prev, px, levels):
    if prev is None or px is None or prev == px: return []
    out = []
    for L in levels:
        p = L["price"]
        if prev < p <= px: out.append({"level": p, "role": L["role"], "direction": "up"})
        elif px <= p < prev: out.append({"level": p, "role": L["role"], "direction": "down"})
    return out

def describe(section, ref, px, levels):
    below = sorted((L for L in levels if L["price"] < px), key=lambda L: -L["price"])
    above = sorted((L for L in levels if L["price"] > px), key=lambda L: L["price"])
    if section == SECTIONS[2]:
        nxt = below[0] if below else None
        return f"under {fp(ref['price'])} {ref['role']}" + (f"; {fp(nxt['price'])} {nxt['role']} next" if nxt else "; no level below")
    if section == SECTIONS[1]:
        return f"at {fp(ref['price'])} {ref['role']}"
    if section == SECTIONS[0]:
        nxt = above[0] if above else None
        return f"over {fp(ref['price'])} {ref['role']}" + (f"; {fp(nxt['price'])} {nxt['role']} next" if nxt else "")
    if not levels: return "no plan levels"
    parts = ([f"over {fp(below[0]['price'])}"] if below else []) + ([f"under {fp(above[0]['price'])}"] if above else [])
    return ", ".join(parts)

def parse_d(s):
    m = re.match(r"(\d{2})/(\d{2})/(\d{2})", s.strip())
    return dt.date(2000 + int(m.group(3)), int(m.group(1)), int(m.group(2))) if m else None

def load_earnings(path):
    """{TICKER: {"last": (date, timing), "next": (date, timing), "gap": "-5.7%"}} from earnings_calendar.md."""
    out = {}
    if not path or not os.path.exists(path): return out
    for line in open(path, encoding="utf-8"):
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) >= 3 and re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", c[0]):
            e = {}
            for k, cell in (("last", c[1]), ("next", c[2])):
                d = parse_d(cell)
                if d and "unconfirmed" not in cell.lower():
                    t = re.search(r"\b(BMO|AMC)\b", cell); e[k] = (d, t.group(1) if t else None)
            out[c[0]] = e
        m = re.match(r"- \*\*([A-Z][A-Z0-9.]*)\*\*.*?=\s*\*\*([+\-−]?\d+(?:\.\d+)?)%\*\*\s*gap", line)
        if m: out.setdefault(m.group(1), {})["gap"] = m.group(2).replace("-", MINUS)
    return out

def earnings_text(e, today, session):
    if not e: return None
    def when(d, t):
        tm = TIMING.get(t, "")
        if d == today: return ("tonight " if t == "AMC" else "this morning " if t == "BMO" else "today ") + tm
        if d == today + dt.timedelta(1): return "tomorrow " + tm
        return f"{WEEKDAY[d.weekday()]} {d.month}/{d.day} {tm}"
    n = e.get("next"); l = e.get("last")
    if n and 0 <= (n[0] - today).days <= 7:
        done = n[0] == today and (n[1] == "BMO" or (n[1] == "AMC" and session == "extended"))
        return f"{'reported' if done else 'reports'} {when(*n).strip()}"
    if l and 0 <= (today - l[0]).days <= 7:
        return f"reported {when(*l).strip()}" + (f", gapped {e['gap']}%" if e.get("gap") else "")
    return None

def time_label(hhmm):
    h, m = int(hhmm[:2]), int(hhmm[2:])
    ap = "AM" if h < 12 else "PM"; h12 = h % 12 or 12
    return f"{h12} {ap}" if m == 0 else f"{h12}:{m:02d} {ap}"

def snap_key(path):
    m = re.search(r"(\d{4}-\d{2}-\d{2})[/_](\d{4})\.json$", path)
    return (m.group(1), m.group(2)) if m else None

def find_prev(root, date, hhmm):
    c = [p for p in glob.glob(os.path.join(root, "snapshots", "*", "*.json")) + glob.glob(os.path.join(root, "snapshots", "*.json"))
         if snap_key(p) and snap_key(p) < (date, hhmm)]
    return max(c, key=snap_key) if c else None

def atomic_write(path, text):
    d = os.path.dirname(os.path.abspath(path)); os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp.", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f: f.write(text); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp): os.unlink(tmp)
        raise

def bullet(sym, row, session, desc, note, earn):
    px = row["last"]
    if session == "extended" and row.get("price_basis") == "extended":
        reg = row.get("regular_price"); ec = pct(row.get("ext_change_pct"))
        body = f"{px:.2f} ({reg:.2f}, {ec}{'' if ec == 'flat' else ' after hours'})"
    else:
        body = f"{px:.2f} ({pct(row.get('change_pct')) or 'n/a'})"
    tail = "; ".join(x for x in [f"changed: {note}" if note else None, desc, earn] if x)
    wk = week_text(row.get("week"))
    if wk: tail = f"{tail}. {wk}." if tail else f"{wk}."
    return f"\u2022 **{sym}** {body}" + (f": {tail}" if tail else "")

def week_text(w):
    """'Green wk +7.8%' / 'Red wk −2.1%' / 'Flat wk' (old update style); None if the weekly fetch failed."""
    if not isinstance(w, dict) or w.get("week_pct") is None: return None
    p = pct(w["week_pct"])
    return "Flat wk" if p == "flat" else f"{'Green' if w['week_pct'] > 0 else 'Red'} wk {p}"

def split_msgs(lines):
    text = "\n".join(lines)
    if len(text) <= LIMIT: return [text]
    a, i = [], 0
    while i < len(lines) and len("\n".join(a + [lines[i]])) <= LIMIT: a.append(lines[i]); i += 1
    if len(a) > 2 and a[-1].startswith("**"): i -= 1; a.pop()  # never end message 1 on a section heading
    b = lines[i:]
    if len("\n".join(b)) > LIMIT: raise ValueError("update needs more than 2 messages")
    return ["\n".join(a), "\n".join(b)]

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", choices=["regular", "extended"], default="regular")
    ap.add_argument("--time"); ap.add_argument("--date"); ap.add_argument("--levels"); ap.add_argument("--notes")
    ap.add_argument("--out"); ap.add_argument("--prev"); ap.add_argument("--snapshot"); ap.add_argument("--fixture")
    ap.add_argument("--earnings", default=EARNINGS); ap.add_argument("--force", action="store_true")
    o = ap.parse_args(argv)
    now = dt.datetime.now().astimezone()
    date = o.date or now.strftime("%Y-%m-%d"); hhmm = o.time or now.strftime("%H%M")
    if not re.fullmatch(r"\d{4}", hhmm) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        print("bad --time/--date", file=sys.stderr); return 1
    today = dt.date.fromisoformat(date)
    try:
        lpath = o.levels or levels_io.latest_levels_path(ROOT); LV = levels_io.read_levels(lpath)
        notes = json.load(open(o.notes, encoding="utf-8")) if o.notes else {}
        if not isinstance(notes, dict): raise ValueError("--notes must be a JSON object")
    except Exception as e:
        print(f"input error: {e}", file=sys.stderr); return 1
    snap_path = os.path.join(ROOT, "snapshots", date, f"{hhmm}.json")
    if o.snapshot:
        try: snap = json.load(open(o.snapshot)); atomic_write(snap_path, json.dumps(snap, indent=1))
        except Exception as e: print(f"snapshot error: {e}", file=sys.stderr); return 1
    else:
        args = ["--session", o.session, "--levels", lpath, "--out", snap_path, "--asof", date] + (["--fixture", o.fixture] if o.fixture else [])
        with contextlib.redirect_stdout(io.StringIO()): rc = prices.main(args)
        if rc: return rc
        snap = json.load(open(snap_path))
    prev_path = o.prev or find_prev(ROOT, date, hhmm)
    prev = {}
    if prev_path:
        try: prev = {r["symbol"]: r for r in json.load(open(prev_path))["tickers"] if "error" not in r}
        except Exception as e: print(f"previous snapshot error: {e}", file=sys.stderr); return 1
    rows = {r["symbol"]: r for r in snap["tickers"]}
    earn = load_earnings(o.earnings)
    lvby = {t["symbol"]: t["levels"] for t in LV["tickers"]}
    secs = {s: [] for s in SECTIONS}; summ = {"changed_section": [], "crossed": [], "errors": [], "tickers": {}}
    for t in LV["tickers"]:
        s = t["symbol"]; r = rows.get(s)
        if not r or "error" in r:
            summ["errors"].append({"symbol": s, "error": (r or {}).get("error", "missing from snapshot")}); continue
        sec, ref = classify(r["last"], t["levels"])
        pr = prev.get(s); psec = classify(pr["last"], t["levels"])[0] if pr else None
        cr = crossings(pr["last"] if pr else None, r["last"], t["levels"])
        summ["tickers"][s] = {"price": r["last"], "section": sec, "previous_section": psec, "previous_price": pr["last"] if pr else None}
        if pr and psec != sec: summ["changed_section"].append({"symbol": s, "from": psec, "to": sec})
        if cr: summ["crossed"].append({"symbol": s, "crossings": cr})
        secs[sec].append(bullet(s, r, o.session, describe(sec, ref, r["last"], t["levels"]), notes.get(s), earnings_text(earn.get(s), today, o.session)))
    unknown = sorted(set(notes) - set(lvby))
    summ.update(date=date, time=hhmm, session=o.session, snapshot=snap_path, previous_snapshot=prev_path,
                unknown_note_tickers=unknown, tolerances={"BREAK_TOL_pct": BREAK_TOL, "AT_TOL_pct": AT_TOL})
    changed = bool(summ["changed_section"] or summ["crossed"])
    summ["no_change"] = bool(prev_path) and not changed
    spath = os.path.join(ROOT, "snapshots", date, f"{hhmm}.summary.json")
    if summ["no_change"] and not o.force:
        summ["files"] = []; atomic_write(spath, json.dumps(summ, indent=1)); print(json.dumps(summ, indent=1)); return 10
    wd = WEEKDAY[today.weekday()]; md = f"{today.month}/{today.day}"
    wk = dt.date.fromisoformat(LV["week_of"]); wkl = f"{wk.month}/{wk.day}"
    after = o.session == "extended" and int(hhmm) >= 1600
    pre = o.session == "extended" and int(hhmm) < 930
    stamp = snap.get("generated_at", "")[11:16]
    st = time_label(stamp.replace(":", "")) if re.fullmatch(r"\d\d:\d\d", stamp) else time_label(hhmm)
    if after or pre:
        kind = "after-hours" if after else "pre-market"
        lines = [f"**{wd} {md} {time_label(hhmm)} {kind} update (~{st} ET, extended hours)**",
                 f"Jason's {wkl} plan levels. {'After-hours' if after else 'Pre-market'} price ({'close' if after else 'prior close'}, {'after-hours' if after else 'pre-market'} %)."]
    else:
        lines = [f"**{wd} {md} {time_label(hhmm)} update (~{st} ET)**", f"Jason's {wkl} plan levels."]
    for s in SECTIONS:
        if secs[s]: lines += [f"**{s}**"] + secs[s]
    if prev_path:
        k = snap_key(prev_path); since = time_label(k[1]) if k else "last update"
        bits = [f"{c['symbol']} {c['from'].split(' /')[0].lower()} to {c['to'].split(' /')[0].lower()}" for c in summ["changed_section"]]
        bits += [f"{c['symbol']} {'up through' if x['direction']=='up' else 'down through'} {fp(x['level'])}" for c in summ["crossed"] for x in c["crossings"]]
        if bits: lines.append(f"Since {since}: " + "; ".join(bits) + ".")
    try: msgs = split_msgs(lines)
    except ValueError as e: print(str(e), file=sys.stderr); return 1
    out = o.out or os.path.join(DISCORD, f"update_{today.month:02d}{today.day:02d}_{hhmm}.md")
    files = [out] + ([out[:-3] + "b.md"] if len(msgs) > 1 else [])
    for f, m in zip(files, msgs): atomic_write(f, m + "\n")
    summ["files"] = files; summ["slots"] = [f"{date}_{hhmm}"] + ([f"{date}_{hhmm}b"] if len(msgs) > 1 else [])
    atomic_write(spath, json.dumps(summ, indent=1)); print(json.dumps(summ, indent=1))
    return 0

if __name__ == "__main__": sys.exit(main())
