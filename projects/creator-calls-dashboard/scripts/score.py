#!/usr/bin/env python3
"""Score mentions against cached prices: forward returns, hits, flips, reaction,
price-talk targets, chase flags, and SMA-50 regime.

Reads data/mentions.json and data/prices.json. Writes data/scores.json.
Rerun anytime; does not fetch the network.

Assumptions (also stored in the output):
- Only bullish/bearish mentions are "directional calls" for hit rates.
- Returns start at the next trading day's open after the video date, because
  upload time is unknown. Same-day moves are not counted as the call working.
- 1d = close of that entry day / entry open - 1.
  5d = close of the 5th session starting at entry / entry open - 1.
- A bullish call hits when the forward return is > 0; a bearish call hits
  when it is < 0. SPY-adjusted hits use (ticker return - SPY return) the same way.
- Mentions without enough future bars are marked pending, not misses.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import re
import sys
import tempfile
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
FLIP_CONFIG = os.path.join(ROOT, "scripts", "flip_config.json")
FLIP_DEFAULTS = {"forward_sessions": 5, "prior_sessions": 5, "ahead_min_move": 0.0, "prior_min_move": 0.0, "vs_spy": False}
THIN_N = 10  # fewer scored calls than this = too few to trust


def load_flip_config(path=FLIP_CONFIG):
    """Flip tag settings; keys starting with '_' are comments."""
    cfg = dict(FLIP_DEFAULTS)
    if os.path.exists(path):
        with open(path) as f:
            user = json.load(f)
        cfg.update({k: v for k, v in user.items() if not k.startswith("_")})
    cfg["forward_sessions"] = max(1, int(cfg["forward_sessions"]))
    cfg["prior_sessions"] = max(1, int(cfg["prior_sessions"]))
    cfg["ahead_min_move"] = float(cfg["ahead_min_move"])
    cfg["prior_min_move"] = float(cfg["prior_min_move"])
    cfg["vs_spy"] = bool(cfg["vs_spy"])
    return cfg

ASSUMPTIONS = [
    "Directional calls are bullish or bearish mentions; mixed and neutral are not scored for hit rate.",
    "Returns start at the next trading day's open after the video date (upload time is unknown); same-day moves are excluded.",
    "1d is the close of the entry session vs that open; 5d is the close of the 5th session starting at entry vs that open.",
    "A bullish call hits when the forward return is > 0; a bearish call hits when it is < 0.",
    "SPY-adjusted hits use the same rule on (ticker return minus SPY return) over the same dates.",
    "Calls without enough future bars are pending, not misses.",
    "The prior-day move used for 'chasing' is the last completed session on or before the video date.",
    "SMA-50 uses the 50 closes ending on the last session on or before the video date.",
    "SMA-20 uses the 20 closes ending on the same session as SMA-50 (last session on or before the video date).",
    "'To date' is the latest close in prices.json vs the entry open; vs SPY subtracts SPY's move over the exact same dates (missing if SPY lacks either date).",
    "Flip tags (ahead / after / no_follow_through / pending) follow scripts/flip_config.json; the settings used are stored in flip_config.",
    "Per-creator, per-ticker splits (by_channel_ticker) use the same hit rules; under 10 scored calls is flagged thin.",
    "Price-talk levels are parsed numbers near the then-current price; percents, years, multiples, and 'day/SMA' references are skipped.",
]


def load_json(path):
    with open(path) as f:
        return json.load(f)


def atomic_write(path, obj):
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


def iso(d: dt.date) -> str:
    return d.isoformat()


def parse_date(s):
    if not s or not isinstance(s, str):
        return None
    s = s.strip()[:10]
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


class Book:
    """Daily bars for one ticker, indexed by date."""

    def __init__(self, bars):
        self.bars = []
        for b in bars or []:
            if not b or not b.get("date") or b.get("close") is None:
                continue
            self.bars.append(b)
        self.bars.sort(key=lambda b: b["date"])
        self.by = {b["date"]: b for b in self.bars}
        self.dates = [b["date"] for b in self.bars]
        self._idx = {d: i for i, d in enumerate(self.dates)}

    def __len__(self):
        return len(self.bars)

    def on_or_before(self, day: dt.date):
        s = iso(day)
        i = None
        for j, d in enumerate(self.dates):
            if d <= s:
                i = j
            else:
                break
        return (i, self.bars[i]) if i is not None else (None, None)

    def first_on_or_after(self, day: dt.date):
        s = iso(day)
        for j, d in enumerate(self.dates):
            if d >= s:
                return j, self.bars[j]
        return None, None

    def first_after(self, day: dt.date):
        s = iso(day)
        for j, d in enumerate(self.dates):
            if d > s:
                return j, self.bars[j]
        return None, None

    def at_index(self, i):
        if i is None or i < 0 or i >= len(self.bars):
            return None
        return self.bars[i]

    def sma(self, end_i, n=50):
        if end_i is None or end_i < n - 1:
            return None
        chunk = self.bars[end_i - n + 1 : end_i + 1]
        closes = [b["close"] for b in chunk if b.get("close") is not None]
        if len(closes) < n:
            return None
        return sum(closes) / n

    def daily_abs_rets(self, end_i, n=20):
        # |close/prev_close - 1| for up to n sessions ending at end_i
        out = []
        if end_i is None:
            return out
        start = max(1, end_i - n + 1)
        for i in range(start, end_i + 1):
            a = self.bars[i - 1].get("close")
            b = self.bars[i].get("close")
            if a and b and a > 0:
                out.append(abs(b / a - 1))
        return out


def typ_move(abs_rets):
    if not abs_rets:
        return None
    xs = sorted(abs_rets)
    mid = xs[len(xs) // 2]
    return mid if mid > 0 else (sum(xs) / len(xs) if xs else None)


# ---------- price-talk parsing ----------

# Words that make a nearby number not a price level.
_SKIP_NEAR = re.compile(
    r"(?i)(%|percent|bps|multiple|forward earnings|p/?e|rsi|shares?|calls?|"
    r"puts?|contracts?|days?|weeks?|months?|years?|year-end|sma|ema|"
    r"moving.average|session|hour|min|capex|billion|million|trillion|"
    r"\b[bmt]il\b)"
)
_YEAR = re.compile(r"\b(20[2-3][0-9])\b")
_RANGE = re.compile(
    r"(?i)(?<![A-Z])(?:[$~≈]|around\s+|near\s+|to\s+|at\s+)?"
    r"(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(k)?\s*"
    r"(?:-|–|—|to|/)\s*"
    r"(?:[$~≈])?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(k|s)?"
)
_SINGLE = re.compile(
    r"(?i)(?<![A-Z])(?:[$~≈])?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)(\s*k)?\b"
)
_TEENS = re.compile(r"(?i)\b(\d{2,4})s\b")  # 240s, 190s


def _to_f(s, k=False):
    s = s.replace(",", "")
    try:
        v = float(s)
    except ValueError:
        return None
    if k:
        v *= 1000.0
    return v


def _context_ok(text, start, end):
    window = text[max(0, start - 24) : min(len(text), end + 24)]
    # percents / multiples / sizes
    if re.search(r"%|percent|\dx\b|billion|\b[0-9.]+\s*[BMTbtm]\b", window):
        # allow if the number itself isn't the one with % — check immediate suffix
        after = text[end : min(len(text), end + 8)]
        before = text[max(0, start - 8) : start]
        if re.match(r"\s*%", after) or re.search(r"\d\s*[BMT]$", before + "x"):
            return False
        if re.match(r"\s*%", after) or re.match(r"\s*[BMTbtm]\b", after):
            return False
        if re.search(r"(?i)\bx\b", after[:4]):
            return False
    after = text[end : min(len(text), end + 18)]
    before = text[max(0, start - 22) : start]
    blob = (before + " " + after).lower()
    if re.search(r"\b(sma|ema|day ma|day moving|rsi|shares?|p/?e|capex|year|years|days|weeks|months)\b", blob):
        # 'to 738' should still pass; '50-day' / '50 SMA' should not
        if re.search(r"(?i)(day|sma|ema|rsi|shares?|year|p/?e)", after[:12]) or re.search(
            r"(?i)(rsi|p/?e|capex|bought|holds?|assigned)\s*$", before
        ):
            return False
        if re.search(r"(?i)(\d{2,4}-day|\d{2,4}\s+sma)", text[max(0, start - 2) : end + 8]):
            return False
    if _YEAR.search(text[max(0, start) : end]):
        return False
    return True


def extract_targets(text, last_price):
    """Return unique numeric levels near last_price, with a loose 0.25x–4x band."""
    if not text or not last_price or last_price <= 0:
        return []
    found = []  # (value, lo, hi, raw)

    def accept(v, lo, hi, raw, span):
        if v is None or v <= 0:
            return
        if not _context_ok(text, span[0], span[1]):
            return
        # Scale: if price is huge (BTC ~80k) and v is like 87, try *1000 when it fits better
        candidates = [v]
        if last_price >= 5000 and v < 1000:
            candidates.append(v * 1000)
        if last_price < 1000 and v >= 10000 and raw.lower().endswith("k") is False:
            # already a full number
            pass
        best = None
        for c in candidates:
            if 0.25 * last_price <= c <= 4.0 * last_price:
                rel = abs(c / last_price - 1)
                if best is None or rel < best[0]:
                    best = (rel, c)
        if best is None:
            return
        v = best[1]
        scale = v / (lo if lo else v) if lo and lo != v else 1.0
        # If we scaled v, scale range ends too when they came from the same unit
        if lo and 0.25 * last_price <= lo <= 4 * last_price:
            lo_v = lo
        elif lo and last_price >= 5000 and 0.25 * last_price <= lo * 1000 <= 4 * last_price:
            lo_v = lo * 1000
        else:
            lo_v = v
        if hi and 0.25 * last_price <= hi <= 4 * last_price:
            hi_v = hi
        elif hi and last_price >= 5000 and 0.25 * last_price <= hi * 1000 <= 4 * last_price:
            hi_v = hi * 1000
        else:
            hi_v = v
        found.append({"value": round(v, 4), "lo": round(min(lo_v, hi_v), 4), "hi": round(max(lo_v, hi_v), 4), "raw": raw})

    for m in _RANGE.finditer(text):
        k1 = bool(m.group(2))
        k2 = bool(m.group(4) and m.group(4).lower() == "k")
        # "240s" handled separately; if group 4 is 's' this is "750-780s"? rare
        if m.group(4) and m.group(4).lower() == "s":
            continue
        a = _to_f(m.group(1), k1 or k2)
        b = _to_f(m.group(3), k1 or k2)
        if a and b:
            mid = (a + b) / 2
            accept(mid, a, b, m.group(0).strip(), m.span())

    for m in _TEENS.finditer(text):
        base = _to_f(m.group(1), False)
        if base:
            accept(base, base, base + 9, m.group(0), m.span())

    for m in _SINGLE.finditer(text):
        raw = m.group(0).strip()
        # skip if inside a range already captured
        if any(m.start() >= rstart and m.end() <= rend for rstart, rend in [(mm.start(), mm.end()) for mm in _RANGE.finditer(text)]):
            continue
        v = _to_f(m.group(1), bool(m.group(2)))
        accept(v, v, v, raw, m.span())

    # unique by rounded value
    uniq = []
    seen = set()
    for t in found:
        key = round(t["value"], 2)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(t)
    return uniq


def target_hit_info(book: Book, entry_i, last_price, target):
    """Did high/low tag the level after entry, and in how many trading days?"""
    lo, hi = target["lo"], target["hi"]
    # already at/through the zone on the last session on or before the video?
    side = "above" if lo >= last_price * 1.002 else "below" if hi <= last_price * 0.998 else "at"
    if side == "at":
        return {"hit": True, "days_to_hit": 0, "side": side, "already_at": True}
    if entry_i is None:
        return {"hit": False, "days_to_hit": None, "side": side, "already_at": False, "pending": True, "days_available": 0}
    days_available = 0
    for j in range(entry_i, len(book.bars)):
        b = book.bars[j]
        high, low = b.get("high"), b.get("low")
        if high is None or low is None:
            continue
        days = j - entry_i + 1
        days_available = days
        if side == "above" and high >= lo:
            return {"hit": True, "days_to_hit": days, "side": side, "already_at": False, "pending": False, "days_available": days}
        if side == "below" and low <= hi:
            return {"hit": True, "days_to_hit": days, "side": side, "already_at": False, "pending": False, "days_available": days}
    # A miss is resolved only after 10 trading days of follow-up; otherwise it is still pending.
    pending = days_available < 10
    return {"hit": False, "days_to_hit": None, "side": side, "already_at": False, "pending": pending, "days_available": days_available}


def earnings_flag(earn_dates, mention_date, book: Book):
    """pre if earnings in the next 5 sessions, post if in the previous 3 sessions. None if no dates."""
    if not earn_dates:
        return None
    # map earnings dates
    ed = []
    for s in earn_dates:
        d = parse_date(s)
        if d:
            ed.append(d)
    if not ed:
        return None
    # session window
    i, last = book.on_or_before(mention_date)
    # next 5 sessions after mention date (or first session on/after if weekend)
    future = []
    past = []
    for b in book.bars:
        bd = parse_date(b["date"])
        if not bd:
            continue
        if bd > mention_date:
            future.append(bd)
        elif bd < mention_date:
            past.append(bd)
    next5 = set(future[:5])
    prev3 = set(past[-3:])
    for d in ed:
        if d in next5 or (d >= mention_date and future and d <= (future[4] if len(future) >= 5 else future[-1])):
            # earnings on mention date: treat as pre if we don't trade same-day (conservative: 'pre' if d == mention_date)
            return "pre"
        if d == mention_date:
            return "pre"
        if d in prev3 or (past and past[-3] <= d < mention_date if len(past) >= 3 else (past[0] <= d < mention_date if past else False)):
            return "post"
    return "neither"


def weekday_name(d: dt.date) -> str:
    return d.strftime("%A")


def hit_from_ret(sentiment, ret):
    if ret is None or sentiment not in ("bullish", "bearish"):
        return None
    if sentiment == "bullish":
        return ret > 0
    return ret < 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mentions", default=os.path.join(DATA, "mentions.json"))
    ap.add_argument("--prices", default=os.path.join(DATA, "prices.json"))
    ap.add_argument("--out", default=os.path.join(DATA, "scores.json"))
    args = ap.parse_args(argv)

    for p in (args.mentions, args.prices):
        if not os.path.exists(p):
            print(f"missing {p}", file=sys.stderr)
            return 1

    raw = load_json(args.mentions)
    if not isinstance(raw, list):
        raw = raw.get("mentions") if isinstance(raw, dict) else []
        if not isinstance(raw, list):
            raw = []

    prices = load_json(args.prices)
    bars_map = prices.get("bars") or {}
    meta_map = prices.get("meta") or {}
    books = {t: Book(b) for t, b in bars_map.items()}
    spy = books.get("SPY")

    calls = []
    skipped_no_price = 0

    for i, row in enumerate(raw):
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").strip().upper() or "—"
        channel = str(row.get("channel") or "").strip() or "Unknown"
        sentiment = str(row.get("sentiment") or "").strip().lower() or "unknown"
        date = parse_date(row.get("date"))
        price_talk = str(row.get("price_talk") or "").strip()
        summary = str(row.get("summary") or "").strip()
        title = str(row.get("title") or "").strip()
        url = str(row.get("url") or "").strip() or str(row.get("video_url") or "").strip()
        video_id = str(row.get("video_id") or "").strip()
        tsec = row.get("t")
        try:
            tsec = int(tsec) if tsec is not None and tsec != "" else None
        except (TypeError, ValueError):
            tsec = None

        rec = {
            "i": i,
            "date": date.isoformat() if date else None,
            "weekday": weekday_name(date) if date else None,
            "channel": channel,
            "ticker": ticker,
            "sentiment": sentiment,
            "directional": sentiment in ("bullish", "bearish"),
            "price_talk": price_talk,
            "summary": summary,
            "title": title,
            "url": url,
            "video_id": video_id,
            "t": tsec,
            "has_price": ticker in books,
        }

        if date is None or ticker not in books:
            rec.update({
                "skip_reason": "no date" if date is None else "no price data",
            })
            if ticker not in books:
                skipped_no_price += 1
            calls.append(rec)
            continue

        book = books[ticker]
        prev_i, prev_bar = book.on_or_before(date)
        entry_i, entry_bar = book.first_after(date)

        last_px = prev_bar["close"] if prev_bar else None
        rec["price_asof"] = last_px
        rec["price_asof_date"] = prev_bar["date"] if prev_bar else None
        rec["entry_date"] = entry_bar["date"] if entry_bar else None
        rec["entry_open"] = entry_bar.get("open") if entry_bar else None

        # prior session move (completed session on or before video date)
        prior_ret = None
        if prev_i is not None and prev_i >= 1:
            a = book.bars[prev_i - 1].get("close")
            b = book.bars[prev_i].get("close")
            if a and b and a > 0:
                prior_ret = b / a - 1
        rec["prior_ret"] = prior_ret
        abs_rets = book.daily_abs_rets(prev_i, 20) if prev_i is not None else []
        typ = typ_move(abs_rets)
        rec["typ_move"] = typ
        chase = False
        chase_dir = None
        if prior_ret is not None and typ and typ > 0 and abs(prior_ret) > 2 * typ:
            chase = True
            chase_dir = "up" if prior_ret > 0 else "down"
        rec["chase"] = chase
        rec["chase_dir"] = chase_dir

        sma50 = book.sma(prev_i, 50) if prev_i is not None else None
        rec["sma50"] = sma50
        rec["above_sma50"] = (last_px > sma50) if (last_px is not None and sma50 is not None) else None
        sma20 = book.sma(prev_i, 20) if prev_i is not None else None
        rec["sma20"] = sma20
        rec["above_sma20"] = (last_px > sma20) if (last_px is not None and sma20 is not None) else None

        def window_ret(k):
            """k-session return from entry open to close of session entry_i + (k-1)."""
            if entry_i is None or entry_bar is None:
                return None, None, True  # ret, spy_ret, pending
            end_i = entry_i + (k - 1)
            end = book.at_index(end_i)
            o = entry_bar.get("open")
            if end is None or not o or o <= 0 or end.get("close") is None:
                return None, None, True
            ret = end["close"] / o - 1
            spy_ret = None
            if spy is not None:
                s_entry_i, s_entry = spy.first_on_or_after(parse_date(entry_bar["date"]))
                if s_entry is not None:
                    # use same calendar end date if possible, else index offset
                    s_end_i, s_end = spy.first_on_or_after(parse_date(end["date"]))
                    # prefer exact end date
                    if s_end is None or s_end["date"] != end["date"]:
                        # try offset from entry
                        s_end = spy.at_index(s_entry_i + (k - 1)) if s_entry_i is not None else None
                        if s_end and s_end["date"] != end["date"]:
                            # still ok if we have a bar; only use if dates match to stay honest
                            s_end = None
                    so = s_entry.get("open") if s_entry else None
                    if s_end and so and so > 0 and s_end.get("close") is not None:
                        spy_ret = s_end["close"] / so - 1
            return ret, spy_ret, False

        for k, name in ((1, "1d"), (5, "5d")):
            ret, spy_ret, pending = window_ret(k)
            rec[f"ret_{name}"] = ret
            rec[f"spy_ret_{name}"] = spy_ret
            rec[f"ex_{name}"] = (ret - spy_ret) if (ret is not None and spy_ret is not None) else None
            rec[f"pending_{name}"] = pending
            rec[f"hit_{name}"] = hit_from_ret(sentiment, ret)
            rec[f"hit_{name}_spy"] = hit_from_ret(sentiment, rec[f"ex_{name}"])

        # return since the call ("to date"): latest close vs entry open
        rec.update({"ret_td": None, "spy_ret_td": None, "ex_td": None, "td_date": None,
                    "td_sessions": None, "pending_td": True, "hit_td": None, "hit_td_spy": None})
        eo = entry_bar.get("open") if entry_bar else None
        if entry_i is not None and eo and eo > 0:
            lb = book.bars[-1]
            rec["ret_td"] = lb["close"] / eo - 1
            rec["td_date"] = lb["date"]
            rec["td_sessions"] = len(book.bars) - entry_i
            rec["pending_td"] = False
            if spy is not None:
                s0, s1 = spy.by.get(entry_bar["date"]), spy.by.get(lb["date"])
                if s0 and s1 and s0.get("open") and s1.get("close") is not None:
                    rec["spy_ret_td"] = s1["close"] / s0["open"] - 1
                    rec["ex_td"] = rec["ret_td"] - rec["spy_ret_td"]
            rec["hit_td"] = hit_from_ret(sentiment, rec["ret_td"])
            rec["hit_td_spy"] = hit_from_ret(sentiment, rec["ex_td"])

        # price-talk targets
        targets = []
        if price_talk and last_px:
            for tinfo in extract_targets(price_talk, last_px):
                info = target_hit_info(book, entry_i, last_px, tinfo)
                targets.append({**tinfo, **info})
        rec["targets"] = targets

        # earnings
        earn_dates = (meta_map.get(ticker) or {}).get("earnings_dates") or []
        rec["sector"] = (meta_map.get(ticker) or {}).get("sector")
        rec["industry"] = (meta_map.get(ticker) or {}).get("industry")
        rec["earnings_dates_available"] = bool(earn_dates)
        rec["earnings"] = earnings_flag(earn_dates, date, book) if earn_dates else None

        rec["skip_reason"] = None
        calls.append(rec)

    # First call / flips per (channel, ticker) among directional calls, chronological
    by_ct = defaultdict(list)
    for rec in calls:
        if rec.get("directional") and rec.get("date"):
            by_ct[(rec["channel"], rec["ticker"])].append(rec)
    flips = []
    for key, rows in by_ct.items():
        rows.sort(key=lambda r: (r["date"], r["i"]))
        first = True
        prev_sent = None
        for rec in rows:
            rec["is_first_call"] = first
            rec["is_flip"] = False
            rec["flip_from"] = None
            if prev_sent and rec["sentiment"] != prev_sent and rec["sentiment"] in ("bullish", "bearish") and prev_sent in ("bullish", "bearish"):
                rec["is_flip"] = True
                rec["flip_from"] = prev_sent
                flips.append({
                    "i": rec["i"],
                    "channel": rec["channel"],
                    "ticker": rec["ticker"],
                    "from": prev_sent,
                    "to": rec["sentiment"],
                    "date": rec["date"],
                    "prev_date": prev_row["date"],
                    "url": rec.get("url"),
                    "hit_1d": rec.get("hit_1d"),
                    "hit_5d": rec.get("hit_5d"),
                    "ret_1d": rec.get("ret_1d"),
                    "ret_5d": rec.get("ret_5d"),
                    "first_hit_5d": rows[0].get("hit_5d"),
                    "first_hit_1d": rows[0].get("hit_1d"),
                    "first_date": rows[0]["date"],
                })
            prev_sent = rec["sentiment"]
            prev_row = rec
            first = False
        for rec in rows:
            if "is_first_call" not in rec:
                rec["is_first_call"] = False

    # Flip tags (settings in scripts/flip_config.json)
    fcfg = load_flip_config()
    by_i = {c["i"]: c for c in calls}

    def spy_move(d0_open_date, d1_close_date, from_close_date=None):
        if spy is None:
            return None
        e = spy.by.get(d1_close_date)
        if from_close_date:
            s = spy.by.get(from_close_date)
            base = s.get("close") if s else None
        else:
            s = spy.by.get(d0_open_date)
            base = s.get("open") if s else None
        if not e or not base or e.get("close") is None:
            return None
        return e["close"] / base - 1

    def tag_flip(rec):
        book = books.get(rec["ticker"])
        d = parse_date(rec["date"])
        out = {"fwd_move": None, "prior_move": None, "fwd_sessions": fcfg["forward_sessions"],
               "prior_sessions": fcfg["prior_sessions"], "tag": None}
        if book is None or d is None:
            out["tag"] = "no_price"
            return out
        sign = 1 if rec["sentiment"] == "bullish" else -1
        prev_i, prev_bar = book.on_or_before(d)
        P = fcfg["prior_sessions"]
        if prev_i is not None and prev_i - P >= 0:
            a, b = book.bars[prev_i - P], book.bars[prev_i]
            if a.get("close") and b.get("close") is not None:
                m = b["close"] / a["close"] - 1
                if fcfg["vs_spy"]:
                    sm = spy_move(None, b["date"], from_close_date=a["date"])
                    m = (m - sm) if sm is not None else None
                out["prior_move"] = m
        N = fcfg["forward_sessions"]
        ei, eb = book.first_after(d)
        end = book.at_index(ei + N - 1) if ei is not None else None
        if eb is None or end is None or not eb.get("open") or end.get("close") is None:
            out["tag"] = "pending"
            return out
        m = end["close"] / eb["open"] - 1
        if fcfg["vs_spy"]:
            sm = spy_move(eb["date"], end["date"])
            m = (m - sm) if sm is not None else None
        out["fwd_move"] = m
        if m is None:
            out["tag"] = "pending"  # SPY bars missing for the vs-SPY version
        elif m * sign > fcfg["ahead_min_move"]:
            out["tag"] = "ahead"
        elif out["prior_move"] is not None and out["prior_move"] * sign > fcfg["prior_min_move"]:
            out["tag"] = "after"
        else:
            out["tag"] = "no_follow_through"
        return out

    flip_tag_counts = {"ahead": 0, "after": 0, "no_follow_through": 0, "pending": 0, "no_price": 0}
    for f in flips:
        info = tag_flip(by_i[f["i"]])
        f.update(info)
        by_i[f["i"]]["flip_tag"] = info["tag"]
        flip_tag_counts[info["tag"]] = flip_tag_counts.get(info["tag"], 0) + 1

    # Mark non-directional
    for rec in calls:
        rec.setdefault("is_first_call", False)
        rec.setdefault("is_flip", False)
        rec.setdefault("flip_from", None)
        rec.setdefault("flip_tag", None)
        for k in ("ret_td", "spy_ret_td", "ex_td", "td_date", "td_sessions", "hit_td", "hit_td_spy", "sma20", "above_sma20"):
            rec.setdefault(k, None)
        rec.setdefault("pending_td", rec.get("has_price", False))

    def rate(xs):
        xs = [x for x in xs if x is not None]
        if not xs:
            return None, 0
        return sum(1 for x in xs if x) / len(xs), len(xs)

    def channel_summary():
        out = []
        chans = sorted({c["channel"] for c in calls})
        for ch in chans:
            rows = [c for c in calls if c["channel"] == ch]
            d5 = [c.get("hit_5d") for c in rows if c.get("directional") and not c.get("pending_5d") and "hit_5d" in c]
            d1 = [c.get("hit_1d") for c in rows if c.get("directional") and not c.get("pending_1d") and "hit_1d" in c]
            s5 = [c.get("hit_5d_spy") for c in rows if c.get("directional") and c.get("ex_5d") is not None]
            r5, n5 = rate(d5)
            r1, n1 = rate(d1)
            rs, ns = rate(s5)
            mean5 = _mean([c["ret_5d"] for c in rows if c.get("ret_5d") is not None and c.get("directional")])
            out.append({
                "channel": ch,
                "mentions": len(rows),
                "n_5d": n5, "hit_rate_5d": r5,
                "n_1d": n1, "hit_rate_1d": r1,
                "n_5d_spy": ns, "hit_rate_5d_spy": rs,
                "mean_ret_5d": mean5,
                "flips": sum(1 for c in rows if c.get("is_flip")),
            })
        return out

    def _mean(xs):
        xs = [x for x in xs if x is not None]
        return (sum(xs) / len(xs)) if xs else None

    def split_stats(rows):
        d = [c for c in rows if c.get("directional")]
        r5, n5_ = rate([c.get("hit_5d") for c in d if not c.get("pending_5d")])
        r1, n1_ = rate([c.get("hit_1d") for c in d if not c.get("pending_1d")])
        rs, ns_ = rate([c.get("hit_5d_spy") for c in d if c.get("ex_5d") is not None])
        rt, nt = rate([c.get("hit_td") for c in d if not c.get("pending_td")])
        return {
            "directional": len(d),
            "bullish": sum(1 for c in d if c["sentiment"] == "bullish"),
            "bearish": sum(1 for c in d if c["sentiment"] == "bearish"),
            "n_5d": n5_, "hit_rate_5d": r5, "n_1d": n1_, "hit_rate_1d": r1,
            "n_5d_spy": ns_, "hit_rate_5d_spy": rs, "n_td": nt, "hit_rate_td": rt,
            "pending_5d": sum(1 for c in d if c.get("pending_5d")),
            "mean_ex_5d": _mean([c.get("ex_5d") for c in d]),
            "flips": sum(1 for c in d if c.get("is_flip")),
            "thin_5d": n5_ < THIN_N,
        }

    by_ct_rows = defaultdict(list)
    for c in calls:
        if c.get("directional"):
            by_ct_rows[(c["channel"], c["ticker"])].append(c)
    by_channel_ticker = []
    for (ch, tk), rows in sorted(by_ct_rows.items()):
        by_channel_ticker.append({"channel": ch, "ticker": tk, **split_stats(rows)})

    d5 = [c for c in calls if c.get("directional") and c.get("hit_5d") is not None]
    d1 = [c for c in calls if c.get("directional") and c.get("hit_1d") is not None]
    hr5, n5 = rate([c["hit_5d"] for c in d5])
    hr1, n1 = rate([c["hit_1d"] for c in d1])
    hrs, ns = rate([c["hit_5d_spy"] for c in d5 if c.get("hit_5d_spy") is not None])

    # reaction: 1d raw return by sentiment (all mentions with ret_1d)
    reaction = {
        "by_sentiment": {},
    }
    for s in ("bullish", "bearish", "mixed", "neutral", "unknown"):
        xs = [c["ret_1d"] for c in calls if c.get("sentiment") == s and c.get("ret_1d") is not None]
        reaction["by_sentiment"][s] = {
            "n": len(xs),
            "mean": _mean(xs),
            "median": (sorted(xs)[len(xs)//2] if xs else None),
            "positive": (sum(1 for x in xs if x > 0) / len(xs) if xs else None),
        }

    # targets summary
    all_t = []
    for c in calls:
        for t in c.get("targets") or []:
            all_t.append(t)
    fresh = [t for t in all_t if not t.get("already_at")]
    hit_t = [t for t in fresh if t.get("hit")]
    days = [t["days_to_hit"] for t in hit_t if t.get("days_to_hit")]
    targets_summary = {
        "mentions_with_targets": sum(1 for c in calls if c.get("targets")),
        "n_targets": len(all_t),
        "n_already_at": sum(1 for t in all_t if t.get("already_at")),
        "n_scored": len(fresh),
        "n_hit": len(hit_t),
        "hit_rate": (len(hit_t) / len(fresh) if fresh else None),
        "median_days_to_hit": (sorted(days)[len(days)//2] if days else None),
    }

    out = {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "assumptions": ASSUMPTIONS,
        "prices_generated_at": prices.get("generated_at"),
        "earnings_status": prices.get("earnings_status") or "not available",
        "summary": {
            "mentions": len(calls),
            "directional": sum(1 for c in calls if c.get("directional")),
            "n_5d": n5,
            "hit_rate_5d": hr5,
            "n_1d": n1,
            "hit_rate_1d": hr1,
            "n_5d_spy": ns,
            "hit_rate_5d_spy": hrs,
            "pending_5d": sum(1 for c in calls if c.get("directional") and c.get("pending_5d")),
            "pending_1d": sum(1 for c in calls if c.get("directional") and c.get("pending_1d")),
            "no_price": skipped_no_price,
            "flips": len(flips),
            "chase_calls": sum(1 for c in calls if c.get("chase") and c.get("directional")),
        },
        "by_channel": channel_summary(),
        "targets_summary": targets_summary,
        "reaction": reaction,
        "flips": flips,
        "flip_config": fcfg,
        "flip_tag_counts": flip_tag_counts,
        "thin_n": THIN_N,
        "by_channel_ticker": by_channel_ticker,
        "calls": calls,
        "failed_tickers": prices.get("failed") or [],
    }
    atomic_write(args.out, out)
    print(
        f"wrote {args.out}  mentions={len(calls)} directional_5d n={n5} hit={hr5 and round(hr5*100,1)}% "
        f"1d n={n1} hit={hr1 and round(hr1*100,1)}% flips={len(flips)} tags={flip_tag_counts} no_price={skipped_no_price}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
