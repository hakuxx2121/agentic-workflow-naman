# NDTL Gains v2.1

A TradingView **Pine Script** indicator for day-trading levels. It draws the same opening range, premarket high/low, gap line, prior highs/lows, moving averages, premarket Fibonacci levels, and multi-timeframe continuity (MTFC) table on any chart timeframe. Version 2.1 works on regular-hours-only charts as well as extended-hours charts: data requests read the extended-hours feed in the background so premarket levels match.

Built with the **NDTL - Gains** Grok Bot agent, under Naman's direction. Published on TradingView as a private script (Gains v2 / v2.1).

This is a charting tool. It does not place trades.

## What it plots

- **Moving averages:** daily 20 / 50 / 200 and weekly 50 / 200 SMAs, with optional name tags. (A green/red fill between the 20-day and 50-day SMAs was removed in v2.1; the lines themselves stay.)
- **Key levels:** previous day, week, month, and quarter highs and lows; premarket high/low (4:00–9:30 AM ET); ADR / AWR bands.
- **Opening range:** three methods. The default is **Opening impulse** (fit to Paper Prophet): each side follows the high or low from 9:30 and locks after 4 quiet minutes, never before 9:37. Alternatives are a time window and a confirmed-swing lock. Optional snap-back is off by default.
- **Gap line:** the 7:57 PM 3-minute candle's high on a gap up, or its low on a gap down.
- **Premarket Fibonacci:** from the first premarket extreme to the second, with 0.5 / 0.618 / 0.65 levels and 1.5 / 1.618 / 1.65 extensions, color-filled between 0.5–0.618 and 0.618–0.65 (and mirrored on the extensions). Levels reset each day.
- **MTFC bar:** direction of the 15m, 1h, 4h, daily, and weekly candles, each with its Strat type (1 / 2u / 2d / 3), plus optional candle outlines and alerts when they align. Hidden on daily and higher timeframes by default (toggle in settings).
- **Display helpers:** confluence zones, proximity highlight, broken/held styling, far-level hiding, nearest-only labels, support/resistance colors, and opening-range retest alerts.

**Extend lines through after-hours and premarket** (on by default) keeps the opening range, premarket high/low, gap line, and premarket fib on the chart until the next day's levels replace them. Off, they stop at 4:00 PM ET.

## Tech stack

- Pine Script v6 (`ndtl-gains-v2.1.pine`, also the prior `ndtl-gains-v2.pine`)
- Python helpers for research and fitting: `fit_or.py`, `build_jason_picks.py`, `common.py`, `pm-fib/pm_fib_reference.py` (pandas, numpy, yfinance)

## How to use the indicator

1. In TradingView, open the Pine Editor and paste `ndtl-gains-v2.1.pine`, or add the script you published.
2. Add it to a chart. If you already had an earlier build, open Settings → Defaults → Reset settings, because inputs were added and removed.
3. Use the setting groups (General, Moving averages, Key levels, Opening range, and so on) to turn pieces on or off.

The indicator does not need API keys.

## Helper scripts

These were used to fit the opening-range logic and premarket fibs against measured levels. They are optional.

```bash
pip install pandas numpy yfinance
python3 fit_or.py --help
```

`or-gap-analysis.md` and `or-gap-review.md` record that fitting work. Publish notes are in `publish_description.txt`, `publish_release_notes.txt`, and `release_notes_mtfc.txt`.

Example chart and settings screenshots are in `docs/screenshots/`. Educational opening-range visuals (and the Python that renders them) are in `docs/orb/`.


## What was removed and how to run it yourself

The Pine Script source (`ndtl-gains-v2.1.pine` and the prior `ndtl-gains-v2.pine`) is included in full.

**Removed (privacy / size, not secrets):**
- Large 1-minute price CSV dumps used only to fit the opening-range logic (`data/` in the original working copy).
- Some TradingView screenshots that showed a personal watchlist on the side of the chart. The screenshots under `docs/screenshots/` were checked and do not include holdings, account balances, or tokens. One publish-page screenshot includes the public TradingView handle that matches this portfolio.
- Git history from the working copy.

**No API keys or accounts are required to use the indicator.**

To run it:
1. In TradingView, open the Pine Editor, paste `ndtl-gains-v2.1.pine`, and add it to a chart.
2. If you already had an earlier build, use Settings → Defaults → Reset settings.

Optional research helpers (`fit_or.py`, `build_jason_picks.py`, `pm-fib/pm_fib_reference.py`) need daily/intraday bars:

```bash
pip install -r requirements.txt
# point the scripts at your own CSVs or let them pull from Yahoo via yfinance
python3 fit_or.py --help
```

The ORB educational PNGs can be regenerated with the scripts in `docs/orb/` (they need whatever Python packages those scripts import, typically matplotlib).
