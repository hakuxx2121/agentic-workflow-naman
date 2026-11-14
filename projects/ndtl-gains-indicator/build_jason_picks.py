#!/usr/bin/env python3
"""
Download 1-minute bars for the Jason's pick watchlist and build
pp_vs_ndtl_jason_picks.csv.

For each ticker-day (US/Eastern regular session):
  prior 4:00 PM regular close, 9:30 1m OHLC, 9:30 5m OHLC,
  first 5/15/30-minute high/low, gap % (open vs prior close),
  and the 4-minute quiet-rule opening range (Pine f_impulseOR port;
  same rule as fit_or.py family nonext, n=4, skip=0, eq=0).

pp_orh/orl/gc and ndtl_orh/orl/gc are left empty for chart reads,
except ARM 2026-11-09 which is filled from pp_vs_ndtl_jason_picks_raw.csv.
"""
from __future__ import annotations

import os, sys, time, math, traceback
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
NY = "America/New_York"
OUT_CSV = os.path.join(HERE, "pp_vs_ndtl_jason_picks.csv")
RAW_CSV = os.path.join(HERE, "pp_vs_ndtl_jason_picks_raw.csv")
FAIL_LOG = os.path.join(HERE, "jason_picks_fetch_failures.txt")

TICKERS = [
    "DIA", "IWM", "QQQ", "SPY",
    "AAPL", "AEHR", "AKAM", "ALAB", "AMAT", "AMD", "AMZN", "ANET", "ARM", "AVGO",
    "BA", "BE", "BMRN",
    "CAT", "COIN", "CRWD", "CRWV",
    "DASH",
    "FLY", "FSLY",
    "GDX", "GEV", "GOOGL",
    "HOOD", "HUT",
    "IBM", "INTC",
    "LEU",
    "MCD", "META", "MRNA", "MRVL", "MU",
    "NBIS", "NET", "NKE", "NVDA", "NXPI",
    "PFE", "PLTR",
    "QCOM",
    "RBRK", "RDDT", "RIVN", "RKLB",
    "SHOP", "SOFI", "SPCX",
    "TEM", "TSLA",
    "UBER",
    "WDC",
    "ZS",
    "SNDK", "APP", "GLW", "VSAT", "NFLX", "LLY", "QXO", "BBY", "COHR", "OKLO",
]

# Yahoo 1m window is ~30 days; existing dumps start 2026-10-13. Go one
# session earlier so Oct 13 has a prior close in the 1m file.
START = date(2026, 10, 13)  # Yahoo 1m only allows the last 30 days; Oct 9 was rejected
END_EXCLUSIVE = date(2026, 11, 10)  # include Nov 9
CHUNK_DAYS = 7  # stay under Yahoo's 8-day 1m cap

# Pine defaults for the opening-impulse quiet rule
QUIET_MIN = 4
MIN_MIN = 10
MAX_MIN = 60
SKIP_OPEN = False


# ----------------------------------------------------------------------------- bars I/O
def _flatten_yf(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["Datetime", "Adj Close", "Close", "High", "Low", "Open", "Volume"])
    if isinstance(df.columns, pd.MultiIndex):
        # either (Price, Ticker) or (Ticker, Price)
        lvl0 = [str(x) for x in df.columns.get_level_values(0)]
        lvl1 = [str(x) for x in df.columns.get_level_values(1)]
        prices = {"Open", "High", "Low", "Close", "Adj Close", "Volume"}
        if set(lvl0) & prices:
            if ticker in lvl1:
                df = df.xs(ticker, axis=1, level=1)
            else:
                df.columns = lvl0
        elif set(lvl1) & prices:
            if ticker in lvl0:
                df = df.xs(ticker, axis=1, level=0)
            else:
                df.columns = lvl1
        else:
            df.columns = lvl0
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    # normalize names
    rename = {}
    for c in df.columns:
        cl = c.lower().replace(" ", "")
        if cl in ("adjclose", "adjustedclose"):
            rename[c] = "Adj Close"
        elif cl == "close":
            rename[c] = "Close"
        elif cl == "high":
            rename[c] = "High"
        elif cl == "low":
            rename[c] = "Low"
        elif cl == "open":
            rename[c] = "Open"
        elif cl == "volume":
            rename[c] = "Volume"
    df = df.rename(columns=rename)
    for need in ("Open", "High", "Low", "Close"):
        if need not in df.columns:
            raise ValueError(f"{ticker}: missing column {need}; have {list(df.columns)}")
    if "Adj Close" not in df.columns:
        df["Adj Close"] = df["Close"]
    if "Volume" not in df.columns:
        df["Volume"] = 0
    idx = df.index
    if not isinstance(idx, pd.DatetimeIndex):
        idx = pd.to_datetime(idx, utc=True)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    df.index = idx.tz_convert(NY)
    df.index.name = "Datetime"
    df = df[["Adj Close", "Close", "High", "Low", "Open", "Volume"]].astype(float)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    # drop all-NaN rows
    df = df.dropna(subset=["Open", "High", "Low", "Close"], how="all")
    return df


def _save_1m(ticker: str, df: pd.DataFrame) -> str:
    os.makedirs(DATA, exist_ok=True)
    path = os.path.join(DATA, f"{ticker}_1m.csv")
    out = df.reset_index()
    # write Datetime with offset, matching existing dumps
    out.to_csv(path, index=False)
    return path


def load_1m(ticker: str) -> pd.DataFrame | None:
    path = os.path.join(DATA, f"{ticker}_1m.csv")
    if not os.path.exists(path):
        return None
    raw = pd.read_csv(path)
    tcol = raw.columns[0]
    idx = pd.to_datetime(raw[tcol], utc=True).dt.tz_convert(NY)
    df = raw.copy()
    df.index = idx
    df.index.name = "Datetime"
    # existing files already have the right names
    cols = {c: c for c in df.columns}
    return df[["Adj Close", "Close", "High", "Low", "Open", "Volume"]].astype(float)


def file_covers_nov9(ticker: str) -> bool:
    df = load_1m(ticker)
    if df is None or df.empty:
        return False
    days = set(df.index.strftime("%Y-%m-%d"))
    return "2026-11-09" in days


def _windows():
    """Inclusive start, exclusive end, 7-day chunks covering START .. END_EXCLUSIVE."""
    d = START
    while d < END_EXCLUSIVE:
        nxt = min(d + timedelta(days=CHUNK_DAYS), END_EXCLUSIVE)
        yield d, nxt
        d = nxt


def fetch_ticker_1m(ticker: str, retries: int = 3) -> tuple[pd.DataFrame | None, str | None]:
    """Download 1m bars in 7-day chunks. Returns (df, error)."""
    parts = []
    last_err = None
    for w0, w1 in _windows():
        got = None
        for attempt in range(retries):
            try:
                raw = yf.download(
                    ticker,
                    start=w0.isoformat(),
                    end=w1.isoformat(),
                    interval="1m",
                    prepost=True,
                    auto_adjust=False,
                    progress=False,
                    threads=False,
                )
                got = _flatten_yf(raw, ticker)
                last_err = None
                break
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                time.sleep(1.5 * (attempt + 1))
        if last_err and got is None:
            return None, f"{ticker} chunk {w0}..{w1}: {last_err}"
        if got is not None and not got.empty:
            parts.append(got)
        time.sleep(0.15)
    if not parts:
        return None, f"{ticker}: no 1m bars returned for {START}..{END_EXCLUSIVE}"
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df, None


def fetch_daily_closes(tickers: list[str]) -> dict[str, pd.Series]:
    """Daily Adj-unadjusted Close, NY dates, for prior-close fallback."""
    out = {}
    # one batch is fine for daily
    try:
        raw = yf.download(
            tickers,
            start=(START - timedelta(days=10)).isoformat(),
            end=END_EXCLUSIVE.isoformat(),
            interval="1d",
            auto_adjust=False,
            progress=False,
            group_by="ticker",
            threads=False,
        )
    except Exception as e:
        print(f"[warn] daily batch failed: {e}")
        raw = None
    if raw is None or raw.empty:
        # try one by one
        for t in tickers:
            try:
                d = yf.download(t, start=(START - timedelta(days=10)).isoformat(),
                                end=END_EXCLUSIVE.isoformat(), interval="1d",
                                auto_adjust=False, progress=False, threads=False)
                d = _flatten_yf(d, t)
                if d.empty:
                    continue
                s = d["Close"].copy()
                s.index = pd.DatetimeIndex(s.index).tz_convert(NY).normalize()
                out[t] = s
            except Exception as e:
                print(f"[warn] daily {t}: {e}")
        return out

    # multi-ticker shape
    if isinstance(raw.columns, pd.MultiIndex):
        # yfinance group_by=ticker -> level 0 is ticker when >1 ticker
        level0 = list(raw.columns.get_level_values(0).unique())
        if "Close" in level0:
            # single-ticker style (Price, Ticker)
            for t in tickers:
                try:
                    d = _flatten_yf(raw, t)
                    if d.empty:
                        continue
                    s = d["Close"].copy()
                    s.index = pd.DatetimeIndex(s.index).tz_convert(NY).normalize()
                    out[t] = s
                except Exception:
                    pass
        else:
            for t in tickers:
                if t not in level0:
                    continue
                try:
                    sub = raw[t].copy() if t in raw.columns.get_level_values(0) else None
                    if sub is None or sub.empty:
                        continue
                    sub = _flatten_yf(sub, t) if isinstance(sub.columns, pd.MultiIndex) else sub
                    if "Close" not in sub.columns:
                        # columns may already be Open/High/Low/Close
                        sub.columns = [str(c).strip() for c in sub.columns]
                    s = sub["Close"].copy().dropna()
                    idx = s.index
                    if idx.tz is None:
                        # daily is often midnight UTC or naive
                        idx = pd.to_datetime(idx)
                        # treat as a calendar date in NY
                        if idx.tz is None:
                            s.index = pd.DatetimeIndex(idx.date)
                        else:
                            s.index = idx.tz_convert(NY).normalize()
                    else:
                        s.index = idx.tz_convert(NY).normalize()
                    # make timezone-naive calendar dates at midnight
                    s.index = pd.DatetimeIndex([pd.Timestamp(i).date() for i in s.index])
                    out[t] = s
                except Exception as e:
                    print(f"[warn] parse daily {t}: {e}")
    else:
        if "Close" in raw.columns:
            # unlikely multi, single
            t = tickers[0]
            s = raw["Close"].copy().dropna()
            s.index = pd.DatetimeIndex([pd.Timestamp(i).date() for i in s.index])
            out[t] = s
    return out


# ----------------------------------------------------------------------------- session helpers
def _sod(ts) -> int:
    return int(ts.hour) * 3600 + int(ts.minute) * 60 + int(ts.second)


def rth_bars(day: pd.DataFrame, start="09:30", end="16:00", end_inclusive=False) -> pd.DataFrame:
    """Bars whose open time is in [start, end) or [start, end] if end_inclusive."""
    sh, sm = map(int, start.split(":"))
    eh, em = map(int, end.split(":"))
    a, b = sh * 3600 + sm * 60, eh * 3600 + em * 60
    sod = day.index.hour * 3600 + day.index.minute * 60 + day.index.second
    if end_inclusive:
        return day[(sod >= a) & (sod <= b)]
    return day[(sod >= a) & (sod < b)]


def first_n_hl(rth: pd.DataFrame, n_min: int) -> tuple[float | None, float | None]:
    if rth is None or rth.empty:
        return None, None
    t0 = rth.index[0]
    # start from the first bar at/after 9:30
    # use 09:30 clock, not first bar (in case of a late open we still want 9:30+N)
    day0 = t0.normalize()
    start = day0 + pd.Timedelta(hours=9, minutes=30)
    end = start + pd.Timedelta(minutes=n_min)
    w = rth[(rth.index >= start) & (rth.index < end)]
    if w.empty:
        return None, None
    return float(w["High"].max()), float(w["Low"].min())


def bar_at(day: pd.DataFrame, hhmm: str) -> pd.Series | None:
    h, m = map(int, hhmm.split(":"))
    target = h * 3600 + m * 60
    sod = day.index.hour * 3600 + day.index.minute * 60 + day.index.second
    w = day[sod == target]
    if w.empty:
        # allow +1s typo like 09:30:01
        w = day[(sod >= target) & (sod < target + 60)]
    if w.empty:
        return None
    return w.iloc[0]


def ohlc5m(rth: pd.DataFrame, start_hhmm="09:30") -> tuple:
    """Build the 5-minute bar starting at start_hhmm from 1m bars."""
    h, m = map(int, start_hhmm.split(":"))
    if rth.empty:
        return (None,) * 4
    day0 = rth.index[0].normalize()
    start = day0 + pd.Timedelta(hours=h, minutes=m)
    end = start + pd.Timedelta(minutes=5)
    w = rth[(rth.index >= start) & (rth.index < end)]
    if w.empty:
        return (None,) * 4
    return (float(w["Open"].iloc[0]), float(w["High"].max()),
            float(w["Low"].min()), float(w["Close"].iloc[-1]))


def prior_regular_close(all_bars: pd.DataFrame, the_date: str, daily: pd.Series | None) -> tuple[float | None, str]:
    """Official prior regular close (4:00 PM). Prefer Yahoo daily Close (official
    auction), then the 16:00 1m close, then 15:59. ARM Nov 6 shows why: daily
    close is 174.62, the 16:00 1m print is 174.72."""
    idx_dates = pd.Index(all_bars.index.strftime("%Y-%m-%d"))
    unique_days = sorted(idx_dates.unique())
    prev = None
    for d in unique_days:
        if d < the_date:
            prev = d
        else:
            break
    m1 = None
    m1src = ""
    if prev is not None:
        day = all_bars[idx_dates == prev]
        b1600 = bar_at(day, "16:00")
        b1559 = bar_at(day, "15:59")
        if b1600 is not None and not (pd.isna(b1600["Close"])):
            m1 = float(b1600["Close"]); m1src = f"1m 16:00 {prev}"
        elif b1559 is not None and not (pd.isna(b1559["Close"])):
            m1 = float(b1559["Close"]); m1src = f"1m 15:59 {prev}"
        else:
            rth = rth_bars(day, "09:30", "16:00", end_inclusive=True)
            if not rth.empty:
                m1 = float(rth["Close"].iloc[-1])
                m1src = f"1m last RTH {prev} {rth.index[-1].strftime('%H:%M')}"
    dcl = None
    dsrc = ""
    if daily is not None and len(daily):
        dts = pd.to_datetime(daily.index).strftime("%Y-%m-%d")
        earlier = daily[dts < the_date]
        if len(earlier):
            dcl = float(earlier.iloc[-1])
            dsrc = f"daily {pd.Timestamp(earlier.index[-1]).date()}"
    if dcl is not None:
        src = dsrc
        if m1 is not None and abs(m1 - dcl) > 0.005:
            src += f" (1m close was {m1:.4f} via {m1src})"
        return dcl, src
    return m1, m1src


def quiet_or(rth_full: pd.DataFrame, quiet_min=QUIET_MIN, min_min=MIN_MIN,
             max_min=MAX_MIN, skip_open=SKIP_OPEN):
    """
    Literal port of ndtl-gains-v2.1.pine f_impulseOR (snap off).
    Locks a side when quiet_min minutes have passed since the close of the
    candle that set that extreme, with nothing beating it. Force-lock at max_min.
    Returns dict: orh, orl, orh_lock (HH:MM:SS of deciding bar's close), orl_lock,
    orh_bar (open time of extreme bar), orl_bar, forced_h, forced_l.
    """
    rth = rth_bars(rth_full, "09:30", "16:00", end_inclusive=False)
    empty = dict(orh=None, orl=None, orh_lock=None, orl_lock=None,
                 orh_bar=None, orl_bar=None, forced_h=None, forced_l=None)
    if rth.empty:
        return empty
    # only need first max_min+1 minutes, but process until both lock or end
    candH = candL = None
    lockH = lockL = None
    extHClose = extLClose = None
    t0 = None
    extH_bar = extL_bar = None
    forced_h = forced_l = False
    orh_lock = orl_lock = None

    for ts, row in rth.iterrows():
        o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
        # Yahoo labels the bar at its open; Pine time_close = open + tf
        # Use 1 minute unless the next bar implies otherwise; 1m dumps are 1m.
        time_open = ts
        # floor sub-minute labels (rare 09:30:01)
        time_open = time_open.floor("min")
        time_close = time_open + pd.Timedelta(minutes=1)
        is_first = t0 is None
        if is_first:
            t0 = time_open
            candH = c if skip_open else h
            candL = c if skip_open else l
            lockH = lockL = None
            extHClose = extLClose = time_close
            extH_bar = extL_bar = time_open
        else:
            if lockH is None and h > candH:
                candH = h
                extHClose = time_close
                extH_bar = time_open
            if lockL is None and l < candL:
                candL = l
                extLClose = time_close
                extL_bar = time_open
        # historical bars are confirmed
        elapsed_ms = (time_close - t0).total_seconds() * 1000
        ok_min = elapsed_ms >= min_min * 60000
        forced = elapsed_ms >= max_min * 60000
        if lockH is None and ok_min and (
            (quiet_min > 0 and extHClose is not None and (time_close - extHClose).total_seconds() >= quiet_min * 60)
            or forced
        ):
            lockH = candH
            orh_lock = time_close
            forced_h = bool(forced and not (
                quiet_min > 0 and extHClose is not None and (time_close - extHClose).total_seconds() >= quiet_min * 60
            ))
        if lockL is None and ok_min and (
            (quiet_min > 0 and extLClose is not None and (time_close - extLClose).total_seconds() >= quiet_min * 60)
            or forced
        ):
            lockL = candL
            orl_lock = time_close
            forced_l = bool(forced and not (
                quiet_min > 0 and extLClose is not None and (time_close - extLClose).total_seconds() >= quiet_min * 60
            ))
        if lockH is not None and lockL is not None:
            break
        # stop after max_min even if we somehow didn't force (no bars)
        if forced:
            break

    def fmt(t):
        return None if t is None else t.strftime("%H:%M:%S")

    return dict(
        orh=None if lockH is None else float(lockH),
        orl=None if lockL is None else float(lockL),
        orh_lock=fmt(orh_lock),
        orl_lock=fmt(orl_lock),
        orh_bar=fmt(extH_bar),
        orl_bar=fmt(extL_bar),
        forced_h=forced_h,
        forced_l=forced_l,
    )


# ----------------------------------------------------------------------------- row builder
def fnum(x, nd=6):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return ""
    # keep enough precision, trim trailing zeros
    s = f"{x:.{nd}f}".rstrip("0").rstrip(".")
    return s


def build_rows(ticker: str, bars: pd.DataFrame, daily: pd.Series | None) -> list[dict]:
    rows = []
    # group by calendar date in NY
    dates = sorted(set(bars.index.strftime("%Y-%m-%d")))
    for d in dates:
        day = bars[bars.index.strftime("%Y-%m-%d") == d]
        rth = rth_bars(day, "09:30", "16:00", end_inclusive=False)
        if rth.empty:
            continue  # weekend / holiday / only pre/post
        b930 = bar_at(day, "09:30")
        if b930 is None:
            # late open: use first RTH bar, note it
            b930 = rth.iloc[0]
            late = True
            b930_time = rth.index[0].strftime("%H:%M:%S")
        else:
            late = False
            b930_time = "09:30:00"
        o5, h5b, l5b, c5 = ohlc5m(rth, "09:30")
        h5, l5 = first_n_hl(rth, 5)
        h15, l15 = first_n_hl(rth, 15)
        h30, l30 = first_n_hl(rth, 30)
        h45, l45 = first_n_hl(rth, 45)
        h60, l60 = first_n_hl(rth, 60)
        # inclusive of the clock-time bar: 15m incl 09:45, 30m incl 10:00, etc.
        h15i, l15i = first_n_hl(rth, 16)
        h30i, l30i = first_n_hl(rth, 31)
        h45i, l45i = first_n_hl(rth, 46)
        h60i, l60i = first_n_hl(rth, 61)
        # N=1,2,3,4,10 (2 and 10 = PP Opening Range input '2' as 2 minutes or two 5m bars)
        h1, l1 = first_n_hl(rth, 1)
        h2, l2 = first_n_hl(rth, 2)
        h3, l3 = first_n_hl(rth, 3)
        h4, l4 = first_n_hl(rth, 4)
        h10, l10 = first_n_hl(rth, 10)

        prior, prior_src = prior_regular_close(bars, d, daily)
        open_px = float(b930["Open"])
        gap_pct = None if prior in (None, 0) else (open_px - prior) / prior * 100.0

        q4 = quiet_or(rth, quiet_min=4)
        q3 = quiet_or(rth, quiet_min=3)
        q5 = quiet_or(rth, quiet_min=5)

        notes = []
        if late:
            notes.append(f"first RTH bar {b930_time} (no 09:30 print)")
        if prior is None:
            notes.append("missing prior close")

        rows.append(dict(
            ticker=ticker,
            date=d,
            pp_orh="", pp_orl="", pp_gc="",
            ndtl_orh="", ndtl_orl="", ndtl_gc="",
            prior_close=prior,
            prior_close_src=prior_src,
            gap_pct=gap_pct,
            b930_1m_o=float(b930["Open"]),
            b930_1m_h=float(b930["High"]),
            b930_1m_l=float(b930["Low"]),
            b930_1m_c=float(b930["Close"]),
            b930_5m_o=o5, b930_5m_h=h5b, b930_5m_l=l5b, b930_5m_c=c5,
            h1=h1, l1=l1, h2=h2, l2=l2, h3=h3, l3=l3, h4=h4, l4=l4,
            h5=h5, l5=l5, h10=h10, l10=l10,
            h15=h15, l15=l15, h30=h30, l30=l30,
            h45=h45, l45=l45, h60=h60, l60=l60,
            h15_incl=h15i, l15_incl=l15i,
            h30_incl=h30i, l30_incl=l30i,
            h45_incl=h45i, l45_incl=l45i,
            h60_incl=h60i, l60_incl=l60i,
            quiet3_orh=q3["orh"], quiet3_orl=q3["orl"],
            quiet3_orh_lock=q3["orh_lock"], quiet3_orl_lock=q3["orl_lock"],
            quiet4_orh=q4["orh"], quiet4_orl=q4["orl"],
            quiet4_orh_lock=q4["orh_lock"], quiet4_orl_lock=q4["orl_lock"],
            quiet4_orh_bar=q4["orh_bar"], quiet4_orl_bar=q4["orl_bar"],
            quiet5_orh=q5["orh"], quiet5_orl=q5["orl"],
            quiet5_orh_lock=q5["orh_lock"], quiet5_orl_lock=q5["orl_lock"],
            is_biggest_gap_up=0,
            is_biggest_gap_down=0,
            notes="; ".join(notes),
        ))
    # flag biggest gap up / down among days that have a gap_pct
    scored = [r for r in rows if r["gap_pct"] is not None]
    if scored:
        up = max(scored, key=lambda r: r["gap_pct"])
        down = min(scored, key=lambda r: r["gap_pct"])
        up["is_biggest_gap_up"] = 1
        down["is_biggest_gap_down"] = 1
        # if only one day, both flags can be on the same row; that's honest
    return rows


def _parse_level(v):
    """Extract a numeric level from a chart-read cell. Returns (number_or_empty, raw_text)."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "", ""
    raw = str(v).strip()
    if raw.lower() in ("", "nan", "not read", "not tooltip-read", "unattributed", "n/a"):
        return "", raw
    # leading ~ or first number in the string
    s = raw.replace(",", "")
    import re
    m = re.search(r"[-+]?(?:\d+\.?\d*|\.\d+)", s)
    if not m:
        return "", raw
    return m.group(0), raw


def fill_from_raw(rows: list[dict]) -> None:
    """Fill ndtl_* (and ARM pp_*) from the chart-read raw CSV, Nov 9 rows only."""
    if not os.path.exists(RAW_CSV):
        print(f"[warn] no {RAW_CSV}")
        return
    raw = pd.read_csv(RAW_CSV)
    by_t = {str(t).upper(): row for t, row in raw.set_index(raw["ticker"].astype(str).str.upper()).iterrows()}
    nfill = 0
    for r in rows:
        if r["date"] != "2026-11-09":
            continue
        s = by_t.get(r["ticker"])
        if s is None:
            continue
        # NDTL levels from tooltip/crosshair reads
        for col, src in (("ndtl_orh", "ndtl_orh"), ("ndtl_orl", "ndtl_orl"), ("ndtl_gc", "ndtl_gc")):
            num, rawt = _parse_level(s.get(src, ""))
            r[col] = num
            if rawt and rawt != num and rawt.lower() not in ("", "nan"):
                extra = f"{col} chart='{rawt}'"
                r["notes"] = (r["notes"] + "; " if r["notes"] else "") + extra
        # chart 9:30 5m vs yfinance
        diffs = []
        for ck, yk in (("b930_o", "b930_5m_o"), ("b930_h", "b930_5m_h"),
                       ("b930_l", "b930_5m_l"), ("b930_c", "b930_5m_c")):
            num, _ = _parse_level(s.get(ck, ""))
            yv = r.get(yk)
            if num != "" and yv not in (None, ""):
                try:
                    dlt = float(yv) - float(num)
                    diffs.append(f"{ck[-1].upper()} {dlt:+.4f}")
                except (TypeError, ValueError):
                    pass
        if diffs:
            r["notes"] = (r["notes"] + "; " if r["notes"] else "") + "yf-chart 5m " + ", ".join(diffs)
        if "notes" in s and str(s["notes"]) not in ("nan", ""):
            r["notes"] = (r["notes"] + "; " if r["notes"] else "") + str(s["notes"])
        nfill += 1
    # ARM PP: raw pp_* cells are 'unattributed'. Use the measured unlabeled
    # yellow dotted ~183.66 / ORL ~174.79 / white dashed ~174.03, with a note
    # that 183.66 might be PP ORH or (less likely) an AWR high.
    arm = [r for r in rows if r["ticker"] == "ARM" and r["date"] == "2026-11-09"]
    if arm:
        a = arm[0]
        a["pp_orh"] = "183.66"
        a["pp_orl"] = "174.79"
        a["pp_gc"] = "174.03"
        a["notes"] = (a["notes"] + "; " if a["notes"] else "") + (
            "PP ORH 183.66 / ORL 174.79 / GC 174.03 from unlabeled chart lines "
            "(yellow dotted 183.64±0.03, original ORL ~174.79, white dashed 174.03±0.03). "
            "Labeled tooltip OR 177.31/174.76 is NDTL, not PP. 183.66 is also hypothesized as PP AWR high."
        )
    print(f"Filled chart reads on {nfill} Nov 9 rows from {RAW_CSV}")


COLS = [
    "ticker", "date",
    "pp_orh", "pp_orl", "pp_gc",
    "ndtl_orh", "ndtl_orl", "ndtl_gc",
    "prior_close", "prior_close_src", "gap_pct",
    "b930_1m_o", "b930_1m_h", "b930_1m_l", "b930_1m_c",
    "b930_5m_o", "b930_5m_h", "b930_5m_l", "b930_5m_c",
    "h1", "l1", "h2", "l2", "h3", "l3", "h4", "l4",
    "h5", "l5", "h10", "l10",
    "h15", "l15", "h30", "l30",
    "h45", "l45", "h60", "l60",
    "h15_incl", "l15_incl", "h30_incl", "l30_incl",
    "h45_incl", "l45_incl", "h60_incl", "l60_incl",
    "quiet3_orh", "quiet3_orl", "quiet3_orh_lock", "quiet3_orl_lock",
    "quiet4_orh", "quiet4_orl", "quiet4_orh_lock", "quiet4_orl_lock",
    "quiet4_orh_bar", "quiet4_orl_bar",
    "quiet5_orh", "quiet5_orl", "quiet5_orh_lock", "quiet5_orl_lock",
    "is_biggest_gap_up", "is_biggest_gap_down",
    "notes",
]

NUM_COLS = {
    "prior_close", "gap_pct",
    "b930_1m_o", "b930_1m_h", "b930_1m_l", "b930_1m_c",
    "b930_5m_o", "b930_5m_h", "b930_5m_l", "b930_5m_c",
    "h1", "l1", "h2", "l2", "h3", "l3", "h4", "l4",
    "h5", "l5", "h10", "l10",
    "h15", "l15", "h30", "l30",
    "h45", "l45", "h60", "l60",
    "h15_incl", "l15_incl", "h30_incl", "l30_incl",
    "h45_incl", "l45_incl", "h60_incl", "l60_incl",
    "quiet3_orh", "quiet3_orl", "quiet4_orh", "quiet4_orl", "quiet5_orh", "quiet5_orl",
}


def rows_to_frame(rows: list[dict]) -> pd.DataFrame:
    recs = []
    for r in rows:
        rec = {}
        for c in COLS:
            v = r.get(c, "")
            if c in NUM_COLS:
                rec[c] = "" if v is None or v == "" else fnum(v, 6)
            else:
                rec[c] = "" if v is None else v
        recs.append(rec)
    return pd.DataFrame(recs, columns=COLS)


def arm_comparison(rows: list[dict]) -> str:
    arm = [r for r in rows if r["ticker"] == "ARM" and r["date"] == "2026-11-09"]
    if not arm:
        return "ARM 2026-11-09: NO ROW (download failed or no RTH bars)\n"
    r = arm[0]
    pp_orh, pp_orl = 183.6, 174.79
    lines = []
    lines.append("=== ARM 2026-11-09 comparison vs Paper Prophet ORH~183.6 / ORL~174.79 / GC~174.00 ===")
    lines.append(f"  prior_close = {r['prior_close']}  (src: {r['prior_close_src']})")
    lines.append(f"  claimed prior close 174.62?  {'YES' if r['prior_close'] is not None and abs(r['prior_close']-174.62)<=0.02 else 'NO'}  (abs diff={'' if r['prior_close'] is None else round(abs(r['prior_close']-174.62), 4)})")
    lines.append(f"  9:30 1m OHLC  O={r['b930_1m_o']} H={r['b930_1m_h']} L={r['b930_1m_l']} C={r['b930_1m_c']}")
    lines.append(f"  9:30 5m OHLC  O={r['b930_5m_o']} H={r['b930_5m_h']} L={r['b930_5m_l']} C={r['b930_5m_c']}")
    lines.append(f"  gap_pct = {None if r['gap_pct'] is None else round(r['gap_pct'], 4)}%")
    lines.append("  first-N-minute high / low:")
    for n, h, l in (
        (1, r["h1"], r["l1"]), (3, r["h3"], r["l3"]), (4, r["h4"], r["l4"]),
        (5, r["h5"], r["l5"]), (10, r["h10"], r["l10"]), (15, r["h15"], r["l15"]),
        (30, r["h30"], r["l30"]),
    ):
        dh = None if h is None else h - pp_orh
        dl = None if l is None else l - pp_orl
        match_h = h is not None and abs(h - pp_orh) <= 0.15
        match_l = l is not None and abs(l - pp_orl) <= 0.15
        lines.append(f"    N={n:<2}  H={h}  (vs PP ORH {pp_orh}, d={None if dh is None else round(dh,4)}){'  MATCH' if match_h else ''}"
                     f"   L={l}  (vs PP ORL {pp_orl}, d={None if dl is None else round(dl,4)}){'  MATCH' if match_l else ''}")
    lines.append("  quiet-rule OR:")
    for n, oh, ol, th, tl in (
        (3, r["quiet3_orh"], r["quiet3_orl"], r["quiet3_orh_lock"], r["quiet3_orl_lock"]),
        (4, r["quiet4_orh"], r["quiet4_orl"], r["quiet4_orh_lock"], r["quiet4_orl_lock"]),
        (5, r["quiet5_orh"], r["quiet5_orl"], r["quiet5_orh_lock"], r["quiet5_orl_lock"]),
    ):
        dh = None if oh is None else oh - pp_orh
        dl = None if ol is None else ol - pp_orl
        mh = oh is not None and abs(oh - pp_orh) <= 0.15
        ml = ol is not None and abs(ol - pp_orl) <= 0.15
        lines.append(f"    quiet={n}  ORH={oh} lock={th} (d={None if dh is None else round(dh,4)}){'  MATCH' if mh else ''}"
                     f"   ORL={ol} lock={tl} (d={None if dl is None else round(dl,4)}){'  MATCH' if ml else ''}"
                     f"   both={'YES' if mh and ml else 'no'}")
    lines.append(f"  quiet4 extreme bars: ORH bar={r['quiet4_orh_bar']}  ORL bar={r['quiet4_orl_bar']}")
    # which N / rule matches
    matches = []
    for n, h, l in ((1, r["h1"], r["l1"]), (3, r["h3"], r["l3"]), (4, r["h4"], r["l4"]),
                    (5, r["h5"], r["l5"]), (10, r["h10"], r["l10"]), (15, r["h15"], r["l15"]),
                    (30, r["h30"], r["l30"])):
        if h is not None and l is not None and abs(h - pp_orh) <= 0.15 and abs(l - pp_orl) <= 0.15:
            matches.append(f"fixed first-{n}m window")
    for n, oh, ol in ((3, r["quiet3_orh"], r["quiet3_orl"]),
                      (4, r["quiet4_orh"], r["quiet4_orl"]),
                      (5, r["quiet5_orh"], r["quiet5_orl"])):
        if oh is not None and ol is not None and abs(oh - pp_orh) <= 0.15 and abs(ol - pp_orl) <= 0.15:
            matches.append(f"quiet-rule N={n}")
        elif oh is not None and abs(oh - pp_orh) <= 0.15:
            matches.append(f"quiet-rule N={n} ORH only")
        elif ol is not None and abs(ol - pp_orl) <= 0.15:
            matches.append(f"quiet-rule N={n} ORL only")
    lines.append("  MATCHING rules (tol ±0.15): " + (", ".join(matches) if matches else "NONE"))
    return "\n".join(lines) + "\n"


def main():
    os.makedirs(DATA, exist_ok=True)
    failures = []  # (ticker, reason)
    all_rows = []
    have = []
    need = []
    for t in TICKERS:
        if file_covers_nov9(t):
            have.append(t)
        else:
            need.append(t)
    print(f"Reuse existing 1m dumps covering Nov 9: {len(have)}  ({', '.join(have)})")
    print(f"Need to download: {len(need)}  ({', '.join(need)})")

    # download missing
    for i, t in enumerate(need, 1):
        print(f"[{i}/{len(need)}] fetching {t} ...", flush=True)
        df, err = fetch_ticker_1m(t)
        if err or df is None or df.empty:
            failures.append((t, err or "empty dataframe"))
            print(f"    FAIL {t}: {err}")
            continue
        days = sorted(set(df.index.strftime("%Y-%m-%d")))
        rth_days = []
        for d in days:
            day = df[df.index.strftime("%Y-%m-%d") == d]
            if not rth_bars(day, "09:30", "16:00").empty:
                rth_days.append(d)
        path = _save_1m(t, df)
        print(f"    saved {path}  rows={len(df)}  sessions={len(rth_days)}  {rth_days[0] if rth_days else '?'}..{rth_days[-1] if rth_days else '?'}")
        if "2026-11-09" not in rth_days:
            failures.append((t, f"downloaded but no RTH bars on 2026-11-09 (sessions: {rth_days})"))
        time.sleep(0.25)

    print("Fetching daily closes for prior-close fallback / ARM check...")
    ok_tickers = [t for t in TICKERS if load_1m(t) is not None and not load_1m(t).empty]
    daily_map = fetch_daily_closes(ok_tickers)
    print(f"  daily closes for {len(daily_map)} tickers")

    # build rows
    for t in TICKERS:
        bars = load_1m(t)
        if bars is None or bars.empty:
            if not any(f[0] == t for f in failures):
                failures.append((t, "no 1m file after fetch"))
            continue
        daily = daily_map.get(t)
        try:
            rows = build_rows(t, bars, daily)
        except Exception as e:
            failures.append((t, f"build_rows: {type(e).__name__}: {e}"))
            traceback.print_exc()
            continue
        if not rows:
            failures.append((t, "1m file present but no RTH session rows"))
            continue
        all_rows.extend(rows)
        nov9 = any(r["date"] == "2026-11-09" for r in rows)
        if not nov9 and not any(f[0] == t for f in failures):
            failures.append((t, "rows built but no 2026-11-09 session"))

    fill_from_raw(all_rows)
    frame = rows_to_frame(all_rows)
    frame.to_csv(OUT_CSV, index=False)
    print(f"\nWrote {OUT_CSV}  rows={len(frame)}  tickers={frame['ticker'].nunique() if len(frame) else 0}")

    report = arm_comparison(all_rows)
    print()
    print(report)
    rep_path = os.path.join(HERE, "arm_nov9_comparison.txt")
    with open(rep_path, "w") as f:
        f.write(report)

    if failures:
        with open(FAIL_LOG, "w") as f:
            for t, reason in failures:
                f.write(f"{t}\t{reason}\n")
        print("FAILURES:")
        for t, reason in failures:
            print(f"  {t}: {reason}")
    else:
        if os.path.exists(FAIL_LOG):
            os.remove(FAIL_LOG)
        print("No ticker failures.")

    # sanity: reuse SPY Nov 9 quiet4 should be 747.93 / 741.03
    spy = [r for r in all_rows if r["ticker"] == "SPY" and r["date"] == "2026-11-09"]
    if spy:
        r = spy[0]
        print(f"\nSanity SPY 2026-11-09 quiet4 ORH={r['quiet4_orh']} ORL={r['quiet4_orl']} "
              f"(expected ~747.93 / 741.03)")
        if r["quiet4_orh"] is not None and abs(r["quiet4_orh"] - 747.93) > 0.05:
            print("  WARNING: quiet4 ORH does not match known PP/fit value")
        if r["quiet4_orl"] is not None and abs(r["quiet4_orl"] - 741.03) > 0.05:
            print("  WARNING: quiet4 ORL does not match known PP/fit value")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
