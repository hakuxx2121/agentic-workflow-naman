#!/usr/bin/env python3
"""Build the Insights layer from cached prices + scores.

Reads data/scores.json and data/prices.json, writes data/insights.json.
No network. Safe to rerun.

Each finding is one chart + one plain sentence, ranked by evidence strength
(a binomial test vs 50% and/or a permutation test / bootstrap CI). n is always
shown. n<10 is flagged "too few calls to trust". Non-significant results say
"could be chance". Sentences never claim cause and effect.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import random
import sys
import tempfile
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

N_MIN = 10
ALPHA = 0.05
PERM_ITERS = 8000
BOOT_ITERS = 8000
SEED = 20261110


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


def comb(n, k):
    if k < 0 or k > n:
        return 0
    return math.comb(n, k)


def binom_two_sided(k, n, p=0.5):
    """Exact two-sided binomial p-value."""
    if n <= 0:
        return 1.0
    k = int(k)
    n = int(n)
    # probability of exactly i
    # use log where needed? n is small (<500)
    def pdf(i):
        return comb(n, i) * (p ** i) * ((1 - p) ** (n - i))
    p_obs = pdf(k)
    s = 0.0
    for i in range(n + 1):
        pi = pdf(i)
        if pi <= p_obs + 1e-15:
            s += pi
    return min(1.0, max(0.0, s))


def permutation_diff_p(a, b, iters=PERM_ITERS, seed=SEED):
    """Two-sided permutation p-value for mean(a)-mean(b). Returns (p, observed_diff)."""
    a = list(a)
    b = list(b)
    if not a or not b:
        return 1.0, None
    obs = (sum(a) / len(a)) - (sum(b) / len(b))
    pool = a + b
    na = len(a)
    rng = random.Random(seed)
    extreme = 0
    for _ in range(iters):
        rng.shuffle(pool)
        diff = (sum(pool[:na]) / na) - (sum(pool[na:]) / (len(pool) - na))
        if abs(diff) >= abs(obs) - 1e-15:
            extreme += 1
    p = (extreme + 1) / (iters + 1)
    return p, obs


def bootstrap_mean_ci(xs, iters=BOOT_ITERS, alpha=ALPHA, seed=SEED):
    xs = list(xs)
    if not xs:
        return None, None, None
    rng = random.Random(seed)
    n = len(xs)
    means = []
    for _ in range(iters):
        s = 0.0
        for _i in range(n):
            s += xs[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    lo = means[int((alpha / 2) * iters)]
    hi = means[min(iters - 1, int((1 - alpha / 2) * iters))]
    return sum(xs) / n, lo, hi


def pct(x, digits=0):
    if x is None:
        return "—"
    return f"{x * 100:.{digits}f}%"


def nfmt(n):
    return f"n={n}"


def parse_date(s):
    if not s:
        return None
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def scored(calls, horizon="5d"):
    hit_key = f"hit_{horizon}"
    pend = f"pending_{horizon}"
    out = []
    for c in calls:
        if not c.get("directional"):
            continue
        if c.get(pend):
            continue
        if c.get(hit_key) is None:
            continue
        out.append(c)
    return out


def pick_horizon(calls, min_n=N_MIN):
    s5 = scored(calls, "5d")
    if len(s5) >= min_n:
        return "5d", s5
    s1 = scored(calls, "1d")
    return "1d", s1


def hits(rows, horizon):
    k = f"hit_{horizon}"
    return [1 if r.get(k) else 0 for r in rows]


def rate(rows, horizon):
    h = hits(rows, horizon)
    if not h:
        return None, 0
    return sum(h) / len(h), len(h)


def finding(
    *,
    id,
    title,
    test_id,
    n,
    sentence,
    chart,
    p_value=None,
    test_name="",
    horizon=None,
    stats=None,
    extra_n=None,
):
    too_few = (n or 0) < N_MIN
    sig = (not too_few) and (p_value is not None) and (p_value < ALPHA)
    if too_few:
        flag = "too few calls to trust"
        strength = 0.0
    elif p_value is None:
        flag = None
        strength = 0.0
    elif sig:
        flag = None
        strength = -math.log10(max(p_value, 1e-12))
    else:
        flag = "could be chance"
        strength = -math.log10(max(p_value, 1e-12)) * 0.25  # still rank weaker results
    # bump a bit for larger n so ties break toward more data
    if not too_few and p_value is not None:
        strength += 0.01 * math.log10(max(n, 1))
    return {
        "id": id,
        "title": title,
        "test_id": test_id,
        "n": n,
        "extra_n": extra_n,
        "too_few": too_few,
        "significant": bool(sig),
        "p_value": None if p_value is None else round(float(p_value), 4),
        "test_name": test_name,
        "sentence": sentence,
        "flag": flag,
        "horizon": horizon,
        "strength": round(strength, 4),
        "chart": chart,
        "stats": stats or {},
    }


def bar_chart(labels, values, label="Hit rate", n_labels=None, colors=None, y_format="percent"):
    return {
        "type": "bar",
        "labels": labels,
        "datasets": [{
            "label": label,
            "values": [None if v is None else round(float(v), 4) for v in values],
            "colors": colors,
        }],
        "y_format": y_format,
        "n_labels": n_labels,
    }


# ---------- tests ----------

def test_consensus(calls):
    horizon, base = pick_horizon(calls)
    # index directional mentions by ticker
    by_t = defaultdict(list)
    for c in calls:
        if not c.get("date") or not c.get("ticker"):
            continue
        if c.get("sentiment") not in ("bullish", "bearish"):
            continue
        by_t[c["ticker"]].append(c)
    for rows in by_t.values():
        rows.sort(key=lambda r: (r["date"], r["i"]))

    cons, contra, other = [], [], []
    for c in base:
        d = parse_date(c["date"])
        if not d:
            other.append(c)
            continue
        window_start = d - dt.timedelta(days=6)
        peers = []
        latest = {}
        for r in by_t.get(c["ticker"], []):
            rd = parse_date(r["date"])
            if rd is None or rd < window_start or rd > d:
                continue
            latest[r["channel"]] = r["sentiment"]
        if len(latest) < 3:
            other.append(c)
            continue
        bulls = sum(1 for s in latest.values() if s == "bullish")
        bears = sum(1 for s in latest.values() if s == "bearish")
        ncr = len(latest)
        majority = None
        if bulls >= math.ceil(ncr * 2 / 3):
            majority = "bullish"
        elif bears >= math.ceil(ncr * 2 / 3):
            majority = "bearish"
        if not majority:
            other.append(c)
            continue
        if c["sentiment"] == majority:
            cons.append(c)
        else:
            contra.append(c)

    rc, nc = rate(cons, horizon)
    rt, nt = rate(contra, horizon)
    ro, no = rate(base, horizon)
    n = nc + nt
    p, diff = (1.0, None)
    if nc and nt:
        p, diff = permutation_diff_p(hits(cons, horizon), hits(contra, horizon))
    elif nc >= 1:
        p = binom_two_sided(sum(hits(cons, horizon)), nc, 0.5)
    sentence_bits = []
    if nc:
        sentence_bits.append(f"when at least three creators agreed on a ticker over 7 days, those consensus {horizon} calls hit {pct(rc)} ({nfmt(nc)})")
    else:
        sentence_bits.append("there were not enough 7-day consensus clusters to score")
    if nt:
        sentence_bits.append(f"contrarian calls in those windows hit {pct(rt)} ({nfmt(nt)})")
    if n >= N_MIN and nt and nc:
        if p < ALPHA:
            sentence_bits.append(f"the gap is unlikely under a shuffle of the same outcomes (p={p:.2f}), but this is not evidence that agreement causes the result")
        else:
            sentence_bits.append(f"the gap could be chance (p={p:.2f})")
    elif n < N_MIN:
        sentence_bits.append("too few calls to trust")
    sentence = "Over this short sample, " + "; ".join(sentence_bits) + f". All directional {horizon} calls hit {pct(ro)} ({nfmt(no)})."
    chart = bar_chart(
        ["Consensus", "Contrarian", "All directional"],
        [rc, rt, ro],
        label=f"{horizon} hit rate",
        n_labels=[nc, nt, no],
        colors=["#3ecf8e", "#f06470", "#7f8b9c"],
    )
    return finding(
        id="consensus",
        title="Consensus vs contrarian",
        test_id=1,
        n=n,
        sentence=sentence,
        chart=chart,
        p_value=p,
        test_name=f"permutation test of {horizon} hit-rate difference (consensus vs contrarian); 7-day window, ≥3 creators, ≥2/3 agreement",
        horizon=horizon,
        stats={"consensus": {"n": nc, "hit_rate": rc}, "contrarian": {"n": nt, "hit_rate": rt}, "all": {"n": no, "hit_rate": ro}, "diff": diff},
        extra_n={"consensus": nc, "contrarian": nt},
    )


def test_herding(calls):
    # episodes per ticker: gap > 7 days
    by_t = defaultdict(list)
    for c in calls:
        if not c.get("date") or not c.get("ticker"):
            continue
        by_t[c["ticker"]].append(c)
    leads = Counter()
    follows = Counter()
    first_rows = []
    follow_rows = []
    pair_lag = Counter()  # (leader, follower) counts

    for ticker, rows in by_t.items():
        rows = sorted(rows, key=lambda r: (r["date"], r["i"]))
        episodes = []
        cur = []
        prev_d = None
        for r in rows:
            d = parse_date(r["date"])
            if prev_d is not None and d is not None and (d - prev_d).days > 7:
                if cur:
                    episodes.append(cur)
                cur = []
            cur.append(r)
            prev_d = d or prev_d
        if cur:
            episodes.append(cur)
        for ep in episodes:
            # first mention in episode is the lead
            first = ep[0]
            first_d = parse_date(first["date"])
            leads[first["channel"]] += 1
            first_rows.append(first)
            seen_followers = set()
            # other creators whose first mention in the episode is 1-5 days later
            first_by_ch = {}
            for r in ep:
                first_by_ch.setdefault(r["channel"], r)
            for ch, r in first_by_ch.items():
                if ch == first["channel"]:
                    continue
                rd = parse_date(r["date"])
                if first_d and rd and 1 <= (rd - first_d).days <= 5:
                    follows[ch] += 1
                    follow_rows.append(r)
                    pair_lag[(first["channel"], ch)] += 1
                    seen_followers.add(ch)

    horizon, _ = pick_horizon(calls)
    # hit rates: lead first-mentions vs follower mentions that are directional and scored
    lead_s = [c for c in scored(first_rows, horizon)]
    # first_rows may include non-directional; scored() filters
    fol_s = scored(follow_rows, horizon)
    rl, nl = rate(lead_s, horizon)
    rf, nf = rate(fol_s, horizon)
    n = nl + nf
    p, diff = (1.0, None)
    if nl and nf:
        p, diff = permutation_diff_p(hits(lead_s, horizon), hits(fol_s, horizon))

    # chart: lead counts vs follow counts per creator (top by leads+follows)
    creators = sorted(set(leads) | set(follows), key=lambda c: -(leads[c] + follows[c]))
    labels = creators
    chart = {
        "type": "bar",
        "labels": labels,
        "datasets": [
            {"label": "First in a cluster", "values": [leads[c] for c in labels], "colors": ["#7aa2ff"] * len(labels)},
            {"label": "Followed within 1–5 days", "values": [follows[c] for c in labels], "colors": ["#e0b34c"] * len(labels)},
        ],
        "y_format": "count",
        "n_labels": None,
    }
    top_leader = leads.most_common(1)[0] if leads else None
    top_pair = pair_lag.most_common(1)[0] if pair_lag else None
    parts = []
    if top_leader:
        parts.append(f"{top_leader[0]} was first in a ticker cluster most often ({top_leader[1]} times)")
    if top_pair:
        (a, b), cnt = top_pair
        parts.append(f"the most common lead-lag pair was {a} then {b} within 1–5 days ({cnt} times)")
    if nl or nf:
        parts.append(
            f"first mentions in a cluster hit {pct(rl)} on the {horizon} score ({nfmt(nl)}), "
            f"and later follows hit {pct(rf)} ({nfmt(nf)})"
        )
    if n >= N_MIN and nl and nf:
        if p < ALPHA:
            parts.append(f"that hit-rate gap is unlikely under a shuffle (p={p:.2f}), not a claim that being first causes better calls")
        else:
            parts.append(f"that hit-rate gap could be chance (p={p:.2f})")
    elif n < N_MIN:
        parts.append("too few calls to trust for a hit-rate comparison")
    sentence = ("Lead-lag counts use every mention, not just directional ones. " + "; ".join(parts) + ".") if parts else "There were not enough clusters to describe lead-lag patterns."
    return finding(
        id="herding",
        title="Herding (who calls first)",
        test_id=2,
        n=max(n, sum(leads.values()) + sum(follows.values())),
        sentence=sentence,
        chart=chart,
        p_value=p if (nl and nf) else None,
        test_name=f"lead-lag counts in 7-day-gap clusters; permutation test of {horizon} hit rate, first mention vs follow within 1–5 days",
        horizon=horizon,
        stats={
            "leads": dict(leads),
            "follows": dict(follows),
            "top_pair": {"leader": top_pair[0][0], "follower": top_pair[0][1], "n": top_pair[1]} if top_pair else None,
            "first_hit": {"n": nl, "hit_rate": rl},
            "follow_hit": {"n": nf, "hit_rate": rf},
            "diff": diff,
        },
    )


def test_spikes(calls, prices):
    # unique ticker-days, spike if >=3 distinct creators in [d-1, d]
    by_td = defaultdict(list)
    for c in calls:
        if not c.get("date") or not c.get("ticker"):
            continue
        by_td[(c["ticker"], c["date"])].append(c)
    # creators by ticker, date
    creators_on = defaultdict(set)
    for (t, d), rows in by_td.items():
        creators_on[(t, d)] |= {r["channel"] for r in rows}

    def window_creators(t, d):
        day = parse_date(d)
        s = set()
        for delta in (0, 1):
            prev = (day - dt.timedelta(days=delta)).isoformat()
            s |= creators_on.get((t, prev), set())
        return s

    # one return per ticker-day: use first call's ret on that day if any scored, else any mention's ret
    def day_ret(rows, horizon):
        key = f"ret_{horizon}"
        for r in rows:
            if r.get(key) is not None and not r.get(f"pending_{horizon}"):
                return r[key]
        return None

    horizon = "5d"
    spike_rets, normal_rets = [], []
    spike_days = normal_days = 0
    for (t, d), rows in by_td.items():
        ret = day_ret(rows, horizon)
        if ret is None:
            # try 1d later if needed
            continue
        ncr = len(window_creators(t, d))
        if ncr >= 3:
            spike_rets.append(ret)
            spike_days += 1
        else:
            normal_rets.append(ret)
            normal_days += 1

    used_horizon = "5d"
    if len(spike_rets) + len(normal_rets) < N_MIN:
        # rebuild with 1d
        spike_rets, normal_rets = [], []
        spike_days = normal_days = 0
        used_horizon = "1d"
        for (t, d), rows in by_td.items():
            ret = day_ret(rows, "1d")
            if ret is None:
                continue
            ncr = len(window_creators(t, d))
            if ncr >= 3:
                spike_rets.append(ret)
                spike_days += 1
            else:
                normal_rets.append(ret)
                normal_days += 1
        horizon = "1d"
    else:
        horizon = used_horizon

    n = len(spike_rets) + len(normal_rets)
    p, diff = (1.0, None)
    if spike_rets and normal_rets:
        p, diff = permutation_diff_p(spike_rets, normal_rets)
    ms, lo_s, hi_s = bootstrap_mean_ci(spike_rets) if spike_rets else (None, None, None)
    mn, lo_n, hi_n = bootstrap_mean_ci(normal_rets) if normal_rets else (None, None, None)
    frac_neg = (sum(1 for x in spike_rets if x < 0) / len(spike_rets)) if spike_rets else None
    frac_pos = (sum(1 for x in spike_rets if x > 0) / len(spike_rets)) if spike_rets else None

    def meanfmt(x):
        if x is None:
            return "—"
        sign = "+" if x >= 0 else ""
        return f"{sign}{x*100:.1f}%"

    parts = []
    if spike_rets:
        parts.append(
            f"ticker-days with at least three creators in a two-day window had a mean next-{horizon} return of {meanfmt(ms)} ({nfmt(len(spike_rets))})"
        )
        parts.append(f"{pct(frac_pos, 0)} of those spike days were followed by a positive {horizon} move, {pct(frac_neg, 0)} by a negative one")
    else:
        parts.append("there were almost no days with three or more creators on the same ticker")
    if normal_rets:
        parts.append(f"ordinary mention days averaged {meanfmt(mn)} ({nfmt(len(normal_rets))})")
    if spike_rets and normal_rets and n >= N_MIN:
        if p < ALPHA:
            parts.append(f"the difference is unlikely under a shuffle (p={p:.2f}), which is not a forecast rule")
        else:
            parts.append(f"the difference could be chance (p={p:.2f})")
    elif n < N_MIN:
        parts.append("too few calls to trust")
    sentence = "A spike is three or more distinct creators mentioning the same ticker in two calendar days. " + "; ".join(parts) + "."
    chart = bar_chart(
        ["Spike days", "Other mention days"],
        [ms, mn],
        label=f"Mean {horizon} return",
        n_labels=[len(spike_rets), len(normal_rets)],
        colors=["#e0b34c", "#7f8b9c"],
        y_format="percent",
    )
    return finding(
        id="spikes",
        title="Mention spikes and later returns",
        test_id=3,
        n=n,
        sentence=sentence,
        chart=chart,
        p_value=p if (spike_rets and normal_rets) else None,
        test_name=f"permutation test of mean {horizon} return, spike ticker-days (≥3 creators in 2 days) vs other mention days; bootstrap CI on the means",
        horizon=horizon,
        stats={
            "spike": {"n": len(spike_rets), "mean": ms, "ci": [lo_s, hi_s], "frac_pos": frac_pos, "frac_neg": frac_neg},
            "normal": {"n": len(normal_rets), "mean": mn, "ci": [lo_n, hi_n]},
            "diff": diff,
        },
        extra_n={"spike_days": len(spike_rets), "normal_days": len(normal_rets)},
    )


def test_price_talk(scores):
    calls = scores.get("calls") or []
    MIN_DIST = 0.03  # ignore levels inside 3% of spot — daily ranges tag those routinely
    ts_all = []
    meaningful = []
    days = []
    for c in calls:
        px = c.get("price_asof")
        for t in c.get("targets") or []:
            if t.get("already_at"):
                continue
            ts_all.append(t)
            if not px or px <= 0:
                continue
            dist = abs((t.get("value") or 0) / px - 1)
            if dist < MIN_DIST:
                continue
            if t.get("hit") or not t.get("pending"):
                meaningful.append(t)
                if t.get("hit") and t.get("days_to_hit"):
                    days.append(t["days_to_hit"])
    n_pending_far = 0
    for c in calls:
        px = c.get("price_asof")
        for t in c.get("targets") or []:
            if t.get("already_at") or not px or px <= 0:
                continue
            if abs((t.get("value") or 0) / px - 1) < MIN_DIST:
                continue
            if not t.get("hit") and t.get("pending"):
                n_pending_far += 1
    n = len(meaningful)
    n_hit = sum(1 for t in meaningful if t.get("hit"))
    hr = (n_hit / n) if n else None
    # 50% is a poor null for 10-day high/low tags in a volatile sample; report it but do not treat it as evidence.
    p_raw = binom_two_sided(n_hit, n, 0.5) if n else None
    med = (sorted(days)[len(days) // 2] if days else None)
    buckets = ["1d", "2d", "3d", "4d", "5d", "6–10d", "11d+", "not yet / pending"]
    counts = [0] * 8
    # chart uses all far-enough levels, including pending
    far_all = []
    for c in calls:
        px = c.get("price_asof")
        for t in c.get("targets") or []:
            if t.get("already_at") or not px or px <= 0:
                continue
            if abs((t.get("value") or 0) / px - 1) < MIN_DIST:
                continue
            far_all.append(t)
    for t in far_all:
        if t.get("hit") and t.get("days_to_hit") is not None:
            d = t["days_to_hit"]
            if d <= 5:
                counts[d - 1] += 1
            elif d <= 10:
                counts[5] += 1
            else:
                counts[6] += 1
        else:
            counts[7] += 1
    chart = bar_chart(buckets, counts, label="Levels ≥3% from spot", n_labels=None, colors=["#7aa2ff"] * 7 + ["#7f8b9c"], y_format="count")
    if n == 0:
        sentence = "Not enough named levels at least 3% from the then-current price had a finished 10-session window, so this test did not run."
    else:
        sentence = (
            f"Named levels at least 3% from the then-current price were tagged on a later daily high or low "
            f"in {n_hit} of {n} resolved cases ({pct(hr)}) within 10 sessions"
        )
        if med is not None:
            sentence += f", and among those tagged the median wait was {med} trading day{'s' if med != 1 else ''}"
        if n_pending_far:
            sentence += f"; {n_pending_far} further levels are still pending and are not counted as misses"
        if n < N_MIN:
            sentence += "; too few calls to trust"
        else:
            sentence += (
                ". A 50% coin-flip is a poor model of whether a 10-session high/low will tag a nearby level "
                f"in a volatile sample (raw p={p_raw:.2f} vs 50%), so this is not evidence that naming a level made it happen"
            )
        sentence += "."
    f = finding(
        id="price_talk",
        title="Did named price levels get tagged?",
        test_id=4,
        n=n,
        sentence=sentence,
        chart=chart,
        p_value=None,  # do not rank this on a 50% baseline
        test_name="Descriptive tag rate for parsed price-talk levels at least 3% from spot, using daily high/low, resolved after 10 sessions. A 50% binomial is not used for ranking because it is a poor null for 10-day ranges.",
        horizon=None,
        stats={**(scores.get("targets_summary") or {}), "resolved_far": {"n": n, "n_hit": n_hit, "hit_rate": hr, "p_vs_50_not_used_for_rank": p_raw}, "pending_far": n_pending_far, "min_dist": MIN_DIST},
    )
    return f


def test_chasing(calls):
    horizon, base = pick_horizon(calls)
    chase = [c for c in base if c.get("chase")]
    rest = [c for c in base if not c.get("chase")]
    # also chase-up bullish vs other bullish
    rc, nc = rate(chase, horizon)
    rr, nr = rate(rest, horizon)
    n = nc + nr
    p, diff = (1.0, None)
    if nc and nr:
        p, diff = permutation_diff_p(hits(chase, horizon), hits(rest, horizon))
    bull_up = [c for c in chase if c.get("chase_dir") == "up" and c.get("sentiment") == "bullish"]
    bear_dn = [c for c in chase if c.get("chase_dir") == "down" and c.get("sentiment") == "bearish"]
    rbu, nbu = rate(bull_up, horizon)
    rbd, nbd = rate(bear_dn, horizon)
    parts = [
        f"calls made right after a session whose move was more than twice that stock's typical daily move (20-session median) hit {pct(rc)} over {horizon} ({nfmt(nc)})",
        f"other directional calls hit {pct(rr)} ({nfmt(nr)})",
    ]
    if nbu:
        parts.append(f"bullish calls after a big up day hit {pct(rbu)} ({nfmt(nbu)})")
    if nbd:
        parts.append(f"bearish calls after a big down day hit {pct(rbd)} ({nfmt(nbd)})")
    if n >= N_MIN and nc and nr:
        if p < ALPHA:
            parts.append(f"the main gap is unlikely under a shuffle (p={p:.2f}), not a claim that chasing causes worse or better outcomes")
        else:
            parts.append(f"the main gap could be chance (p={p:.2f})")
    elif n < N_MIN:
        parts.append("too few calls to trust")
    sentence = "; ".join(parts) + "."
    chart = bar_chart(
        ["After a big move", "Other calls", "Bullish after a big up", "Bearish after a big down"],
        [rc, rr, rbu, rbd],
        label=f"{horizon} hit rate",
        n_labels=[nc, nr, nbu, nbd],
        colors=["#e0b34c", "#7f8b9c", "#3ecf8e", "#f06470"],
    )
    return finding(
        id="chasing",
        title="Recency / chasing big days",
        test_id=5,
        n=n,
        sentence=sentence,
        chart=chart,
        p_value=p if (nc and nr) else None,
        test_name=f"permutation test of {horizon} hit rate, calls after |prior session| > 2× 20-session median daily move vs others",
        horizon=horizon,
        stats={
            "chase": {"n": nc, "hit_rate": rc},
            "rest": {"n": nr, "hit_rate": rr},
            "bullish_after_up": {"n": nbu, "hit_rate": rbu},
            "bearish_after_down": {"n": nbd, "hit_rate": rbd},
            "diff": diff,
        },
    )


def test_regime(calls):
    horizon, base = pick_horizon(calls)
    bulls = [c for c in base if c.get("sentiment") == "bullish" and c.get("above_sma50") is not None]
    above = [c for c in bulls if c.get("above_sma50")]
    below = [c for c in bulls if c.get("above_sma50") is False]
    ra, na = rate(above, horizon)
    rb, nb = rate(below, horizon)
    n = na + nb
    p, diff = (1.0, None)
    if na and nb:
        p, diff = permutation_diff_p(hits(above, horizon), hits(below, horizon))
    if not bulls:
        sentence = "Not enough bullish calls had a 50-day average to compare the two regimes."
    else:
        sentence = (
            f"Bullish calls when the stock was above its 50-day average hit {pct(ra)} over {horizon} ({nfmt(na)}); "
            f"when it was below, they hit {pct(rb)} ({nfmt(nb)})"
        )
        if n < N_MIN:
            sentence += "; too few calls to trust."
        elif na and nb and p < ALPHA:
            sentence += f". The gap is unlikely under a shuffle (p={p:.2f}), not evidence that the average itself caused the outcomes."
        elif na and nb:
            sentence += f"; the gap could be chance (p={p:.2f})."
        else:
            sentence += "."
    chart = bar_chart(
        ["Bullish, above 50-day", "Bullish, below 50-day"],
        [ra, rb],
        label=f"{horizon} hit rate",
        n_labels=[na, nb],
        colors=["#3ecf8e", "#f06470"],
    )
    return finding(
        id="regime",
        title="Bullish calls above vs below the 50-day average",
        test_id=6,
        n=n,
        sentence=sentence,
        chart=chart,
        p_value=p if (na and nb) else None,
        test_name=f"permutation test of {horizon} hit rate for bullish calls above vs below the 50-day average at the last close on or before the video date",
        horizon=horizon,
        stats={"above": {"n": na, "hit_rate": ra}, "below": {"n": nb, "hit_rate": rb}, "diff": diff},
    )


def test_overlap(calls):
    # pairwise agreement: same ticker, both directional, other mention within 3 days
    by_t = defaultdict(list)
    for c in calls:
        if c.get("sentiment") not in ("bullish", "bearish") or not c.get("date"):
            continue
        by_t[c["ticker"]].append(c)
    pair = defaultdict(lambda: {"agree": 0, "total": 0, "same_day": 0})
    for ticker, rows in by_t.items():
        rows = sorted(rows, key=lambda r: (r["date"], r["i"]))
        for i, a in enumerate(rows):
            da = parse_date(a["date"])
            for b in rows[i + 1 :]:
                if a["channel"] == b["channel"]:
                    continue
                db = parse_date(b["date"])
                if not da or not db:
                    continue
                lag = (db - da).days
                if lag > 3:
                    break
                if lag < 0:
                    continue
                key = tuple(sorted((a["channel"], b["channel"])))
                pair[key]["total"] += 1
                if a["sentiment"] == b["sentiment"]:
                    pair[key]["agree"] += 1
                if lag == 0:
                    pair[key]["same_day"] += 1

    rows = []
    for (a, b), st in pair.items():
        if st["total"] <= 0:
            continue
        rows.append({
            "a": a, "b": b,
            "n": st["total"],
            "agree": st["agree"],
            "rate": st["agree"] / st["total"],
            "same_day": st["same_day"],
            "p": binom_two_sided(st["agree"], st["total"], 0.5),
        })
    rows.sort(key=lambda r: (-r["n"], -r["rate"], r["a"], r["b"]))
    # near-copies: high agreement and decent n
    copies = [r for r in rows if r["n"] >= N_MIN and r["rate"] >= 0.8]
    notable = [r for r in rows if r["n"] >= N_MIN]
    # chart: top 8 pairs by n
    top = rows[:8]
    labels = [f"{r['a'].replace('official','')} × {r['b'].replace('official','')}" for r in top]
    # shorten labels a bit
    def short(s):
        return s.replace("official", "").replace("AfterHours", "AH")[:18]
    labels = [f"{short(r['a'])} · {short(r['b'])}" for r in top]
    chart = bar_chart(
        labels,
        [r["rate"] for r in top],
        label="Agreement",
        n_labels=[r["n"] for r in top],
        colors=["#7aa2ff"] * len(top),
    )
    n_all = sum(r["n"] for r in rows)
    # overall agreement
    ag = sum(r["agree"] for r in rows)
    overall = (ag / n_all) if n_all else None
    p_all = binom_two_sided(ag, n_all, 0.5) if n_all else 1.0
    if not rows:
        sentence = "There were not enough overlapping directional mentions (same ticker within three days) to compare creators."
        n_use = 0
        p = None
    else:
        if copies:
            bits = ", ".join(f"{r['a']} and {r['b']} agreed {pct(r['rate'])} of the time ({nfmt(r['n'])})" for r in copies[:3])
            sentence = f"Closest overlaps (same ticker within three days): {bits}"
        elif notable:
            r0 = notable[0]
            sentence = (
                f"The most-overlapped pair was {r0['a']} and {r0['b']}, agreeing {pct(r0['rate'])} of the time ({nfmt(r0['n'])})"
            )
        else:
            sentence = "No creator pair had 10 or more overlapping directional mentions on the same ticker within three days"
        sentence += f". Across all such pairs, agreement was {pct(overall)} ({ag} of {nfmt(n_all)})"
        if n_all < N_MIN:
            sentence += "; too few calls to trust."
        elif p_all < ALPHA:
            sentence += f", which is unlikely under a 50% coin-flip (p={p_all:.2f}) — that only means agreement is uneven, not that anyone is copying anyone."
        else:
            sentence += f"; versus a 50% baseline this could be chance (p={p_all:.2f})."
        n_use = n_all
        p = p_all
    return finding(
        id="overlap",
        title="Creator overlap (agreement on the same ticker)",
        test_id=7,
        n=n_use,
        sentence=sentence if rows else sentence,
        chart=chart if top else bar_chart(["No overlapping pairs"], [0], y_format="percent"),
        p_value=p,
        test_name="binomial test of pairwise sentiment agreement vs 50%, for directional mentions of the same ticker within 3 days",
        horizon=None,
        stats={"pairs": rows[:15], "overall_rate": overall, "n_pairs": len(rows), "near_copies": copies},
    )


def test_timing(calls, prices):
    findings = []
    horizon, base = pick_horizon(calls)
    # Weekday
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    by_w = defaultdict(list)
    for c in base:
        if c.get("weekday"):
            by_w[c["weekday"]].append(c)
    labels = [d for d in order if d in by_w]
    rates, ns = [], []
    for d in labels:
        r, n = rate(by_w[d], horizon)
        rates.append(r)
        ns.append(n)
    # test weekday vs rest for the most extreme day with n>=10, else all
    p_week = None
    extreme = None
    for d in labels:
        if ns[labels.index(d)] < N_MIN:
            continue
        grp = by_w[d]
        rest = [c for c in base if c.get("weekday") != d]
        if len(rest) < N_MIN:
            continue
        p, diff = permutation_diff_p(hits(grp, horizon), hits(rest, horizon))
        if extreme is None or p < extreme[0]:
            extreme = (p, d, rate(grp, horizon)[0], len(grp), diff)
    p_week = extreme[0] if extreme else (binom_two_sided(sum(hits(base, horizon)), len(base), 0.5) if base else None)
    parts = []
    if labels:
        pretty = ", ".join(f"{d} {pct(rates[i])} ({nfmt(ns[i])})" for i, d in enumerate(labels))
        parts.append(f"{horizon} hit rate by video weekday was {pretty}")
    parts.append("a separate calendar 'call date' is not in the data — mentions use the video date, and the timestamp is seconds into the video, not a posting lag")
    if extreme and extreme[3] + len(base) >= N_MIN:
        if extreme[0] < ALPHA:
            parts.append(f"{extreme[1]} stood out vs the other days (p={extreme[0]:.2f}), which could still be a calendar fluke and is not a reason to trade a weekday")
        else:
            parts.append(f"no weekday's gap from the others was hard to explain by chance (lowest p={extreme[0]:.2f})")
    n_w = len(base)
    if n_w < N_MIN:
        parts.append("too few calls to trust")
    sentence = "; ".join(parts) + "."
    findings.append(finding(
        id="weekday",
        title="Video weekday",
        test_id=8,
        n=n_w,
        sentence=sentence,
        chart=bar_chart(labels, rates, label=f"{horizon} hit rate", n_labels=ns, colors=["#7aa2ff"] * len(labels)),
        p_value=p_week,
        test_name=f"permutation test of {horizon} hit rate for each weekday vs the others (most extreme p reported); posting lag not available as a separate date",
        horizon=horizon,
        stats={"by_weekday": {d: {"n": ns[i], "hit_rate": rates[i]} for i, d in enumerate(labels)}},
    ))

    # Pre vs post earnings — only if real dates exist
    earn_status = prices.get("earnings_status") or "not available"
    has_earn = any(c.get("earnings") in ("pre", "post", "neither") for c in calls)
    if not has_earn or earn_status == "not available":
        findings.append(finding(
            id="earnings",
            title="Pre vs post earnings",
            test_id=8,
            n=0,
            sentence="Pre vs post earnings is not available: no earnings dates were obtained from yfinance, and none were guessed.",
            chart=bar_chart(["Not available"], [0], label="Hit rate", n_labels=[0], colors=["#7f8b9c"]),
            p_value=None,
            test_name="skipped — earnings dates not available",
            horizon=horizon,
            stats={"earnings_status": earn_status},
        ))
        # force too_few / flag
        findings[-1]["too_few"] = True
        findings[-1]["flag"] = "not available"
        findings[-1]["strength"] = 0
        return findings

    pre = [c for c in base if c.get("earnings") == "pre"]
    post = [c for c in base if c.get("earnings") == "post"]
    neither = [c for c in base if c.get("earnings") == "neither"]
    unknown = [c for c in base if c.get("earnings") is None]
    rp, np_ = rate(pre, horizon)
    ro, no = rate(post, horizon)
    rn, nn = rate(neither, horizon)
    n = np_ + no
    p, diff = (1.0, None)
    if np_ and no:
        p, diff = permutation_diff_p(hits(pre, horizon), hits(post, horizon))
    sentence = (
        f"Directional calls in the five sessions before a listed earnings date hit {pct(rp)} over {horizon} ({nfmt(np_)}); "
        f"calls in the three sessions after earnings hit {pct(ro)} ({nfmt(no)}); "
        f"calls away from earnings hit {pct(rn)} ({nfmt(nn)})"
    )
    if unknown:
        sentence += f"; {len(unknown)} scored calls had no earnings date for that ticker"
    if n < N_MIN:
        sentence += ". Too few calls to trust."
    elif np_ and no and p < ALPHA:
        sentence += f". The pre/post gap is unlikely under a shuffle (p={p:.2f}), not evidence that earnings caused the difference."
    elif np_ and no:
        sentence += f"; the pre/post gap could be chance (p={p:.2f})."
    else:
        sentence += "."
    findings.append(finding(
        id="earnings",
        title="Pre vs post earnings",
        test_id=8,
        n=n if n else np_ + no + nn,
        sentence=sentence,
        chart=bar_chart(
            ["5 sessions before earnings", "3 sessions after earnings", "Away from earnings"],
            [rp, ro, rn],
            label=f"{horizon} hit rate",
            n_labels=[np_, no, nn],
            colors=["#e0b34c", "#7aa2ff", "#7f8b9c"],
        ),
        p_value=p if (np_ and no) else None,
        test_name=f"permutation test of {horizon} hit rate, calls in the 5 sessions before a yfinance earnings date vs the 3 sessions after; dates are not guessed when missing",
        horizon=horizon,
        stats={"pre": {"n": np_, "hit_rate": rp}, "post": {"n": no, "hit_rate": ro}, "neither": {"n": nn, "hit_rate": rn}, "unknown": len(unknown), "diff": diff},
    ))
    return findings


def test_flips(calls, scores):
    horizon, base = pick_horizon(calls)
    firsts = [c for c in base if c.get("is_first_call")]
    flips = [c for c in base if c.get("is_flip")]
    # some flips may be pending on 5d; pick_horizon already filtered
    rf, nf = rate(firsts, horizon)
    rflip, nflip = rate(flips, horizon)
    n = nf + nflip
    p, diff = (1.0, None)
    if nf and nflip:
        p, diff = permutation_diff_p(hits(flips, horizon), hits(firsts, horizon))
    # also 1d if 5d flips are few
    note = ""
    if nflip < N_MIN:
        f1 = [c for c in scored(calls, "1d") if c.get("is_flip")]
        first1 = [c for c in scored(calls, "1d") if c.get("is_first_call")]
        r1, n1 = rate(f1, "1d")
        r1f, n1f = rate(first1, "1d")
        if n1:
            note = f" On the 1d score, flipped calls hit {pct(r1)} ({nfmt(n1)}) vs {pct(r1f)} for first calls ({nfmt(n1f)})."
    sentence = (
        f"When a creator flipped from bullish to bearish or the other way, those flipped {horizon} calls hit {pct(rflip)} ({nfmt(nflip)}), "
        f"versus {pct(rf)} for that creator's first scored call on a ticker ({nfmt(nf)})"
    )
    if n < N_MIN or nflip < N_MIN:
        sentence += ". Too few calls to trust."
    elif p < ALPHA:
        sentence += f". The gap is unlikely under a shuffle (p={p:.2f}), not evidence that flipping itself is an edge."
    else:
        sentence += f"; the gap could be chance (p={p:.2f})."
    sentence += note
    chart = bar_chart(
        ["Flipped calls", "First call on a ticker"],
        [rflip, rf],
        label=f"{horizon} hit rate",
        n_labels=[nflip, nf],
        colors=["#e0b34c", "#7aa2ff"],
    )
    return finding(
        id="flips",
        title="Flip quality vs first calls",
        test_id=9,
        n=n if nflip >= N_MIN else nflip,
        sentence=sentence,
        chart=chart,
        p_value=p if (nf and nflip) else None,
        test_name=f"permutation test of {horizon} hit rate, a creator's flipped call vs their first directional call on that ticker",
        horizon=horizon,
        stats={"flips": {"n": nflip, "hit_rate": rflip}, "firsts": {"n": nf, "hit_rate": rf}, "diff": diff, "n_flip_events": len(scores.get("flips") or [])},
    )


def test_creator_best(calls):
    horizon, base = pick_horizon(calls)
    by_ch = defaultdict(list)
    for c in base:
        by_ch[c["channel"]].append(c)
    ch_rows = []
    for ch, rows in by_ch.items():
        r, n = rate(rows, horizon)
        p = binom_two_sided(sum(hits(rows, horizon)), n, 0.5) if n else 1.0
        ch_rows.append({"channel": ch, "n": n, "hit_rate": r, "p": p})
    ch_rows.sort(key=lambda r: (-(r["hit_rate"] or -1), -r["n"]))

    # per creator-ticker
    by_ct = defaultdict(list)
    for c in base:
        by_ct[(c["channel"], c["ticker"])].append(c)
    ct_rows = []
    for (ch, t), rows in by_ct.items():
        r, n = rate(rows, horizon)
        ct_rows.append({"channel": ch, "ticker": t, "n": n, "hit_rate": r})
    ct_ok = [r for r in ct_rows if r["n"] >= N_MIN]
    ct_ok.sort(key=lambda r: (-(r["hit_rate"] or -1), -r["n"]))

    # sector
    by_cs = defaultdict(list)
    missing_sector = 0
    for c in base:
        sec = c.get("sector")
        if not sec:
            missing_sector += 1
            continue
        by_cs[(c["channel"], sec)].append(c)
    cs_rows = []
    for (ch, sec), rows in by_cs.items():
        r, n = rate(rows, horizon)
        cs_rows.append({"channel": ch, "sector": sec, "n": n, "hit_rate": r})
    cs_ok = [r for r in cs_rows if r["n"] >= N_MIN]
    cs_ok.sort(key=lambda r: (-(r["hit_rate"] or -1), -r["n"]))

    # chart: per-creator overall
    labels = [r["channel"] for r in ch_rows]
    chart = bar_chart(
        labels,
        [r["hit_rate"] for r in ch_rows],
        label=f"{horizon} hit rate",
        n_labels=[r["n"] for r in ch_rows],
        colors=["#7aa2ff"] * len(labels),
    )
    usable = [r for r in ch_rows if r["n"] >= N_MIN]
    parts = []
    if usable:
        best = usable[0]
        worst = min(usable, key=lambda r: (r["hit_rate"] if r["hit_rate"] is not None else 99, -r["n"]))
        parts.append(
            f"among creators with at least 10 scored {horizon} calls, {best['channel']} had the highest hit rate at {pct(best['hit_rate'])} ({nfmt(best['n'])}, p={best['p']:.2f} vs 50%) "
            f"and {worst['channel']} the lowest at {pct(worst['hit_rate'])} ({nfmt(worst['n'])}, p={worst['p']:.2f})"
        )
        # overall most extreme p
    else:
        parts.append("no creator had 10 scored calls at this horizon")
    if ct_ok:
        b = ct_ok[0]
        w = min(ct_ok, key=lambda r: (r["hit_rate"] if r["hit_rate"] is not None else 99))
        parts.append(
            f"at the creator-ticker level, {b['channel']} on {b['ticker']} was best at {pct(b['hit_rate'])} ({nfmt(b['n'])})"
        )
    else:
        parts.append("no creator-ticker pair had 10 scored calls, so best/worst tickers are too few calls to trust")
    if cs_ok:
        b = cs_ok[0]
        parts.append(
            f"the strongest creator-sector slice with enough calls was {b['channel']} in {b['sector']} at {pct(b['hit_rate'])} ({nfmt(b['n'])})"
        )
    else:
        parts.append("no creator-sector slice had 10 scored calls" + (" (some tickers have no yfinance sector)" if missing_sector else ""))
    # p: most extreme creator vs 50% with n>=10
    p = None
    if usable:
        raw_p = min(r["p"] for r in usable)
        p = min(1.0, raw_p * len(usable))  # Bonferroni across creators with n>=10
        if p < ALPHA:
            parts.append(f"at least one creator's rate is unlikely under a 50% coin-flip even after a Bonferroni adjustment for {len(usable)} creators (adjusted p={p:.2f}), which is still not a ranking of skill")
        else:
            parts.append(f"those creator gaps could be chance (lowest p={raw_p:.2f} vs 50%, {p:.2f} after adjusting for {len(usable)} creators)")
    n_use = max((r["n"] for r in ch_rows), default=0)
    # actually use total scored for n, but flag based on per-creator
    n_total = len(base)
    sentence = "; ".join(parts) + "."
    return finding(
        id="creator_best",
        title="Per-creator hit rates, tickers, and sectors",
        test_id=10,
        n=n_total,
        sentence=sentence,
        chart=chart,
        p_value=p,
        test_name=f"binomial test of each creator's {horizon} hit rate vs 50%; ticker and sector slices only highlighted when n≥10; sector from yfinance when available",
        horizon=horizon,
        stats={"by_creator": ch_rows, "by_creator_ticker_n10": ct_ok, "by_creator_sector_n10": cs_ok, "missing_sector_calls": missing_sector},
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scores", default=os.path.join(DATA, "scores.json"))
    ap.add_argument("--prices", default=os.path.join(DATA, "prices.json"))
    ap.add_argument("--out", default=os.path.join(DATA, "insights.json"))
    args = ap.parse_args(argv)

    for p in (args.scores, args.prices):
        if not os.path.exists(p):
            print(f"missing {p} — run scripts/fetch_prices.py and scripts/score.py first", file=sys.stderr)
            return 1

    scores = load_json(args.scores)
    prices = load_json(args.prices)
    calls = scores.get("calls") or []

    findings = []
    findings.append(test_consensus(calls))
    findings.append(test_herding(calls))
    findings.append(test_spikes(calls, prices))
    findings.append(test_price_talk(scores))
    findings.append(test_chasing(calls))
    findings.append(test_regime(calls))
    findings.append(test_overlap(calls))
    findings.extend(test_timing(calls, prices))
    findings.append(test_flips(calls, scores))
    findings.append(test_creator_best(calls))

    # sort by strength desc, too_few / not available last
    def sort_key(f):
        last = 1 if (f.get("too_few") or f.get("flag") == "not available") else 0
        return (last, -f.get("strength") or 0, f.get("test_id") or 99)

    findings.sort(key=sort_key)
    for i, f in enumerate(findings, 1):
        f["rank"] = i

    thin = [f["title"] for f in findings if f.get("too_few") or f.get("flag") in ("too few calls to trust", "not available")]
    notable = [f for f in findings if f.get("significant") and not f.get("too_few")]

    out = {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "scores_generated_at": scores.get("generated_at"),
        "prices_generated_at": prices.get("generated_at"),
        "assumptions": scores.get("assumptions") or [],
        "baseline": "50% hit rate for directional calls, and a permutation or bootstrap comparison between groups. SPY-adjusted rates are in the scorecard, not the primary insight tests.",
        "alpha": ALPHA,
        "n_min": N_MIN,
        "disclaimer": "These are associations in a short sample. A low p-value is not proof, and nothing here is a cause-and-effect claim or a trading recommendation.",
        "summary": scores.get("summary") or {},
        "n_findings": len(findings),
        "n_significant": len(notable),
        "too_few_or_unavailable": thin,
        "findings": findings,
    }
    atomic_write(args.out, out)
    print(f"wrote {args.out}  findings={len(findings)} notable={len(notable)} thin={len(thin)}", flush=True)
    for f in findings:
        flag = f["flag"] or ("notable" if f["significant"] else "ok")
        pv = "—" if f["p_value"] is None else f"p={f['p_value']:.3f}"
        print(f"  {f['rank']:2d}. [{flag}] {f['title']}  n={f['n']} {pv}  {f['sentence'][:160]}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
