# Discord posting guardrails

A small system that posts scheduled market updates to a Discord forum thread **only** through one allowlisted script, then checks afterward that nothing else leaked a webhook or posted without a receipt.

Built with the **Manager Bot** and **TradingViewBot** Grok Bot agents under Naman's direction.

The webhook URL is never stored in this repo. Set `NDTL_WEBHOOK_URL` (see `.env.example`). Discord channel and guild IDs in the original working copy were replaced with placeholders.

## What each piece does

### Official poster (`poster/post_webhook.py`)

Posts or edits one UTF-8 Markdown file as a single Discord message in a thread, optionally with a PNG attachment. It can also create a new forum post (`--new-thread`) if the target channel matches `forum_channel_id` in `config.json`.

Safety behavior visible in the code:

- Reads the webhook from `NDTL_WEBHOOK_URL` (or an optional `NDTL_WEBHOOK_FILE`). It never prints the token; receipts and errors go through a redaction helper.
- `--slot NAME` takes an exclusive lock (`O_CREAT|O_EXCL`) so a retry cannot post twice. A slot is released only when nothing was posted (failed pre-check or a clear HTTP error). Unclear failures leave the lock in place.
- A pre-check `GET`s the webhook and refuses to post if it does not point at the thread's parent channel (or the configured forum channel for `--new-thread`).
- `--dry-run` does the locks and receipts under a dry-run directory and sends no POST. `--check-only` is the read-only GET.
- Writes a JSON receipt (status, content SHA-256, message id, thread id) and prints JSON on stdout.

Copy `poster/config.example.json` to `poster/config.json` and fill in your forum channel ID.

### Pipeline (`pipeline/`)

- `prices.py` — Yahoo Finance snapshot versus the week's `levels.json` (last, change, nearest support/resistance, weekly candle).
- `render_update.py` — compares snapshots, classifies each ticker (weak / at a level / triggered / in range), and writes the Markdown update (and a second file if the text would exceed Discord's 2000-character limit). Exit 10 means nothing changed, so the post should be skipped.
- `levels_io.py` — atomic read/write of `levels.json` and a CLI to rebuild it from a plan folder.
- `tv_lease.py` — single-editor lease for TradingView, with heartbeats, expiry, and a verified-takeover path.
- `post_earnings.sh` / `post_earnings.py` — posts an earnings-chart image only after a Manager Bot OK file (SHA-256 of the exact PNG) and a passing claims check.

### Review / guard scripts (`review/`)

- `discord_guard.py` — read-only scan: (C) scripts other than the official poster that mention Discord webhooks or the REST API, (D) files that contain a live webhook URL (reports location and numeric id only, never the token), (A) Discord page visits in a Chrome profile history since `--since`. Exit 0 if clean, 1 if findings.
- `claims_check.py` — recomputes price claims from the raw CSV, searches quoted words in transcripts, and flags unsourced numbers. Used before an earnings chart is allowed to post.
- `receipts_check.py` — matches on-disk receipts to slots, duplicate posts, locks without receipts, and update files with no posted receipt.

`docs/forum_setup_steps.md` explains why the webhook has to point at a **forum** channel. `docs/factcheck.md` and `docs/post_plan.md` are an example fact-check of a streamer's levels (not brokerage account data).

## Tech stack

- Python 3 standard library for the poster and pipeline (`urllib` for Discord HTTPS)
- `pytest` for offline tests (`pipeline/tests/test_pipeline.py`) — no network, no Discord
- Optional matplotlib in `poster/render_update_img.py` for a preview image

## How to run

```bash
cd discord-posting-guardrails
cp .env.example .env          # then set NDTL_WEBHOOK_URL
cp poster/config.example.json poster/config.json

# Offline tests (do not need a webhook)
python3 -m pytest -q pipeline/tests

# Read-only guard scan of this project tree
NDTL_GUARD_ROOTS=. python3 review/discord_guard.py --since '2026-01-01 00:00'

# Dry-run a post (no message is sent)
export NDTL_WEBHOOK_URL  # from .env
python3 poster/post_webhook.py path/to/update.md "$THREAD_URL" --slot 2026-11-14_1300 --dry-run
```

The original working copy also had weekday update slots and a large tree of receipts, locks, and posted screenshots. Those operational files are not included here.


## What was removed and how to run it yourself

**Removed or replaced with placeholders (security / privacy):**
- The live Discord webhook URL (never stored in this repo; originally kept in a secrets file that was not copied).
- Discord guild, forum, channel, webhook, thread, and message IDs.
- Operational receipts, slot locks, snapshots, and the full week `levels.json` files, which contained real thread URLs and box paths.
- Daily update archives except two **examples** under `examples/updates/`, with any IDs redacted.
- Example receipts under `examples/receipts/` use `${DISCORD_THREAD_ID}` / `${DISCORD_MESSAGE_ID}` and relative file paths.

**What you must supply to actually post (optional — tests and dry-run do not need a live webhook):**

1. Create a Discord webhook for a **forum** channel (Server Settings → Integrations → Webhooks). Copy `.env.example` to `.env` and set:

```bash
NDTL_WEBHOOK_URL=https://discord.com/api/webhooks/<id>/<token>
```

   Prefer the environment variable. `NDTL_WEBHOOK_FILE` is an optional path to a file that contains the same URL. Never commit `.env` or that file.

2. Copy `poster/config.example.json` to `poster/config.json` and replace `${DISCORD_GUILD_ID}`, `${DISCORD_FORUM_CHANNEL_ID}`, and `${DISCORD_WEBHOOK_ID}` with your IDs. See `docs/forum_setup_steps.md` for why the webhook must point at a forum channel.

3. Offline tests (no network, no Discord):

```bash
pip install -r requirements.txt
python3 -m pytest -q pipeline/tests
```

4. Dry-run a post (validates locks/receipts and, if a webhook is set, the read-only GET; sends no message):

```bash
python3 poster/post_webhook.py examples/updates/update_1113_2000.md "$THREAD_URL" --slot 2026-11-13_2000 --dry-run
```

Earnings-chart examples (annotated public-company moves, plus a claims-check file) are under `examples/earnings/`. An OK file for `post_earnings.py` must look like `examples/earnings/PLTR-2026-11-02/review_ok/pltr_call_v2.png.ok.example`, with `"reviewer": "Manager Bot"` and the SHA-256 of the exact PNG (`sha256sum <png>`). Raw call transcripts are not included; you would supply those locally if you want to re-run `review/claims_check.py`.
