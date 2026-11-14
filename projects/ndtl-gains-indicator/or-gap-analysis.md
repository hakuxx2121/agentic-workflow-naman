# NDTL Gains v2.1 — Paper Prophet opening range + gap line

## The rule (plain words)
Each side of the opening range follows its running high (or low), starting with the 9:30 candle INCLUDING its wick. A new high resets that side's clock. When 4 minutes (four 1-minute candles) pass after the candle that made the high without anything beating it, the high locks. The low works the same way. While a side keeps making new extremes it stays hidden. Once locked it stays, even if price later goes through it.
Pine: input `orQuietMin` = 4 in f_impulseOR. The snap-back rule is kept but Off by default (`orImpulseBy` = "Off"). `orSkipOpen` now defaults to Off.

## Why 4 (what the data pins down)
Verified against Yahoo 1m bars (fit_or.py, family `nonext`):
- SPY Nov 9 (measured by Naman on TradingView): ORH 747.93 = the 9:52 high. Quiet = 3 locks at the 9:45 high (747.05, which is what Bar Replay showed). Quiet = 5 never locks near 9:52 (goes to 749.42). Only 4 gives 747.93.
- SPY Nov 6: ORH 742.23 = the 9:54 high. Quiet = 3 would lock early at 736.41 (9:33 high). Only 4 or more reaches 742.21.
So 3 fails Nov 6 and 5 fails Nov 9, and 4 fits both. This is the single parameter the evidence supports, but it rests on two SPY days (Nov 6's date is inferred), so more rows are needed.
Other rules tried (best of each, all 9 rows, per-row tolerances): n_candle (red/green closes) 8/9 rows, pivot 8/9, ATR pullback 7/9, % of price 7/9, fixed 10-min window 7/9, % of range snap-back 6/9. Quiet-minutes 9/9. These counts use loose tolerance (see below).

## Per-row fit (Pine rule, 1m bars, orQuietMin=4, skipOpen off)
Dates for everything except SPY Nov 9 are INFERRED: Nov 6 is the best date for all 8 tickers in Yahoo data (every PP value is within 0.26 of a real Nov 6 bar high/low and no other day is close on all of them).
| Row | PP ORH | Rule ORH (bar) | diff | PP ORL | Rule ORL (bar) | diff |
|---|---|---|---|---|---|---|
| SPY Nov 9 (measured) | 747.93 | 747.93 (9:52) | 0.00 | 741.03 | 741.03 (9:30) | 0.00 |
| SPY Nov 6 | 742.23 | 742.21 (9:54) | -0.02 | 734.59 | 734.58 (9:30) | -0.01 |
| COIN | 138.26 | 138.24 (9:30) | -0.02 | 133.90 | 133.89 (9:35) | -0.01 |
| AVGO | 311.50 | 311.35 (9:30) | -0.15 | 302.75 | 302.75 (9:35) | 0.00 |
| MSFT | 532.50 | 532.44 (9:33) | -0.06 | 524.50 | 524.61 (9:30) | +0.11 |
| AMZN | 263.56 | 263.55 (9:38) | -0.01 | 258.53 | 258.63 (9:30) | +0.10 |
| AAPL | 341.70 | 341.68 (9:32) | -0.02 | 338.31 | 338.30 (9:30) | -0.01 |
| GOOGL | 290.45 | 290.49 (9:39) | +0.04 | ~284.6 | 284.78 (9:30) | +0.18 |
| META | ~622.2 | 622.19 (9:39) | -0.01 | ~606.7 | 606.96 (9:30) | +0.26 |
At the strict ±0.05: 12 of 18 sides match (SPY, COIN, AAPL all sides; AVGO ORL; AMZN/MSFT/GOOGL/META ORH within 0.06). The other 6 sides (AVGO ORH, MSFT ORH 0.06, MSFT/AMZN/GOOGL/META ORL) pick the SAME candle PP's value points to but differ by 0.04-0.26 in price.

## Which rows break and why
- The rule picks the right candle on every row (9 of 9 rows, both sides). It does not break on any row's logic.
- Remaining price gaps are all small and have one pattern: PP's 9:30 low is LOWER than the Yahoo 9:30 low by 0.10-0.26 (MSFT, AMZN, GOOGL, META) and AVGO's high is 0.15 higher. That looks like data (TradingView's 9:30 candle includes small prints Yahoo drops), not a different rule. Not verifiable without TradingView's own 1m/15s bars.
- The "ignored opening wick" rows (MSFT 520.0, AMZN 258.1, AAPL 338.0): those wicks are not in the Yahoo bars at all (Yahoo 9:30 lows 524.61, 258.63, 338.30). PP's values sit near Yahoo's, so PP is NOT skipping a wick in the rule; the chart's wick is a print PP's data excludes. SPY keeps its 9:30 low. So skipOpen must stay OFF. Whether PP drops only the first 15 s print cannot be tested here (no 15s data).
- Bar Replay disagrees with the live chart (SPY Nov 9 replay: 747.05 locked early and never updates; live: 747.93). Replay looks like quiet=3 with no later reset. I have no rule that explains both; the rule above matches the loaded-chart (historical) values, which is what all the other measurements are.
- Lock times in Naman's table (e.g. SPY ORH ~9:57, ORL ~9:33) are 1-2 candles earlier than this rule (SPY ORH locks 9:58, ORL 9:34). Those times were eyeballed.

## Gap line fixes
1. gapDown now comes from the chosen side (`gapIsDown`): gap line = candle HIGH means gap up (fibs from premarket high), = LOW means gap down (fibs from premarket low). Before, an open inside the candle could pair a LOW line with premarket-high fibs, or the reverse.
2. f_preGapHL resets gl/gh to na on every new day before setting them, so a day without a detected break can't reuse yesterday's candle.
Unchanged: lookahead_on stays (only prior-candle data is released), no extra repaint.

## Also changed in OR code
- Lock decisions only happen on a closed data candle (`barstate.isconfirmed`), so a lock can't appear and then vanish on the live candle (review item 1).

## Not changed / remaining risks
- Not compiled in TradingView (no compiler on the box). Changes are small and checked by reading; paste into the Pine editor and fix any error. Logic is cross-checked by a literal Python port (matches the table above).
- Quiet minutes is measured on `orConfirmTf` candles (default 1m). With 15S it counts 4 minutes after the extreme candle closes, not four 1m candles, so levels can differ slightly. Keep "1" to match these measurements.
- N=4 is supported by two SPY days. Not yet tested: other tickers with a deciding run (a high set, then one more extension after 3 quiet candles). See test plan.
- Snap-back inputs are kept but do nothing unless set; the "min minutes" (3) is irrelevant with quiet=4.
- The forced lock at 60 minutes remains.
- First-print effect for 15S data is untested.

## Test plan
1. On SPY, Nov 9 and Nov 6 at 1m, 5m, 15S: ORH/ORL should read 747.93/741.03 and 742.2x/734.5x with the default inputs, identical on every chart timeframe.
2. Pick 5 more days with a clear run then a late extension (e.g. a stock that makes a new high 4-5 minutes after a pause). Read PP's ORH/ORL and add rows to pp_or_truth.csv with exact dates, then `python3 fit_or.py --detail` (add bars to bars/<T>_<date>_1m.csv if older than Yahoo's window). Look for any day where quiet=3 or 5 fits better than 4.
3. If PP is higher/lower than ours by a few cents on the 9:30 low, compare with TradingView's own 9:30 candle on that ticker: the cause is the opening print.
4. Try orSkipOpen on with orConfirmTf=15S only if a ticker's PP low is above the chart's 9:30 low and Yahoo shows the same low as PP.
5. Replay vs live: record PP's ORH at 9:35/9:45/9:55/10:15 in replay and on the reloaded chart on one more day.

## Nov 9 2026 PP truth (TradingView Data Window + thick yellow dotted lines)

New measured rows (tolerance = stated ± plus 0.06 for Yahoo vs TV print noise):

| Ticker | Chart | PP ORH / ORL | 1m quiet-4 | 1m quiet-5 | First 5m |
|---|---|---|---|---|---|
| AMZN | 1m | 274.7 / 269.3 (±0.1) | 274.74 / 269.32 OK | 275.34 / 269.32 BAD (includes 9:45 TV high 275.34) | 273.64 BAD |
| ARM | 5m | 183.66 / 174.79 (±0.05) | 177.31 / 174.76 (ORH BAD) | 183.59 / 174.76 OK under +0.06 noise (d=-0.07) | 177.31 BAD |
| NVDA | 5m | 175.24 / 170.26 (±0.05) | 175.22 / 170.24 OK | 175.22 / 170.24 OK | 175.22 OK |
| AMD | 5m | 478.86 / 468.34 (±0.15) | 478.68 / 468.21 OK with noise (chart 478.72/468.21) | same | same |
| PLTR | 5m | 166.41 / 161.00 (±0.07) | 166.35 / 161.05 OK | same | same |
| SPY | 5m | ORH unknown / 741.01 | ORL 741.03 OK; quiet-4 ORH would be 747.93 (the earlier 1m measurement) | ORL OK; ORH would be 749.42 | ORL OK |

TV 1m prints confirm AMZN 9:40=274.74 and 9:45=275.34, so a 30-minute window is ruled out for AMZN. TV also confirms ARM 9:57/9:58/9:59 highs 183.71/183.80/183.89, so 183.66 is not the 30-minute high (183.89).

No single 1m rule hits all 6. Quiet-2/3/4 each hit 5/6 (miss ARM ORH). Quiet-5 hits 5/6 (miss AMZN ORH, and ARM 183.59 is only OK if we allow 0.07 of Yahoo/TV noise). Fixed windows, % retrace, ATR, close-inside, and n-candle do not beat this. Historical Nov 6 + the earlier SPY Nov 9 1m measurement (ORH 747.93, not 747.05 or 749.42) are 9/9 only at quiet-4.

Without ARM, quiet-4 minutes on 1m is the rule: 5/5 new rows and 9/9 historical. That is already the v2.1 default (`orQuietMin=4` on `orConfirmTf=1`). It is not chart-timeframe dependent.

With ARM included, the only way to get 183.66 and 274.7 together is to evaluate quiet minutes on the *chart's* bars (4 quiet minutes, decided at bar close: on 1m that is 4 bars; on 5m the next 5m close is enough, i.e. quiet-1 five-minute bar, locking ARM at 183.59 around 9:55). That would be inherently timeframe-dependent: AMZN on a 5m chart would show 275.34, and ARM on a 1m chart would show 177.31. Not implemented, because Naman wants the same levels on 15s/1/3/5m, and because it would contradict the measured SPY 1m ORH 747.93 once the same ticker is opened on 5m.

ARM 183.66 remains the ambiguity. It is 0.07 from the Yahoo 9:49 / 9:45-5m high (183.59), and clearly not the 9:57-9:59 tape. The extra chart reads that would settle it: ARM 9:49 1m and 9:45 5m highs on TradingView, and PP's ORH on an ARM *1m* chart (177.31 would mean 183.66 is not OR; 183.59/183.66 would mean PP is chart-TF dependent).

## Nov 9 2026, ARM settled (same ORH on 1m/3m/5m)

TradingView: ARM ORH is 183.62 on 1m, 3m and 5m (the 9:49 1m high, equal to the 9:45 5m high). ORL is 174.76 (9:33 1m low). PP locked the high after 9:49 and before the 9:57 break (a 4-7 minute pause) and ignored the early 9:31-9:34 pause that makes plain quiet-4 lock at 177.31. AMZN still locked after 9:40 and before the 9:45 high of 275.34.

Truth: the 6 new Nov 9 rows (AMZN 274.74/269.32, ARM 183.62/174.76, NVDA 175.24/170.26, AMD 478.86/468.34, PLTR 166.41/161.00, SPY 747.93/741.01) plus the 8 earlier Nov 6 rows and the measured SPY Nov 9 ORH, 14 rows / 28 sides, TV overrides, per-row ± plus 0.06.

**The rule: 4 quiet 1-minute bars, no lock before T minutes after 9:30.** Extremes still update during [9:30, T); a pause that finishes before T does not lock. Default T=10 (`orMinMinutes=10`, `orQuietMin=4`, `orConfirmTf=1`). Timeframe-independent.

T window on this truth set:

| T | rows | sides | miss |
|---|---|---|---|
| 0-5 | 13/14 | 27/28 | ARM ORH 177.31 (early pause completes at 9:35, elapsed=5) |
| **6-10** | **14/14** | **28/28** | none |
| 11-13 | 13/14 | 27/28 | NVDA ORH (9:40 break is included once T>10) |
| 15 | 12/14 | 26/28 | NVDA, AMD |
| 20 | 9/14 | 23/28 | also AMZN 275.34, COIN 139.28, PLTR |

T=10 is the requested candidate and the upper end of the exact window. T=5, 15 and 20 fail. Quiet-3 at T=10 misses ARM (locks 180.30 after the 3-minute 9:41-9:43 pause). Quiet-5 at T=10 misses AMZN (includes 275.34).

Other requested families:

- quiet-4 counting only from 9:35 (ignore the first 5m bar for the quiet clock): also 14/14. Lock times can be 1-2 minutes earlier than T=10; levels match on this truth set.
- quiet-4 after the running range reaches the first 5m bar's range: also 14/14. The non-repainting form of this is essentially "start after 9:35."
- quiet-N requiring a pullback of X% of range or K x ATR: does **not** fit. ARM's early pause already retraces to 174.76, so the high still locks at 177.31.
- quiet-4 after range >= K x ATR: fails ARM for K=0.5..4 (the early range is already large vs 1m ATR). K=5 happens to fit this set but is fragile.

Implemented by changing the existing `orMinMinutes` default from 3 to 10. No new input, no repainting, same levels on 15s/1/3/5m charts (confirmation stays on 1m).

On the 67-ticker Nov 9 table, 18 names change vs plain quiet-4 (T=3): AEHR, ALAB, ARM, CAT, CRWD, DASH, GEV, IBM, MCD, MRNA, MU, NBIS, QCOM, RDDT, RKLB, SOFI, ZS, SNDK. Largest ORH moves: CAT +8.11, NBIS +7.48, QCOM +7.44, ARM +6.31. AMZN, NVDA, AMD, PLTR and SPY do not change. Those 18 are the best later spot checks.
