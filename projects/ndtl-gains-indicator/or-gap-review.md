# OR + gap code review (read-only; script = ndtl-gains-v2.pine, 1487 lines, from t1u; no strat_mega_v2.txt attachment found, so t1u is the source)
Line numbers refer to ndtl-gains-v2.pine. Nothing was changed.

## Gap line: f_preGapHL (l.511) + gapLevel (l.521-538)
Verdict: the lookahead use is safe. Two real bugs and a few weak spots.
Safe:
- f_preGapHL reads only low[1]/high[1] of the 3-min bar. lookahead_on only releases it at the chart bar where that 3m bar opens, and that value depends only on prior data, so nothing peeks forward.
- 3m bars are bucket-aligned (4:00, 4:03 ...), so on 15S/1m/3m charts the first chart bar after the break maps to the same 3m bar. On 5m+ charts the 3m series is lower than the chart TF, and var gl/gh latches the value, so the result is the same.
Bugs / risks:
1. (BUG, inconsistent fib side) l.536 picks gapLevel by the MIDPOINT of the pre-break candle. l.555 decides gapDown as gapNewOpen <= gapLevel. If the open is inside the candle and below the midpoint, gapLevel = low but gapDown is false (open > low), so the fibs are measured from the premarket HIGH while the gap line is the LOW. Fix: store the side chosen at l.536 and set gapDown from it (open < midpoint), or use gapDown = open < pgLo and treat inside-candle as no gap.
2. (BUG, stale value) l.512-518: gl/gh are `var` and never reset. If the 3m series has no bar flagged as a session break (feed hiccup, symbol with a different "D" boundary), the old day's candle is reused silently at l.534-535 (na() fallback to low[1] never triggers because the value is stale, not na). Fix: reset gl/gh to na when nd, then set.
3. (RISK) "last 3m candle before the break" is the last candle with data, not literally the 7:57 PM slot. On thin tickers it can be earlier (e.g. 7:30 PM). Unknown whether PP uses the last print or the 7:57 slot; compare on a thin name.
4. (RISK) gapHours >= 5 on the chart (l.506) and nd/5h on the 3m series are evaluated separately; on a 15S chart with no print until 4:20 they still agree, but half-day sessions where AH is shorter than expected could differ. OK in practice.
5. gapNewOpen is the first chart bar's open of the day = first premarket print; identical on every TF. OK.

## Opening range code (l.313-498)
Chart-timeframe independence: OK. Impulse/confirm OR run in request.security on orConfirmTf with lookahead_off and are latched by var, so 15S/1/3/5m charts get the same final level as long as orConfirmTf is the same. Results DO depend on orConfirmTf (1m vs 15S) and orSkipOpen then skips a whole 1m candle vs 15 seconds.
Bugs / risks:
1. Realtime un-lock: inside request.security, var state rolls back on each tick of the developing bar. A lock made intrabar on the forming orConfirmTf candle can disappear before that candle closes (intrabar repaint on the live bar only; history is fine). To avoid: make lock decisions on bar close only (barstate.isconfirmed inside the function) or accept it.
2. l.452-456: when a candle sets a new high, lowSinceH is reset to that candle's CLOSE, so a candle that makes the high and then drops a lot inside the same candle (very common at the open on 1m) never counts as a snap-back. Same on the low side. This makes the rule depend on candle size / orConfirmTf. The 15S timeframe shrinks it but does not remove it.
3. l.444-445 orSkipOpen replaces the first candle's high/low with its close, but its own pullback state (lowSinceH/highSinceL = close) is also blind. It also means the first candle can never be the OR extreme: yet Naman's AVGO row says PP's ORH 311.5 was made at 9:30. That conflicts with skipping. (On my inferred Nov-6 AVGO 1m bar the 9:30 high is 311.35.)
4. l.466-471 the % of range snap-back uses the CURRENT range, which is ~0 right after the open, so a tiny wiggle satisfies "30% of range" very early and locks a side at once (min 3 min only delays the check, then it fires immediately). Rule is very sensitive in the first minutes.
5. l.419/l.469: `forced` locks at orMaxMinutes (60) at whatever extreme: a side that never snaps back keeps moving for an hour; PP likely does not. Compare lock times in the truth CSV.
6. orMaxMinutes has minval=5 and orMinMinutes minval=0; orMinMinutes max 60 > ok. Harmless.
7. l.478 / l.488 `rthStartTime - 5 min` tolerance is not needed (imStart is the 9:30 candle time) and would admit a prior-day value if rthStartTime ever came from an early bar; harmless today.
8. l.498 orLocked needs BOTH sides; the retest logic (l.702) therefore waits for the slower side. Intended? Probably fine.
9. Mode 1 (Time window) l.370: orIsToday uses orTfTime >= rthStartTime - orMinutes*60000; correct, but the 9:30 "10" bar closes at 9:40 so ORH/ORL are not visible until then. Fine, no repaint.

## fit_or.py
fit_or.py reads pp_or_truth.csv; sample rows are ILLUSTRATIVE (Naman's screenshot table values with an inferred date, 2026-11-06, taken by matching yfinance 1m bars, not verified against PP). The five rows in the sample are only to prove the script runs; do not draw conclusions. Yahoo 1m bars are consolidated feed bars and can differ from TradingView's by a few cents.
