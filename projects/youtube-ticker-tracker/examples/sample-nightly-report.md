# Ticker report: 2026-11-14

Nightly run (fetch 01:25 ET, default window). **3 new videos, 36 new mention rows:**
- **futurenvesting:** "The Nvidia Case Is Only Getting Worse... New SpaceX Deal? | Market Monitor" (ssjI2cIyi4o, Nov 13 stream, ~73 min, 13 tickers).
- **TradeBrigade:** "[LIVE] Pre-Market Prep – PPI Inflation Live Market Reaction" (wubxlftpQ5A, Nov 13 stream, ~86 min, 23).
- **ThePlainBagel:** "Canada Just Made Some Big Tax Changes" (V6Vm1LU0kbQ, Nov 13, 0 tickers; it covers Canada's federal budget: the productivity "mega deduction", the Canada Growth Incentive, the creator tax credit, RRSP for life, higher CDIC deposit insurance and the Real-Time Rail payment system. No stocks were discussed).
- **OptionsWithRyan** had a new upload (8YeWNhktU1c) but no transcript (see Channel errors). Nothing new from StockedUp, DumbMoneyLive, StockswithJosh, JosephCarlsonAfterHours, wickedstocksofficial, amitinvesting or joinschoolofgains.

Window: last 7 days (uploads since 2026-11-07), 34 videos, 343 mention rows, skipped videos excluded. Ranked by mention count (video x ticker); ties broken by number of channels.

Context: Nvidia closed around 167 on Nov 13 after rallying ~10% off the gap-down open on ~4.5x normal volume. Hosts call it a "news failure" bounce, but the chart is still damaged. Colette Kress is interim CEO; there are reports the woman at the center may not have been a spy, and Trump and Lex Fridman publicly backed Jensen. PPI came in cooler than expected month over month (0.3% vs 0.4%), and futures ticked up. Markets still price a ~90% chance of a December hike. The Anthropic IPO and Nvidia earnings are next week.

1. **NVDA** (25 mentions / 9 channels; split, leaning cautious: 15 mixed / 5 bullish / 5 bearish). Most hosts think the business is intact, but they see the leaderless company as a real risk. TradeBrigade bought the gap down in his long-term account, and he treats 166 as the line to hold. futurenvesting's host is still holding from the mid-20s but may trim, and he no longer expects 250 unless Jensen returns.
2. **AMD** (16 / 6 channels; bullish: 13 bullish / 2 mixed / 1 bearish). This is the clear rotation winner, up ~45% in a handful of sessions. TradeBrigade wants a pullback to a higher low above ~513 / the 20-day before a new entry.
3. **MU** (14 / 7 channels; leaning bullish: 7 bullish / 3 bearish / 2 mixed / 2 neutral). Value-minded hosts see it as cheap and a winner whichever AI chip maker comes out ahead. Traders say the chart is undecided: it made an inside day near the daily 200.
4. **CRWV** (13 / 6 channels; split: 5 bullish / 4 mixed / 3 bearish / 1 neutral). It sold off ~7% despite strong earnings and ~$9B in customer prepayments. futurenvesting is bullish, citing the CEO's claim that capacity is heavily oversubscribed through 2027-28.
5. **TSLA** (13 / 5 channels; leaning bullish: 6 bullish / 5 mixed / 1 bearish / 1 neutral). It's trading around ~401-408 on reports that SpaceX and Tesla could merge as soon as December or early 2027. futurenvesting thinks a deal would land near ~$500. TradeBrigade would fade a rally into the ~408.50 high rather than buy there.

Also notable: AVGO (13, bullish; TradeBrigade wants a flag/pullback toward the 50-day), QQQ (12, leaning bearish; NQ ~29,000 is major overhead supply), NBIS (12, mostly bullish but hammered after earnings), SPY (11, mixed; ES 7650 is the over/under) and ANT (11, bullish into next week's IPO).

**Tonight's notable new calls**
- **TradeBrigade:** ES 7650 decides the day and the weekly close (7675 / 7700 / 7740 above; 7598 and the gap down to ~7566 below). The NQ downtrend holds until ~29,000 breaks. IWM must stay over ~2,800. NVDA must hold 166. Long GOOGL from ~295.8 (296 must hold). MSFT stays weak below the 50-day after the Office 365 outage and the Anthropic news. Leaders: AMD, AVGO, LLY, ZETA, BSY. Damaged charts: INTC, SNDK, MU.
- **futurenvesting:** still holds NVDA (cost basis in the mid-20s) but may trim and sit in cash, and won't sell covered calls before earnings in case a big-name CEO hire sparks a rally. Thinks NBIS/CRWV are being punished too much for Nvidia's problems. Avoid SMCI if the new probe implicates current management. Would make AMZN a top-3 to top-5 holding (no founder key-man risk). Likes the NU print.

Page: rows for the 3 new videos are in `data/page_rows_2026-11-14.json` (36 MENTIONS rows, 3 VIDEOS rows) and were added to the Page (UPDATED 2026-11-14 01:45 ET, Read callout refreshed).

## Channel errors
From `data/last_fetch.json` (run 2026-11-14 01:25 ET): 1 of 11 channels logged an error.
- **OptionsWithRyan** 8YeWNhktU1c: no transcript (YouTube blocked the transcript download from the box). It is listed in `needs_pc`, but **Naman's PC was offline tonight, so the PC captions fallback could not run and the video is unrecovered.** It isn't in state.json yet, so the next run needs `--days 2` (or the PC fallback) to pick it up.
- The three videos left unrecovered on Nov 13 (DumbMoneyLive qdyD1nPwIWI, futurenvesting Fi3fMF9Gtqs, StockedUp 9yVzMrwDwAU) are still unrecovered. They weren't retried tonight.
- errors_summary.py printed nothing, so there is no error line for the morning note.

## Code changes
- none
