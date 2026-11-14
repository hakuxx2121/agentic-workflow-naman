# NDTL pipeline (.)

All scripts are stdlib Python 3. Tests are offline: `.venv/bin/python -m pytest -q tests` (no network, no Discord).

| Piece | What it does | Exit codes |
|---|---|---|
| `levels_io.py` | `write_levels(path,data)` validates, writes a temp file in the same dir, fsyncs it, then `os.replace`. `read_levels(path)` checks `schema_version == 1`. CLI: `python3 levels_io.py build ./discord-output/plan_MMDD --week-of YYYY-MM-DD` writes `week_MMDD/levels.json` | 0 ok, 1 usage, traceback on invalid data |
| `week_MMDD/levels.json` | The week's levels: `schema_version, week_of, thread_url, generated_at, tickers[{symbol, levels[{price, role, note}], plan_note}]` | – |
| `prices.py` | Yahoo v8 chart snapshot (same source as the old px scripts) vs the newest `week_*/levels.json`: last, prev close, change %, pre/post price, nearest support/resistance (nearest level below/above, any role), status | 0 ok, 1 levels error, 6 all fetches failed |
| `../poster/post_webhook.py` | Posts or edits one message in a thread (optional `--image` PNG attachment; `--new-thread NAME` with the forum channel URL creates a forum post). Use `--slot` to make the post idempotent. Writes a receipt to `receipts/YYYY-MM-DD/<slot>.json` | 0 ok, 1 failed, 2 content mismatch, 3 duplicate slot, 4 skipped (missing/bad thread URL) |
| `render_update.py` | Takes a price snapshot (prices.py module) on every run and saves it to `snapshots/<date>/<HHMM>.json`. Compares it with the previous snapshot (newest before it, legacy `snapshots/<date>_<HHMM>.json` too), sorts each levels.json ticker into a section, and renders every bullet plus the header and the "Since …" line. The only free text is `--notes notes.json` (`{"FSLY": "sentence"}` → `changed: sentence`). Writes `./discord-output/update_MMDD_HHMM.md` (or `--out`). If it runs over 2000 characters, it also writes `…b.md` for slot `<slot>b`. Prints a summary JSON (`changed_section`, `crossed`, `files`, `slots`) and saves it as `snapshots/<date>/<HHMM>.summary.json`. Flags: `--session --time HHMM --date --levels --notes --out --prev --snapshot --fixture --earnings --force` | 0 rendered, 1 bad input, 6 all fetches failed, **10 no change: no .md written, skip the post** (`--force` renders anyway) |
| `post_earnings.sh` / `.py` | `post_earnings.sh <TICKER> <image.png> <caption.md> <thread_url> <slot> [--dry-run]`. Checks the chart's claims and Manager Bot OK, then runs `post_webhook.py --image --slot` as a subprocess | 20 no OK file, 21 OK sha256/format mismatch, 22 claims missing/not PASS/stale/for another image, 23 bad args; otherwise post_webhook's code |
| `tv_lease.py` | Single-editor lease on TradingView, stored in `locks/tradingview.lease`. Each event is logged to `locks/tradingview.history.jsonl` | 0 ok, 3 held by an active owner, 4 not owner / no lease, 5 expired: needs a verified takeover, 6 takeover screenshot is missing or older than the expiry |

Status rules in prices.py: price is above the highest resistance/trigger level → `above resistance`. Price is below the lowest support/stop level → `below support`. Price is within `--near-pct` (default 1) of any level → `within X% of P (role)`. Anything else → `in range`. A ticker with no levels → `no levels`.

Slot lock rules: a slot is released only when nothing was posted (pre-check failure, or an HTTP error response). After a timeout or other unclear failure, the slot stays locked so a retry can't post twice. Check the receipt and Discord, then delete `slots/<slot>.lock` by hand if the post never went through. `--dry-run` uses `dryrun/slots` and `dryrun/receipts`, so it never blocks a real slot.

## Routine commands
```bash
P=.; OWNER="ndtl-midday"   # one name per routine
# 1. Before TradingView edits
python3 $P/tv_lease.py acquire --owner $OWNER --ttl 900
#   exit 3 -> someone else is editing: wait/retry later, do not touch TradingView
#   exit 5 -> take a 4-pane screenshot of "Jason's picks 1", confirm no edit in progress, then:
#            python3 $P/tv_lease.py acquire --owner $OWNER --ttl 900 --takeover-verified /path/shot.png
# 2. During edits (at least every ttl/2 seconds)
python3 $P/tv_lease.py heartbeat --owner $OWNER
# 3. After edits (also on failure)
python3 $P/tv_lease.py release --owner $OWNER
# Prices
python3 $P/prices.py --session regular  --out $P/snapshots/$(date +%F_%H%M).json   # market hours
python3 $P/prices.py --session extended --out $P/snapshots/$(date +%F_%H%M).json   # pre/after hours
# Post (thread URL from levels.json)
TURL=$(python3 -c "import json,glob;print(json.load(open(sorted(glob.glob('$P/week_*/levels.json'))[-1]))['thread_url'] or '')")
python3 ../poster/post_webhook.py ./discord-output/update_MMDD_HHMM.md "$TURL" --slot $(date +%F_%H%M)
# image attachment (multipart, caption = .md text) into an existing thread:
python3 ../poster/post_webhook.py caption.md "$TURL" --slot NAME --image chart.png
# new forum post (thread) in #trade-plans; prints/records thread_url:
python3 ../poster/post_webhook.py caption.md https://discord.com/channels/${DISCORD_GUILD_ID}/${DISCORD_FORUM_CHANNEL_ID} --slot NAME --image chart.png --new-thread "Thread name"
#   0 posted | 2 posted but content differs -> --edit <message_id> | 3 already posted for this slot: STOP | 4 no thread URL: STOP and report
```
New week: `python3 $P/levels_io.py build ./discord-output/plan_MMDD --week-of YYYY-MM-DD` (Monday's date).

## render_update.py classifier
The session price is the extended price with `--session extended` (pre-market or after hours), otherwise the regular price. Tolerances (constants in render_update.py):
- `BREAK_TOL = 0.25%`: a support or stop level S is broken when price < S × (1 − 0.0025). A resistance or trigger level R is cleared when price > R × (1 + 0.0025).
- `AT_TOL = 0.50%`: price is at level L when |price / L − 1| ≤ 0.005.

The first match wins:
1. **Weak**: price is under any support or stop by more than BREAK_TOL. This covers losing a support it was above and sitting under its nearest support. Being near a lower level doesn't move it to At a level (FSLY 17.61 after hours, under 19 with 16–15 below → Weak).
2. **At a level**: within AT_TOL of any level.
3. **Triggered / working**: clears any resistance or trigger level by more than BREAK_TOL.
4. **In range / no change**: everything else, plus tickers with no levels.

A crossing means a level lies between the previous and current snapshot prices. Empty sections are left out. Bullets follow one fixed format:
- Regular: `• **SYM** price (±x.x%): [changed: note; ]level text[; earnings]`
- Extended: `• **SYM** price (close, ±x.x% after hours): …`

Earnings text comes from `./discord-output/earnings_calendar.md`, counted against `--date`, within 7 days. It's spelled out ("before the open" / "after the close") and includes the gap for reports this week.

Routine use: `python3 $P/render_update.py --session regular --time 1300 [--notes notes.json]`. Exit 10 means no post. On 0, post each file in `files` with the matching name in `slots`.

## Manager Bot OK file (post_earnings)
`${NDTL_EARNINGS_ROOT}/<TICKER>-<YYYY-MM-DD>/review_ok/<image basename>.ok`, JSON:
```json
{"image": "anet_call_v2.png", "sha256": "<sha256 of the exact PNG bytes>", "reviewer": "Manager Bot", "reviewed_at": "2026-11-04T21:30:00-05:00"}
```
Get the hash with `sha256sum <png>`. A re-rendered image (v3) never matches a v2 OK file. The claims check passes only when all of these hold:
- `claims.json` `"output"` equals the image basename.
- The first line of `claims_check.md` names that basename.
- `claims_check.md` contains `Result: **PASS**` (or `RESULT: PASS`) and has no `- FAIL` line.
- `claims_check.md` is not older than `claims.json`.

## Forum posts (--new-thread)
`poster/config.example.json (copy to config.json)` (not secret) holds `forum_channel_id`; `--new-thread` refuses any other channel. With `--dry-run`, `--new-thread` runs everything plus the read-only webhook GET (webhook channel must equal the forum channel) and sends no POST. A webhook can't tell a forum from a text channel, so a warning is recorded until `forum_type_confirmed` is true. Setup steps are in `../docs/forum_setup_steps.md`.

## Weekly candle (Naman's rule)
`prices.py` adds `"week"` to each row. It fetches Yahoo v8 `interval=1d&range=1mo` with the same request style as the 1-minute fetch. The fields are:
- `week_open`: the first regular-session open on or after Monday of the `--asof` week (ET).
- `week_high` / `week_low`: the daily bars this week plus the session price.
- `week_pct`: session price vs. week open.
- `color`: green, red or flat.

If the weekly fetch fails, the row gets `{"error": ...}` and the run continues. `render_update.py` passes `--asof <date>` and ends each bullet with `. Green wk +7.8%.` / `. Red wk −2.1%.`; it leaves this out when the fetch failed. In fixtures, the key `"SYM@1d"` holds the daily chart.
