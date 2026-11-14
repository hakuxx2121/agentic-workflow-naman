#!/usr/bin/env python3
"""
fit_or.py - test candidate "opening impulse" rules against measured Paper Prophet (PP) opening ranges.

USAGE
  python3 fit_or.py [--truth pp_or_truth.csv] [--tf 1m|15s] [--bars-dir bars] [--tol 0.05]
                    [--max-minutes 60] [--detail] [--rule NAME]

INPUTS
  pp_or_truth.csv columns:
    ticker,date,pp_orh,pp_orl,orh_lock_time,orl_lock_time,open_930,open_wick_high,open_wick_low,notes[,tol]
    (optional last column tol = per-row tolerance; --global-tol ignores it)
    (date = YYYY-MM-DD, times = HH:MM or HH:MM:SS New York time; lock times / open_* / notes are optional)
  Bars (New York time, regular + optional premarket), looked up in this order:
    1. <bars-dir>/<TICKER>_<date>_<tf>.csv        e.g. bars/AVGO_2026-11-06_15s.csv
    2. <bars-dir>/<TICKER>_<tf>.csv               one file with many days
    3. ./data/<TICKER>_1m.csv                     (only for --tf 1m; yfinance dumps already on the box)
  Columns (case-insensitive): Datetime (or time/timestamp, tz-aware or NY-local), Open, High, Low, Close.

WHAT IT DOES
  For every truth row it runs every candidate rule (each with a small parameter grid) on the first
  --max-minutes of RTH bars and checks ORH and ORL separately against PP within --tol.
  Reports per rule family: best parameters, #sides matched (ORH/ORL count separately), #rows matched
  (both sides), and with --detail the per-row result of the best parameters (value, diff, lock time).

RULE FAMILIES (all sides independent, run on the bars' timeframe, mirrors Pine f_impulseOR semantics)
  fixed_window   baseline: high/low of the first N minutes (N in 1,3,5,10,15,30)
  range_snap     lock a side when price retraces P% of the CURRENT opening range from the running extreme
  price_snap     lock a side when price retraces P% of PRICE from the running extreme
  atr_pullback   lock when retrace >= K x ATR(14) of the confirm-TF bars (premarket bars used if supplied)
  n_candle       lock after N consecutive candles closing against the extreme (red after the high / green after the low)
  nonext         lock a side after N consecutive bars that fail to make a new extreme (eq=1: equal high/low counts as extending)
  pivot          lock at the first swing pivot (k bars each side) formed after the extreme, high=pivot high, low=pivot low
  Every family is also tried with skip_open in {0,1,2}: the first N bars' WICKS are ignored
  (only their closes count), and with min_minutes in {0,3}. A side that never locks is force-locked
  at --max-minutes.
"""
import argparse, glob, os, sys, itertools
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
NY = "America/New_York"

# ----------------------------------------------------------------------------- loading
def _norm(df):
    df = df.rename(columns={c: c.strip().capitalize() for c in df.columns})
    tcol = next((c for c in df.columns if c.lower() in ("datetime", "time", "timestamp", "date")), df.columns[0])
    raw = df[tcol].astype(str)
    if raw.str.contains(r"[+-]\d\d:?\d\d$|Z$").any():      # tz-aware strings (mixed DST offsets ok)
        idx = pd.to_datetime(raw, utc=True).dt.tz_convert(NY)
    else:                                                    # naive = New York local time
        idx = pd.to_datetime(raw).dt.tz_localize(NY)
    df = df.set_index(idx)
    df.index.name = "Datetime"
    return df[["Open", "High", "Low", "Close"]].astype(float).sort_index()

def load_bars(ticker, date, tf, bars_dir):
    cands = [os.path.join(bars_dir, f"{ticker}_{date}_{tf}.csv"),
             os.path.join(bars_dir, f"{ticker}_{tf}.csv")]
    if tf == "1m":
        cands.append(os.path.join(HERE, "data", f"{ticker}_1m.csv"))
    for p in cands:
        if os.path.exists(p):
            d = _norm(pd.read_csv(p))
            d = d[d.index.strftime("%Y-%m-%d") == date]
            if len(d):
                return d, p
    return None, None

def apply_overrides(bars, ticker, date, path):
    """Patch individual OHLC fields from a CSV of TradingView Data Window prints."""
    if not path or not os.path.exists(path):
        return bars
    ov = pd.read_csv(path, dtype=str)
    hit = ov[(ov["ticker"].str.upper() == str(ticker).upper()) & (ov["date"] == date)]
    if hit.empty:
        return bars
    out = bars.copy()
    for _, r in hit.iterrows():
        hh, mm = (r["time"].strip().split(":") + ["0"])[:2]
        # match bar by date + clock, ignoring seconds (bars may still be a multi-day frame)
        idx = out.index[(out.index.strftime("%Y-%m-%d") == date)
                        & (out.index.hour == int(hh)) & (out.index.minute == int(mm))]
        if len(idx) == 0:
            print(f"[override] no bar {ticker} {date} {r['time']}")
            continue
        field = str(r["field"]).strip().capitalize()
        if field not in out.columns:
            print(f"[override] bad field {field}")
            continue
        out.loc[idx[0], field] = float(r["value"])
        print(f"[override] {ticker} {date} {r['time']} {field} -> {r['value']}")
    return out

def resample_bars(bars, rule):
    """Resample to a pandas offset alias (3min, 5min). Labels at left (bar open), closed left."""
    if not rule:
        return bars
    # pandas 3 uses 'min' not 'T'
    rule = rule.replace("m", "min").replace("Min", "min") if rule[-1] in "mM" and rule[:-1].isdigit() else rule
    if rule.endswith("m") and not rule.endswith("min"):
        rule = rule[:-1] + "min"
    agg = bars.resample(rule, label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"})
    return agg.dropna(how="any")

def hhmm(s):
    s = str(s).strip()
    if not s or s == "nan": return None
    p = [int(x) for x in s.split(":")]
    return p[0] * 3600 + p[1] * 60 + (p[2] if len(p) > 2 else 0)

# ----------------------------------------------------------------------------- helpers
def split_day(bars, max_min, tf_sec):
    """-> (pre, rth) where rth = bars from 09:30 to 09:30+max_min."""
    t = bars.index
    sod = (t.hour * 3600 + t.minute * 60 + t.second)
    rth = bars[(sod >= 9 * 3600 + 1800) & (sod < 9 * 3600 + 1800 + max_min * 60)]
    pre = bars[sod < 9 * 3600 + 1800]
    return pre, rth

def tf_seconds(bars):
    if len(bars) < 2: return 60
    d = np.median(np.diff(bars.index.values).astype("timedelta64[s]").astype(int))
    return int(d) if d > 0 else 60

def sod(ts): return ts.hour * 3600 + ts.minute * 60 + ts.second

def fmt(sec):
    return None if sec is None else f"{sec//3600:02d}:{(sec%3600)//60:02d}:{sec%60:02d}"

# ----------------------------------------------------------------------------- generic side engine
# One function drives both sides: side=+1 high, -1 low. Work in "sign space": x = side*price so the
# extreme is always a maximum.
def run_side(rth, side, lock_fn, skip_open, min_min, max_min, eq_ext=False, count_after=0, min_rng=0.0):
    """lock_fn(state)->bool decides locking. state dict has: ext, since (worst price since ext, sign space),
    rng, price, i, closes_against, pivot flags... Returns (level, lock_second, forced).
    count_after: do not accumulate quiet/nonext until this many minutes after 9:30 (extremes still update).
    min_rng: do not accumulate quiet/nonext until the running range is at least this wide.
    """
    H = rth["High"].values * 1.0; L = rth["Low"].values * 1.0
    O = rth["Open"].values; C = rth["Close"].values
    if side < 0:  # sign space: high' = -low, low' = -high
        H, L = -rth["Low"].values, -rth["High"].values
        O, C = -O, -C
    n = len(rth); t0 = sod(rth.index[0]); step = tf_seconds(rth)
    ext = None; since = None; against = 0; nonext = 0
    opp_ext = None  # the other side's running extreme (for range), in sign space of THIS side (min)
    for i in range(n):
        skip = i < skip_open
        h = C[i] if skip else H[i]
        l = C[i] if skip else L[i]
        if i == 0:
            ext = h; since = C[i]; opp_ext = l; against = 1 if C[i] <= O[i] else 0; nonext = 0
        else:
            opp_ext = min(opp_ext, l)
            if h > ext or (eq_ext and h >= ext):
                ext = h; since = C[i]; against = 1 if C[i] <= O[i] else 0; nonext = 0
            else:
                since = min(since, l)
                # Quiet count is gated: pauses before count_after (or before the
                # range is wide enough) are ignored; the counter stays at 0.
                elapsed_now = sod(rth.index[i]) + step - t0
                counting = (elapsed_now >= count_after * 60
                            and (ext - min(opp_ext, l)) >= min_rng - 1e-12)
                if counting:
                    against = against + 1 if C[i] <= O[i] else 0
                    nonext += 1
                else:
                    against = 0
                    nonext = 0
        elapsed = sod(rth.index[i]) + step - t0
        okmin = elapsed >= min_min * 60
        forced = elapsed >= max_min * 60 or i == n - 1
        st = dict(i=i, ext=ext, since=since, rng=ext - opp_ext, against=against, nonext=nonext,
                  price=abs(ext), H=H, L=L, C=C, O=O, n=n, skip_open=skip_open,
                  elapsed=elapsed, retrace=ext - since)
        if okmin and lock_fn(st):
            return side * ext, sod(rth.index[i]) + step, False
        if forced:
            return side * ext, sod(rth.index[i]) + step, True
    return None, None, True

# ---- lock rules (take state dict) -------------------------------------------------------------
def rule_range_snap(p):  return lambda s: s["rng"] > 0 and (s["ext"] - s["since"]) >= s["rng"] * p / 100
def rule_price_snap(p):  return lambda s: (s["ext"] - s["since"]) >= s["price"] * p / 100
def rule_nonext(k):    return lambda s: s["nonext"] >= k
def rule_n_candle(k):    return lambda s: s["against"] >= k
def rule_close_inside(mode):
    # In sign space, a close "back through the high" is C[i] < ext (mode=ext).
    # Mode=rng: close has retraced back inside the running range (C < ext and C > opp, i.e. C < ext always
    # once it is not at the extreme; we treat C[i] < ext - 0 as inside if it is strictly below the extreme).
    if mode == "ext":
        return lambda s: s["C"][s["i"]] < s["ext"]
    return lambda s: s["C"][s["i"]] < s["ext"] and s["C"][s["i"]] > (s["ext"] - s["rng"])
def rule_atr(kx, atr):   return lambda s: (s["ext"] - s["since"]) >= kx * atr
def rule_nonext_retrace(n, p=None, k=None, atr=0.0):
    """Quiet-N AND a pullback of p% of range, or k x ATR (whichever args are set; both required if both given)."""
    def f(s):
        if s["nonext"] < n:
            return False
        ok = True
        if p is not None:
            ok = ok and s["rng"] > 0 and (s["ext"] - s["since"]) >= s["rng"] * p / 100
        if k is not None:
            ok = ok and (s["ext"] - s["since"]) >= k * atr
        return ok
    return f
def rule_pivot(k):
    # lock when the extreme bar has k bars after it that all have lower highs (in sign space), i.e. pivot confirmed
    def f(s):
        i = s["i"]; H = s["H"]
        if i < k: return False
        j = i - k                      # candidate pivot bar
        if j < 0: return False
        # extreme must be at bar j (first bar of that high) and bars j+1..i all lower highs
        if abs(H[j] - s["ext"]) > 1e-9 and not (H[j] >= s["ext"] - 1e-9): return False
        return all(H[m] < H[j] for m in range(j + 1, i + 1))
    return f

def atr_of(pre, rth, n=14):
    allb = pd.concat([pre, rth]) if len(pre) else rth
    if len(allb) < 3: return float(rth["High"].max() - rth["Low"].min()) / 5
    pc = allb["Close"].shift(1)
    tr = pd.concat([allb["High"] - allb["Low"], (allb["High"] - pc).abs(), (allb["Low"] - pc).abs()], axis=1).max(axis=1)
    return float(tr.dropna().tail(n).mean())

# ----------------------------------------------------------------------------- families + grids
def families():
    fam = {}
    fam["range_snap"] = [dict(p=p) for p in (5, 8, 10, 12, 15, 18, 20, 22, 25, 30, 35, 40, 50, 60)]
    fam["price_snap"] = [dict(p=p) for p in (0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0, 1.5, 2.0)]
    fam["atr_pullback"] = [dict(k=k) for k in (0.5, 1, 1.5, 2, 3, 4)]
    fam["n_candle"] = [dict(n=n) for n in (1, 2, 3, 4, 5)]
    fam["pivot"] = [dict(k=k) for k in (1, 2, 3, 5)]
    ns = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
    fam["nonext"] = [dict(n=n, eq=e) for n in ns for e in (0, 1)]
    # close back through the extreme (close_vs=ext) or close back inside the running range (close_vs=rng)
    fam["close_inside"] = [dict(mode=m) for m in ("ext", "rng")]
    # quiet-N counting only after the first F minutes (F=5: ignore pauses inside the first 5m bar)
    fam["nonext_from"] = [dict(n=n, eq=0, from_min=f) for n in (3, 4, 5, 6, 7) for f in (5, 10, 15)]
    # quiet-N AND a percent-of-range or ATR pullback
    fam["nonext_retrace"] = (
        [dict(n=n, eq=0, p=p) for n in (3, 4, 5, 6, 7) for p in (10, 15, 20, 25, 30, 40, 50)]
        + [dict(n=n, eq=0, k=k) for n in (3, 4, 5, 6, 7) for k in (0.25, 0.5, 0.75, 1.0, 1.5, 2.0)]
    )
    # quiet-N, but the quiet clock only runs once the running range is at least
    # k x ATR, or at least the first 5-minute bar's range (first5=1).
    fam["nonext_minrng"] = (
        [dict(n=n, eq=0, k=k, first5=0) for n in (4,) for k in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0)]
        + [dict(n=n, eq=0, k=0, first5=1) for n in (3, 4, 5, 6, 7)]
        + [dict(n=n, eq=0, k=k, first5=1) for n in (4,) for k in (0.5, 1.0, 1.5, 2.0)]
    )
    return fam

def make_lock(name, prm, atr):
    return {"range_snap": lambda: rule_range_snap(prm["p"]), "price_snap": lambda: rule_price_snap(prm["p"]),
            "atr_pullback": lambda: rule_atr(prm["k"], atr), "n_candle": lambda: rule_n_candle(prm["n"]),
            "pivot": lambda: rule_pivot(prm["k"]), "nonext": lambda: rule_nonext(prm["n"]),
            "close_inside": lambda: rule_close_inside(prm["mode"]),
            "nonext_from": lambda: rule_nonext(prm["n"]),
            "nonext_retrace": lambda: rule_nonext_retrace(prm["n"], prm.get("p"), prm.get("k"), atr),
            "nonext_minrng": lambda: rule_nonext(prm["n"])}[name]()

def eval_rule(name, prm, skip, minm, rows, maxm, tol):
    out = []
    for r in rows:
        if name == "fixed_window":
            d = r["rth"]; w = d[d.index < d.index[0] + pd.Timedelta(minutes=prm["n"])]
            h, l = float(w["High"].max()), float(w["Low"].min()); th = tl = None; fh = fl = False
            # fixed window: skip_open ignores first bars' wicks too
            if skip:
                w2 = w.copy(); w2.iloc[:skip, w2.columns.get_loc("High")] = w2["Close"].iloc[:skip]
                w2.iloc[:skip, w2.columns.get_loc("Low")] = w2["Close"].iloc[:skip]
                h, l = float(w2["High"].max()), float(w2["Low"].min())
            th = tl = sod(w.index[-1]) + tf_seconds(w)
        else:
            lk = make_lock(name, prm, r["atr"])
            ca = prm.get("from_min", 0)
            mr = 0.0
            if name == "nonext_minrng":
                if prm.get("first5"):
                    mr = max(mr, r.get("first5_rng") or 0.0)
                if prm.get("k"):
                    mr = max(mr, float(prm["k"]) * (r["atr"] or 0.0))
            h, th, fh = run_side(r["rth"], +1, lk, skip, minm, maxm, prm.get("eq", 0), count_after=ca, min_rng=mr)
            lk = make_lock(name, prm, r["atr"])
            l, tl, fl = run_side(r["rth"], -1, lk, skip, minm, maxm, prm.get("eq", 0), count_after=ca, min_rng=mr)
        out.append(dict(ticker=r["ticker"], date=r["date"], orh=h, orl=l, th=th, tl=tl, fh=fh, fl=fl,
                        okh=(None if r["pp_orh"] is None else bool(h is not None and abs(h - r["pp_orh"]) <= r.get("tol", tol))),
                        okl=(None if r["pp_orl"] is None else bool(l is not None and abs(l - r["pp_orl"]) <= r.get("tol", tol)))))
    return out

# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--truth", default=os.path.join(HERE, "pp_or_truth.csv"))
    ap.add_argument("--tf", default="1m", help="bar timeframe label used in file names: 1m, 15s ...")
    ap.add_argument("--bars-dir", default=os.path.join(HERE, "bars"))
    ap.add_argument("--tol", type=float, default=0.05)
    ap.add_argument("--max-minutes", type=int, default=60)
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--global-tol", action="store_true", help="ignore the per-row tol column; use --tol for every row")
    ap.add_argument("--only-measured", action="store_true", help="only rows whose notes start with MEASURED")
    ap.add_argument("--rule", default=None, help="only this family")
    ap.add_argument("--resample", default=None, help="resample loaded bars to this TF before fitting, e.g. 3min, 5min")
    ap.add_argument("--overrides", default=None, help="CSV of TV print overrides: ticker,date,time,field,value (time=HH:MM, field=Open/High/Low/Close)")
    ap.add_argument("--floor-tol", action="store_true", dest="floor_tol",
                    help="use max(--tol, per-row tol) so --tol is a floor")
    ap.add_argument("--plus-tol", action="store_true", dest="plus_tol",
                    help="effective tol = per-row precision + --tol (e.g. 0.06 plus the stated ±, for Yahoo vs TV noise)")
    ap.add_argument("--quiet-grid", action="store_true", help="expand nonext N to 1..10")
    ap.add_argument("--min-grid", default=None,
                    help="comma-separated min-minutes values to try (default: 0,3; use 0,3,5,10,15,20 for the T-gate search)")
    a = ap.parse_args()

    truth = pd.read_csv(a.truth, dtype=str)
    if a.only_measured:
        truth = truth[truth["notes"].fillna("").str.startswith("MEASURED")]
    rows = []
    for _, t in truth.iterrows():
        bars, path = load_bars(t["ticker"], t["date"], a.tf, a.bars_dir)
        if bars is None:
            print(f"[skip] no {a.tf} bars for {t['ticker']} {t['date']}"); continue
        if getattr(a, "overrides", None):
            bars = apply_overrides(bars, t["ticker"], t["date"], a.overrides)
        if getattr(a, "resample", None):
            bars = resample_bars(bars, a.resample)
        pre, rth = split_day(bars, a.max_minutes, tf_seconds(bars))
        if len(rth) < 3:
            print(f"[skip] <3 RTH bars for {t['ticker']} {t['date']} ({path})"); continue
        def _side(col):
            v = t.get(col, "")
            if v is None or str(v).strip() in ("", "nan", "None", "?"):
                return None
            return float(v)
        # per-row tol: max(--tol, row tol) so a global 0.06 floor can be combined with tighter reads
        row_tol = a.tol
        if "tol" in t.index and str(t["tol"]) not in ("nan", "") and not a.global_tol:
            rt = float(t["tol"])
            if a.plus_tol:
                row_tol = rt + a.tol          # per-row precision plus the --tol floor (Yahoo/TV noise)
            elif a.floor_tol:
                row_tol = max(a.tol, rt)
            else:
                row_tol = rt
        # first 5-minute bar range (9:30-9:35), for the min-range gate
        first5 = rth[rth.index < rth.index[0] + pd.Timedelta(minutes=5)]
        first5_rng = (float(first5["High"].max()) - float(first5["Low"].min())) if len(first5) else 0.0
        rows.append(dict(ticker=t["ticker"], date=t["date"], pp_orh=_side("pp_orh"), pp_orl=_side("pp_orl"),
                         tol=row_tol,
                         lh=hhmm(t.get("orh_lock_time")), ll=hhmm(t.get("orl_lock_time")),
                         pre=pre, rth=rth, atr=atr_of(pre, rth), first5_rng=first5_rng))
    if not rows:
        sys.exit("no usable rows")
    print(f"{len(rows)} truth rows, bars tf={a.tf}, tol=±{a.tol}, window={a.max_minutes} min\n")

    fam = families()
    fam = {"fixed_window": [dict(n=n) for n in (1, 2, 3, 4, 5, 10, 15, 20, 25, 30, 45, 60)], **fam}
    if a.rule: fam = {a.rule: fam[a.rule]}
    results = []
    for name, grid in fam.items():
        for prm in grid:
            min_grid = (0, 3)
            if a.min_grid:
                min_grid = tuple(int(x) for x in a.min_grid.split(",") if x.strip()!="")
            for skip in (0, 1, 2):
                for minm in ((0,) if name == "fixed_window" else min_grid):
                    res = eval_rule(name, prm, skip, minm, rows, a.max_minutes, a.tol)
                    sides = sum(int(x["okh"] is True) + int(x["okl"] is True) for x in res)
                    # a row matches when every known side is ok (unknown sides ignored)
                    both = sum(int((x["okh"] is not False) and (x["okl"] is not False)
                                   and (x["okh"] is True or x["okl"] is True)) for x in res)
                    # lock-time agreement (when truth gives one): within 90s
                    tm = tc = 0
                    for x, r in zip(res, rows):
                        for tk, lk in (("th", "lh"), ("tl", "ll")):
                            if r[lk] is not None and x[tk] is not None:
                                tc += 1; tm += abs(x[tk] - r[lk]) <= 90 + (tf_seconds(r["rth"]))
                    results.append(dict(rule=name, prm=prm, skip=skip, minm=minm, sides=sides, rows=both, tm=tm, tc=tc, res=res))
    results.sort(key=lambda r: (-r["rows"], -r["sides"], -r["tm"]))
    nS = sum((1 if r["pp_orh"] is not None else 0) + (1 if r["pp_orl"] is not None else 0) for r in rows)
    print(f"{'rule':14} {'best params':22} skip min  rows-matched sides-matched  lock-time-ok")
    seen = set()
    for r in results:
        if r["rule"] in seen: continue
        seen.add(r["rule"])
        print(f"{r['rule']:14} {str(r['prm']):22} {r['skip']:>4} {r['minm']:>3}  {r['rows']:>4}/{len(rows):<8} {r['sides']:>4}/{nS:<8} {r['tm']}/{r['tc']}")
    print("\nTop 10 overall:")
    for r in results[:10]:
        print(f"  {r['rule']:14} {str(r['prm']):18} skip={r['skip']} min={r['minm']}  rows {r['rows']}/{len(rows)}  sides {r['sides']}/{nS}")
    perfect = [r for r in results if r["rows"] == len(rows) and r["sides"] == nS]
    print(f"\nPerfect fits (all {len(rows)} rows, all {nS} sides): {len(perfect)}")
    for r in perfect:
        print(f"  {r['rule']:16} {str(r['prm']):28} skip={r['skip']} min={r['minm']}")
    almost = [r for r in results if r["rows"] >= len(rows)-1 or r["sides"] >= nS-1]
    # de-dupe into a short list of unique (rule,prm,skip,minm) already in results order
    print(f"\nNear-perfect (missing at most 1 row or 1 side), first 20:")
    for r in almost[:20]:
        print(f"  {r['rule']:16} {str(r['prm']):28} skip={r['skip']} min={r['minm']}  rows {r['rows']}/{len(rows)}  sides {r['sides']}/{nS}")
    if a.detail:
        b = results[0]
        print(f"\nPer-row detail for best: {b['rule']} {b['prm']} skip={b['skip']} min={b['minm']}")
        for x, r in zip(b["res"], rows):
            f = lambda v: "  na  " if v is None else f"{v:8.2f}"
            def side(pp, got, ok, lock, forced, name):
                pps = "    n/a" if pp is None else f"{pp:8.2f}"
                tag = "  - " if ok is None else ("OK " if ok else "BAD")
                return f"{name} pp={pps} got={f(got)} {tag} lock={fmt(lock)}{' (forced)' if forced else ''}"
            print(f"  {x['ticker']:5} {x['date']}  {side(r['pp_orh'], x['orh'], x['okh'], x['th'], x['fh'], 'ORH')}"
                  f" | {side(r['pp_orl'], x['orl'], x['okl'], x['tl'], x['fl'], 'ORL')}")
    # rows that NO rule reproduces on a side
    print("\nSides no rule/param reproduces (candidate 'rule breaks here'):")
    any_bad = False
    for i, r in enumerate(rows):
        for side, key, pkey in (("ORH", "okh", "pp_orh"), ("ORL", "okl", "pp_orl")):
            if r[pkey] is None:
                continue
            if not any(res["res"][i][key] is True for res in results):
                print(f"  {r['ticker']} {r['date']} {side}  (pp={r[pkey]})"); any_bad = True
    if not any_bad: print("  none - every side is hit by at least one rule/param (check the best rule is the SAME for all rows)")
    print("\nNOTE: a rule only counts if ONE (rule, params, skip, min) fits all rows; compare 'rows-matched' above.")

if __name__ == "__main__":
    main()
