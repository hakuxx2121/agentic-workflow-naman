#!/usr/bin/env python3
"""Reference implementation of NDTL premarket fibs (v2.1 section 11).

Premarket is 04:00-09:29 America/New_York inclusive (09:30 exclusive),
read from 1-minute pre/post bars. The first print of the premarket high
and the first print of the premarket low, left to right, set the fib
anchors. TradingView convention: level 1 sits at the first extreme and
level 0 at the second, so price = second + (first - second) * ratio.

If the high and low come from the same 1-minute candle, or the high
equals the low, that day's fib is skipped (no color tie-break).

Ratios: 0.5, 0.618, 0.65, and extensions 1.5, 1.618, 1.65.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

NY = "America/New_York"
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "pm-fib" / "pm_fib_reference.csv"
TICKERS = ["ARM", "AMZN", "NVDA", "AEHR"]
RATIOS = [0.5, 0.618, 0.65, 1.5, 1.618, 1.65]
FRESH_START = date(2026, 11, 10)
FRESH_END_EXCL = date(2026, 11, 13)  # include Nov 12


def _flatten_yf(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["Adj Close", "Close", "High", "Low", "Open", "Volume"])
    if isinstance(df.columns, pd.MultiIndex):
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
        df["Volume"] = 0.0
    idx = df.index
    if not isinstance(idx, pd.DatetimeIndex):
        idx = pd.to_datetime(idx, utc=True)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    df.index = idx.tz_convert(NY)
    df.index.name = "Datetime"
    df = df[["Adj Close", "Close", "High", "Low", "Open", "Volume"]].astype(float)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df.dropna(subset=["Open", "High", "Low", "Close"], how="all")


def load_1m(ticker: str) -> pd.DataFrame:
    path = DATA / f"{ticker}_1m.csv"
    if not path.exists():
        return pd.DataFrame(columns=["Adj Close", "Close", "High", "Low", "Open", "Volume"])
    raw = pd.read_csv(path)
    idx = pd.to_datetime(raw["Datetime"], utc=True).dt.tz_convert(NY)
    df = raw.copy()
    df.index = idx
    df.index.name = "Datetime"
    return df[["Adj Close", "Close", "High", "Low", "Open", "Volume"]].astype(float)


def save_1m(ticker: str, df: pd.DataFrame) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    out = df.reset_index()
    out.to_csv(DATA / f"{ticker}_1m.csv", index=False)


def fetch_fresh(ticker: str) -> pd.DataFrame:
    last_err = None
    for attempt in range(3):
        try:
            raw = yf.download(
                ticker,
                start=FRESH_START.isoformat(),
                end=FRESH_END_EXCL.isoformat(),
                interval="1m",
                prepost=True,
                auto_adjust=False,
                progress=False,
                threads=False,
            )
            return _flatten_yf(raw, ticker)
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    print(f"[warn] {ticker} fresh download failed: {last_err}", file=sys.stderr)
    return pd.DataFrame(columns=["Adj Close", "Close", "High", "Low", "Open", "Volume"])


def ensure_data(ticker: str) -> pd.DataFrame:
    existing = load_1m(ticker)
    last = existing.index.max() if not existing.empty else None
    need = last is None or last.tz_convert(NY).date() < date(2026, 11, 12)
    if need:
        fresh = fetch_fresh(ticker)
        if not fresh.empty:
            merged = pd.concat([existing, fresh]).sort_index()
            merged = merged[~merged.index.duplicated(keep="last")]
            save_1m(ticker, merged)
            print(f"{ticker}: merged {len(fresh)} fresh bars; last={merged.index.max()}")
            return merged
        print(f"{ticker}: no fresh bars; keeping existing last={last}")
    else:
        print(f"{ticker}: existing data already through {last}")
    return existing


def fib_price(first: float, second: float, ratio: float) -> float:
    return second + (first - second) * ratio


def pm_window(day: pd.DataFrame) -> pd.DataFrame:
    # 04:00 inclusive, 09:30 exclusive
    return day.between_time("04:00", "09:29")


def analyze_day(day: pd.DataFrame) -> dict:
    pm = pm_window(day)
    if pm.empty:
        return {
            "pm_high": None,
            "pm_high_time": None,
            "pm_low": None,
            "pm_low_time": None,
            "first_extreme": None,
            "direction": None,
            "skip": "no_premarket",
            **{f"fib_{r}": None for r in RATIOS},
        }
    pm_high = float(pm["High"].max())
    pm_low = float(pm["Low"].min())
    hi_time = pm.loc[pm["High"] == pm_high].index[0]
    lo_time = pm.loc[pm["Low"] == pm_low].index[0]
    skip = None
    first_extreme = None
    direction = None
    fibs = {f"fib_{r}": None for r in RATIOS}
    if hi_time == lo_time or pm_high == pm_low:
        skip = "same_candle" if hi_time == lo_time else "flat"
        if hi_time == lo_time and pm_high == pm_low:
            skip = "same_candle_and_flat"
    else:
        if hi_time < lo_time:
            first, second = pm_high, pm_low
            first_extreme = "high"
            direction = "high-to-low"
        else:
            first, second = pm_low, pm_high
            first_extreme = "low"
            direction = "low-to-high"
        for r in RATIOS:
            fibs[f"fib_{r}"] = fib_price(first, second, r)
    return {
        "pm_high": pm_high,
        "pm_high_time": hi_time.strftime("%Y-%m-%d %H:%M:%S%z"),
        "pm_low": pm_low,
        "pm_low_time": lo_time.strftime("%Y-%m-%d %H:%M:%S%z"),
        "first_extreme": first_extreme,
        "direction": direction,
        "skip": skip or "",
        **fibs,
    }


def main() -> int:
    rows = []
    for ticker in TICKERS:
        df = ensure_data(ticker)
        if df.empty:
            print(f"{ticker}: no data", file=sys.stderr)
            continue
        # Group by NY calendar date; only days that have a regular session
        # or any premarket prints. Weekend / empty dates are skipped.
        days = df.groupby(df.index.date)
        for d, day in days:
            # Skip dates with no premarket and no RTH (e.g. leftover AH only)
            pm = pm_window(day)
            rth = day.between_time("09:30", "15:59")
            if pm.empty and rth.empty:
                continue
            rec = analyze_day(day)
            rec["date"] = d.isoformat()
            rec["ticker"] = ticker
            rows.append(rec)

    cols = [
        "date", "ticker",
        "pm_high", "pm_high_time", "pm_low", "pm_low_time",
        "first_extreme", "direction", "skip",
        "fib_0.5", "fib_0.618", "fib_0.65",
        "fib_1.5", "fib_1.618", "fib_1.65",
    ]
    # rename fib keys
    out_rows = []
    for r in rows:
        item = dict(r)
        for ratio in RATIOS:
            item[f"fib_{ratio}"] = r[f"fib_{ratio}"]
            if f"fib_{ratio}" != f"fib_{ratio}":
                pass
        # map 0.5 key: stored as fib_0.5 from f"fib_{r}"
        out_rows.append(item)
    # The dict already uses fib_0.5 etc. because f"fib_{0.5}" == "fib_0.5"
    table = pd.DataFrame(out_rows)
    # Ensure column names match
    rename = {f"fib_{r}": f"fib_{r}" for r in RATIOS}
    table = table.rename(columns=rename)
    table = table[cols]
    table.to_csv(OUT, index=False, float_format="%.6f")
    print(f"wrote {OUT} ({len(table)} rows)")

    ties = table[table["skip"].isin(["same_candle", "flat", "same_candle_and_flat"])]
    print(f"\nTie / skip days: {len(ties)}")
    if not ties.empty:
        print(ties[["date", "ticker", "pm_high", "pm_high_time", "pm_low", "pm_low_time", "skip"]].to_string(index=False))

    print("\nARM / AMZN, two most recent days with premarket data:")
    for ticker in ("ARM", "AMZN"):
        sub = table[table["ticker"] == ticker].sort_values("date")
        sub = sub[sub["pm_high"].notna()]
        print(f"\n{ticker}")
        print(sub.tail(2).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
