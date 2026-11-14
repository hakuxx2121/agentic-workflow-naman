#!/usr/bin/env python3
"""Price snapshot vs this week's levels. Price snapshot vs this week's levels.
Data source (same as old scripts): Yahoo Finance v8 chart API, 1m bars with includePrePost.
Usage: prices.py [--levels PATH] [--session regular|extended] [--near-pct 1.0]
                 [--tickers A,B] [--out PATH] [--fixture FILE.json] [--asof YYYY-MM-DD]
Each row also has "week": week-to-date candle from Yahoo v8 interval=1d range=1mo (open = first regular-session
open on/after Monday of the --asof week; high/low include the session price; week_pct = price vs week open),
or {"error": ...} if that fetch failed.
Default levels: newest ${NDTL_PIPELINE_ROOT}/week_*/levels.json. Prints JSON to stdout; --out also writes it atomically.
Exit: 0 ok, 1 bad args/levels, 6 every ticker failed to fetch."""
import argparse, concurrent.futures as cf, datetime as dt, json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import levels_io
H = {"User-Agent": "Mozilla/5.0"}
SUP = {"support", "stop"}; RES = {"resistance", "trigger"}

def fetch(t):
    import urllib.request
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{t}?interval=1m&range=1d&includePrePost=true"
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=15))["chart"]["result"][0]

def fetch_week(t):
    import urllib.request
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{t}?interval=1d&range=1mo"
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=15))["chart"]["result"][0]

def parse_week(d, asof, px):
    """Week-to-date candle from Yahoo 1d bars: open = first regular-session open on/after Monday of asof's week (ET);
    high/low = daily highs/lows this week plus px; pct = px vs week open."""
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York"); mon = asof - dt.timedelta(days=asof.weekday())
    q = d["indicators"]["quote"][0]; ts = d.get("timestamp") or []
    bars = [(dt.datetime.fromtimestamp(ts[i], et).date(), q["open"][i], q["high"][i], q["low"][i]) for i in range(len(ts))
            if q["open"][i] is not None]
    bars = [b for b in bars if mon <= b[0] <= asof]
    if not bars: raise ValueError(f"no daily bars since {mon}")
    wo = bars[0][1]
    hi = max([b[2] for b in bars if b[2] is not None] + [px]); lo = min([b[3] for b in bars if b[3] is not None] + [px])
    return {"week_start": mon.isoformat(), "week_open": round(wo, 4), "week_high": round(hi, 4), "week_low": round(lo, 4),
            "week_pct": round((px / wo - 1) * 100, 2), "color": "green" if px > wo else "red" if px < wo else "flat"}

def parse(d):
    m = d["meta"]; q = d["indicators"]["quote"][0]; ts = d.get("timestamp") or []
    per = m.get("currentTradingPeriod", {}); rs = per.get("regular", {})
    bars = [(ts[i], q["close"][i]) for i in range(len(ts)) if q["close"][i]]
    reg = m.get("regularMarketPrice")
    pre = [b for b in bars if rs.get("start") and b[0] < rs["start"]]
    post = [b for b in bars if rs.get("end") and b[0] >= rs["end"]]
    ext = post[-1] if post else (pre[-1] if pre else None)
    tm = lambda s: dt.datetime.fromtimestamp(s).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    return {"regular_price": reg, "regular_time": tm(m["regularMarketTime"]) if m.get("regularMarketTime") else None,
            "prev_close": m.get("chartPreviousClose") or m.get("previousClose"),
            "ext_session": ("post" if post else "pre") if ext else None,
            "ext_price": round(ext[1], 4) if ext else None, "ext_time": tm(ext[0]) if ext else None}

def classify(px, levels, near):
    below = [L for L in levels if L["price"] <= px]; above = [L for L in levels if L["price"] > px]
    ns = max(below, key=lambda L: L["price"]) if below else None
    nr = min(above, key=lambda L: L["price"]) if above else None
    sups = [L["price"] for L in levels if L["role"] in SUP]; ress = [L["price"] for L in levels if L["role"] in RES]
    if not levels: status = "no levels"
    elif ress and px > max(ress): status = "above resistance"
    elif sups and px < min(sups): status = "below support"
    else:
        c = min(levels, key=lambda L: abs(px / L["price"] - 1))
        dist = abs(px / c["price"] - 1) * 100
        status = f"within {near:g}% of {c['price']:g} ({c['role']})" if dist <= near else "in range"
    f = lambda L: None if not L else {**L, "dist_pct": round((L["price"] / px - 1) * 100, 2)}
    return f(ns), f(nr), status

def snapshot(t, levels, session, near, fetcher, week_fetcher=None, asof=None):
    try: p = parse(fetcher(t))
    except Exception as e: return {"symbol": t, "error": f"{type(e).__name__}: {e}"}
    px = p["ext_price"] if session == "extended" and p["ext_price"] else p["regular_price"]
    pc = p["prev_close"]
    ns, nr, st = classify(px, levels, near)
    try: week = parse_week((week_fetcher or fetch_week)(t), asof or dt.date.today(), px)
    except Exception as e: week = {"error": f"{type(e).__name__}: {e}"}  # weekly text is optional; never fail the run
    return {"symbol": t, "last": round(px, 4), "price_basis": "extended" if px is p["ext_price"] else "regular", **p,
            "change_pct": round((p["regular_price"] / pc - 1) * 100, 2) if pc else None,
            "ext_change_pct": round((p["ext_price"] / p["regular_price"] - 1) * 100, 2) if p["ext_price"] and p["regular_price"] else None,
            "nearest_support": ns, "nearest_resistance": nr, "status": st, "week": week}

def main(a=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--levels"); ap.add_argument("--session", choices=["regular", "extended"], default="regular")
    ap.add_argument("--near-pct", type=float, default=1.0); ap.add_argument("--tickers"); ap.add_argument("--out"); ap.add_argument("--fixture")
    ap.add_argument("--asof", help="YYYY-MM-DD for the week-to-date candle (default today)")
    o = ap.parse_args(a)
    try: path = o.levels or levels_io.latest_levels_path(); L = levels_io.read_levels(path)
    except Exception as e: print(f"levels error: {e}", file=sys.stderr); return 1
    by = {t["symbol"]: t["levels"] for t in L["tickers"]}
    syms = [s.strip().upper() for s in o.tickers.split(",")] if o.tickers else list(by)
    fetcher, wfetch = fetch, fetch_week
    asof = dt.date.fromisoformat(o.asof) if o.asof else dt.date.today()
    if o.fixture:  # fixture keys: "SYM" = 1m chart, "SYM@1d" = daily chart (missing -> weekly fetch fails)
        fx = json.load(open(o.fixture)); fetcher = lambda t: fx[t]; wfetch = lambda t: fx[t + "@1d"]
    with cf.ThreadPoolExecutor(8) as ex:
        rows = list(ex.map(lambda s: snapshot(s, by.get(s, []), o.session, o.near_pct, fetcher, wfetch, asof), syms))
    out = {"generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "session": o.session,
           "levels_file": path, "week_of": L["week_of"], "tickers": rows}
    s = json.dumps(out, indent=1)
    if o.out:
        d = os.path.dirname(os.path.abspath(o.out)); os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d)
        with os.fdopen(fd, "w") as f: f.write(s); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, o.out)
    print(s)
    return 6 if rows and all("error" in r for r in rows) else 0

if __name__ == "__main__": sys.exit(main())
