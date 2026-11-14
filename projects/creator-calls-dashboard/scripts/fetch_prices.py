#!/usr/bin/env python3
"""Fetch daily OHLCV, sectors, and earnings dates for tickers in mentions.json.

Writes data/prices.json atomically. Safe to rerun. Uses the on-disk cache unless
--refresh is set (or a ticker is missing / its last bar is stale vs SPY).

Prices come from the Yahoo Finance v8 chart API. Sectors and earnings dates
come from yfinance when it is installed; they are left blank (and later marked
'not available') when a lookup fails — nothing is guessed.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
DEFAULT_MENTIONS = os.path.join(DATA, "mentions.json")
DEFAULT_OUT = os.path.join(DATA, "prices.json")

UA = {"User-Agent": "Mozilla/5.0 (compatible; ticker-dashboard/1.0)"}

# Mention tickers that Yahoo lists under a different symbol.
SYMBOL_MAP = {
    "BRK.B": "BRK-B",
    "BRK/B": "BRK-B",
    "BTC": "BTC-USD",
    "VIX": "^VIX",
}


def yahoo_symbol(ticker: str) -> str:
    t = (ticker or "").strip().upper()
    return SYMBOL_MAP.get(t, t)


def load_json(path: str):
    with open(path) as f:
        return json.load(f)


def atomic_write(path: str, obj) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def mention_tickers(mentions) -> list[str]:
    if not isinstance(mentions, list):
        mentions = mentions.get("mentions") if isinstance(mentions, dict) else []
    out = []
    seen = set()
    for row in mentions or []:
        if not isinstance(row, dict):
            continue
        t = str(row.get("ticker") or "").strip().upper()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    if "SPY" not in seen:
        out.append("SPY")
    return out


def parse_chart(payload: dict) -> list[dict]:
    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        err = (payload.get("chart") or {}).get("error")
        raise RuntimeError(f"yahoo chart error: {err}")
    r = result[0]
    ts = r.get("timestamp") or []
    quote = (r.get("indicators") or {}).get("quote") or [{}]
    q = quote[0]
    opens, highs, lows, closes, vols = (
        q.get("open") or [],
        q.get("high") or [],
        q.get("low") or [],
        q.get("close") or [],
        q.get("volume") or [],
    )
    bars = []
    for i, t in enumerate(ts):
        if i >= len(closes) or closes[i] is None:
            continue
        day = dt.datetime.fromtimestamp(int(t), dt.timezone.utc).date().isoformat()

        def num(arr, i=i):
            if i >= len(arr) or arr[i] is None:
                return None
            return float(arr[i])

        bars.append({
            "date": day,
            "open": num(opens),
            "high": num(highs),
            "low": num(lows),
            "close": float(closes[i]),
            "volume": num(vols),
        })
    by = {}
    for b in bars:
        by[b["date"]] = b
    return [by[d] for d in sorted(by)]


def fetch_chart(symbol: str, range_="1y", timeout=20, retries=3) -> list[dict]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range={range_}"
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.load(resp)
            bars = parse_chart(payload)
            if not bars:
                raise RuntimeError("no daily bars")
            return bars
        except Exception as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise last


def fetch_fundamentals(symbol: str) -> dict:
    """Sector / industry / earnings dates. Empty fields on failure — never guessed."""
    out = {"sector": None, "industry": None, "earnings_dates": [], "fundamentals_error": None}
    try:
        import yfinance as yf
    except ImportError:
        out["fundamentals_error"] = "yfinance not installed"
        return out
    try:
        t = yf.Ticker(symbol)
        try:
            info = t.get_info() if hasattr(t, "get_info") else (t.info or {})
        except Exception as e:
            info = {}
            out["fundamentals_error"] = f"info: {type(e).__name__}: {e}"
        if isinstance(info, dict):
            sec = info.get("sector") or info.get("sectorDisp")
            ind = info.get("industry") or info.get("industryDisp")
            out["sector"] = sec if isinstance(sec, str) and sec.strip() else None
            out["industry"] = ind if isinstance(ind, str) and ind.strip() else None
        try:
            ed = t.get_earnings_dates(limit=16)
        except Exception as e:
            ed = None
            prev = out["fundamentals_error"]
            msg = f"earnings: {type(e).__name__}: {e}"
            out["fundamentals_error"] = f"{prev}; {msg}" if prev else msg
        dates = []
        if ed is not None and getattr(ed, "empty", True) is False:
            for idx in ed.index:
                try:
                    if hasattr(idx, "to_pydatetime"):
                        d = idx.to_pydatetime()
                    else:
                        d = idx
                    if hasattr(d, "date"):
                        dates.append(d.date().isoformat())
                    else:
                        dates.append(str(d)[:10])
                except Exception:
                    continue
        out["earnings_dates"] = sorted(set(dates))
        if out["earnings_dates"] and out["sector"]:
            out["fundamentals_error"] = None
        return out
    except Exception as e:
        out["fundamentals_error"] = f"{type(e).__name__}: {e}"
        return out


def _stale_cutoff(today_iso: str) -> str:
    today = dt.date.fromisoformat(today_iso)
    if today.weekday() == 5:
        expected = today - dt.timedelta(days=1)
    elif today.weekday() == 6:
        expected = today - dt.timedelta(days=2)
    else:
        expected = today
    return expected.isoformat()


def cache_usable(cache: dict) -> bool:
    if not cache or not isinstance(cache.get("bars"), dict):
        return False
    spy = cache["bars"].get("SPY") or []
    if not spy:
        return False
    last = spy[-1]["date"]
    today = dt.date.today().isoformat()
    if last < _stale_cutoff(today):
        return False
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mentions", default=DEFAULT_MENTIONS)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--refresh", action="store_true", help="ignore cache and refetch everything")
    ap.add_argument("--prices-only", action="store_true", help="skip sector/earnings lookups")
    ap.add_argument("--range", default="1y")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args(argv)

    if not os.path.exists(args.mentions):
        print(f"mentions not found: {args.mentions}", file=sys.stderr)
        return 1

    tickers = mention_tickers(load_json(args.mentions))
    cache = {}
    if os.path.exists(args.out) and not args.refresh:
        try:
            cache = load_json(args.out)
        except Exception:
            cache = {}

    reuse_prices = (not args.refresh) and cache_usable(cache)
    bars_out = dict(cache.get("bars") or {}) if reuse_prices else {}
    meta_out = dict(cache.get("meta") or {}) if (reuse_prices and not args.refresh) else {}
    failed = []
    fetched = 0

    def need_price(t: str) -> bool:
        b = bars_out.get(t)
        if not b:
            return True
        if not reuse_prices:
            return True
        spy = (bars_out.get("SPY") or cache.get("bars", {}).get("SPY") or [])
        if spy and b[-1]["date"] < spy[-1]["date"] and t != "SPY":
            return True
        return False

    to_fetch = [t for t in tickers if need_price(t)]
    reused = len(tickers) - len(to_fetch)

    def one_price(t: str):
        ys = yahoo_symbol(t)
        try:
            bars = fetch_chart(ys, range_=args.range)
            return t, bars, None
        except Exception as e:
            return t, None, f"{type(e).__name__}: {e}"

    if to_fetch:
        print(f"fetching daily bars for {len(to_fetch)} tickers ({reused} cached)...", flush=True)
        with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
            for t, bars, err in ex.map(one_price, to_fetch):
                if bars:
                    bars_out[t] = bars
                    fetched += 1
                    meta_out.setdefault(t, {})
                    meta_out[t]["yahoo"] = yahoo_symbol(t)
                    print(f"  {t}: {len(bars)} bars {bars[0]['date']} -> {bars[-1]['date']}", flush=True)
                else:
                    failed.append({"ticker": t, "yahoo": yahoo_symbol(t), "error": err})
                    print(f"  {t}: FAIL {err}", flush=True)
    else:
        print(f"reusing cached daily bars for {len(tickers)} tickers", flush=True)
        for t in tickers:
            meta_out.setdefault(t, {})
            meta_out[t]["yahoo"] = yahoo_symbol(t)

    fund_failed = 0
    fund_ok = 0
    if not args.prices_only:
        need_fund = []
        for t in tickers:
            if t not in bars_out:
                continue
            m = meta_out.get(t) or {}
            if not args.refresh and (m.get("sector") or m.get("earnings_dates") or m.get("fundamentals_checked")):
                continue
            need_fund.append(t)
        if need_fund:
            print(f"fetching sector/earnings for {len(need_fund)} tickers...", flush=True)

            def one_fund(t: str):
                time.sleep(0.05)
                return t, fetch_fundamentals(yahoo_symbol(t))

            with cf.ThreadPoolExecutor(max_workers=min(4, args.workers)) as ex:
                for t, fund in ex.map(one_fund, need_fund):
                    meta_out.setdefault(t, {})
                    meta_out[t]["yahoo"] = yahoo_symbol(t)
                    meta_out[t]["sector"] = fund.get("sector")
                    meta_out[t]["industry"] = fund.get("industry")
                    meta_out[t]["earnings_dates"] = fund.get("earnings_dates") or []
                    meta_out[t]["fundamentals_checked"] = True
                    if fund.get("fundamentals_error") and not (fund.get("sector") or fund.get("earnings_dates")):
                        meta_out[t]["fundamentals_error"] = fund["fundamentals_error"]
                        fund_failed += 1
                        print(f"  {t}: fundamentals incomplete ({fund['fundamentals_error']})", flush=True)
                    else:
                        fund_ok += 1
                        if fund.get("fundamentals_error"):
                            meta_out[t]["fundamentals_error"] = fund["fundamentals_error"]
                        print(
                            f"  {t}: sector={fund.get('sector') or '-'} earnings={len(fund.get('earnings_dates') or [])}",
                            flush=True,
                        )
        else:
            print("reusing cached sector/earnings", flush=True)
    else:
        print("skipping fundamentals (--prices-only)", flush=True)

    has_earnings = sum(1 for t, m in meta_out.items() if m.get("earnings_dates"))
    has_sector = sum(1 for t, m in meta_out.items() if m.get("sector"))
    earnings_status = "available" if has_earnings else "not available"
    if has_earnings and has_earnings < len(bars_out):
        earnings_status = "partial"

    out = {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": "yahoo v8 chart (prices); yfinance (sector, earnings_dates)",
        "range": args.range,
        "symbol_map": SYMBOL_MAP,
        "failed": failed,
        "earnings_status": earnings_status,
        "counts": {
            "tickers_requested": len(tickers),
            "bars_ok": len(bars_out),
            "bars_failed": len(failed),
            "bars_fetched_this_run": fetched,
            "bars_reused": reused,
            "with_sector": has_sector,
            "with_earnings": has_earnings,
        },
        "bars": bars_out,
        "meta": meta_out,
    }
    atomic_write(args.out, out)
    print(
        f"wrote {args.out}  bars_ok={len(bars_out)} failed={len(failed)} "
        f"sector={has_sector} earnings={has_earnings} ({earnings_status})",
        flush=True,
    )
    return 0 if bars_out else 6


if __name__ == "__main__":
    sys.exit(main())
