# Trading YouTube Ticker Tracker

Tracks which stocks, ETFs and crypto tickers a set of trading YouTube channels discuss, what they think of each one, and any price levels they give. Results go to the **Trading YouTube Ticker Tracker** Page; its id is saved in `data/canvas.json`.

## Scope rule: latest videos only
- Only watch each channel's **latest** long-form videos. Shorts and currently-live or upcoming streams are skipped. Finished streams (`was_live`) are kept.
- **Nightly:** process only videos uploaded since the previous run (the date in `data/last_fetch.json`), newest first. Never backfill older videos. By default `fetch.py` takes `--max 1` per channel and stops at the first video it has already seen or that falls before the cutoff.
- **New channel first run:** if a channel in `CHANNELS` has no entries in `state.json`, ignore the since-last-run cutoff and process only its single newest eligible long-form video (videos and streams tabs compared by `upload_date`). No backfill. Later nights use the normal cutoff.
- The first pass took one video per channel (`--days 7 --max 1`). Older StockedUp/ThePlainBagel videos fetched earlier are marked `"skipped": true` in `state.json`. They are never analyzed or re-fetched, and they stay out of mentions and the Page.

## Nightly procedure
1. **Fetch:** `python3 fetch.py --no-whisper > fetch.log 2>&1`
   (run it in the background; it sleeps between requests. To force a window, use `--days N`; for more videos per channel, use `--max N`; to limit channels, use `--channels A B`.)
2. **Analyze:** `python3 analyze.py --pending` lists new video ids. For each one, read the transcript (`python3 compact.py <id>` prints it in 1-minute chunks) and write `analysis/<id>.json`: a list of
   `{"ticker","sentiment": bullish|bearish|neutral|mixed,"price_talk","summary","t": seconds}`.
   Then run `python3 analyze.py`. It rebuilds `data/mentions.json` and sets `analyzed: true` in `state.json`.
3. **Update the Page:** read `data/canvas.json` and edit that same Page by its `canvas_id` (ReadCanvas, then EditCanvas or WriteCanvas with that id). Swap in the new embedded data. Never create a new Page.
4. **Report:** run `python3 errors_summary.py`; if it prints a line, use it as the morning note's error line (no output means no error line). Then write `reports/YYYY-MM-DD.md` with the top ~5 tickers by mention count over the last 7 days, giving consensus sentiment and one line each. Include a `## Code changes` section: if `reports/pending_code_changes.md` exists, copy its bullets into that section and then delete the pending file so they are not repeated the next night. If the file is missing, write `- none` (or describe any changes made during the run).

## Summaries: own words only
Summaries and price talk must be paraphrased. Never copy transcript passages; a few words at most.

## Adding or removing a channel
Edit the `CHANNELS` list near the top of `fetch.py`. Use YouTube handles without the `@`. A new channel gets only its latest eligible long-form video on the next run (first-run handling in `fetch.py` ignores the since-last-run cutoff and compares the newest videos-tab and streams-tab uploads so a newer finished stream is not missed). Do not backfill older videos. Record the change in `reports/pending_code_changes.md` so the next nightly report's Code changes section picks it up.

Tracked handles: StockedUp, ThePlainBagel, DumbMoneyLive, futurenvesting, StockswithJosh, TradeBrigade, JosephCarlsonAfterHours, OptionsWithRyan, wickedstocksofficial, amitinvesting, and joinschoolofgains (Paper Gains, now branded School of Gains; https://www.youtube.com/@joinschoolofgains).

## File layout
- `fetch.py`: fetches the video list and metadata (yt-dlp), then the transcript (youtube_transcript_api first, then yt-dlp captions, then optional faster_whisper).
- `backfill_channel.py`: one-time (re-runnable) single-channel date-window backfill that reuses fetch.py helpers; does not write last_fetch.json. Used for the Nov 10 School of Gains backfill.
- `compact.py`: prints a transcript in 1-minute chunks for reading.
- `analyze.py`: merges `analysis/*.json` into `data/mentions.json` and updates `state.json`.
- `transcripts/<channel>/<id>.txt`, `meta/<channel>/<id>.json`: raw inputs.
- `analysis/<id>.json`: per-video extraction. `analysis/skipped/` holds set-aside work for older videos.
- `state.json`: one entry per seen video: `{channel, fetched, analyzed, skipped?}`.
- `errors_summary.py`: prints the morning note's error line, or nothing. It speaks up only when more than half of `CHANNELS` errored or a channel errored that didn't the night before. Members-only and no-transcript skips alone don't count. The previous night comes from `data/prev_fetch.json` (fetch.py copies the old `last_fetch.json` there before overwriting it), falling back to the previous report's `## Channel errors` section.
- `data/last_fetch.json`: the last run's time, new videos and per-channel errors. Its `run` date is the since-last-run cutoff.
- `data/mentions.json`: one record per video × ticker.
- `data/canvas.json`: the Page id and url.
- `reports/YYYY-MM-DD.md`: nightly top-tickers note.
- `reports/pending_code_changes.md`: bullets to copy into the next report's `## Code changes` section, then delete.

## Known issues
- **HTTP 429 on subtitles:** YouTube rate-limits yt-dlp caption downloads. The fetch now tries youtube_transcript_api first, backs off 20/40/60s on 429s, sleeps 3s after each yt-dlp call, and waits 30s and retries on a 429.
- **"The page needs to be reloaded" / "Requested format is not available":** some videos' metadata fails intermittently. They are logged in `last_fetch.json` errors and skipped. Since 2026-11-04, every yt-dlp call (list, metadata, subtitles, whisper audio, all client rotations) passes `--ignore-no-formats-error` through the shared `ytdlp()` helper, so a "format not available" error no longer fails metadata or caption requests.
- **Bot checks ("Sign in to confirm"):** fetch.py rotates yt-dlp player clients (tv, ios, web_safari, mweb, android).
- **faster_whisper** is installed but slow on CPU. Nightly runs use `--no-whisper`; drop that flag for a channel with no captions (max 3 whisper jobs per run).
- Keep yt-dlp current: `pip install -U --break-system-packages yt-dlp youtube_transcript_api`.
- Only one fetch should run at a time; concurrent runs overwrite `state.json`.
- **Analysis is agent-driven:** `analyze.py` only merges results. Reading transcripts and writing `analysis/<id>.json` needs the nightly agent. Very long streams (DumbMoneyLive, amitinvesting run 1.5-5 hours) are handled by grepping for tickers and company names and reading those chunks.
- **Latest video can be missed:** if the newest video's metadata or transcript fails, fetch.py takes the next newest one instead (on the first pass, futurenvesting's two newest videos had no transcript). Check `last_fetch.json` errors.
- **Page data:** the Page embeds `MENTIONS`, `VIDEOS` and `UPDATED`. Regenerate them from `data/mentions.json` and `state.json`, leaving out skipped videos.

## PC captions fallback (added Nov 12)
When YouTube blocks transcript downloads from the environment that runs `fetch.py`, the script lists the affected video ids in `data/last_fetch.json` under `needs_pc`. You can then fetch captions on another machine that YouTube is less likely to block (for example a personal Windows PC, inside WSL, with a standalone `yt-dlp`):

```bash
wsl -e bash -lc 'cd ~/yt-subs && ~/bin/yt-dlp --skip-download --write-auto-subs --write-subs --sub-langs en --sub-format vtt -o VIDEOID https://www.youtube.com/watch?v=VIDEOID'
```

(PowerShell as the outer shell: no `\"` escapes, and no parentheses inside the single-quoted bash string.) Stage the `.vtt` files into a folder your copy tool can see, then place each `VIDEOID.en.vtt` in `data/pc_subs/` and rerun `fetch.py` with the same `--days` window and `--channels` limited to the affected ones. `fetch.py` uses any `data/pc_subs/<id>*.vtt` first (transcript_source `pc_captions`). Delete used files from `data/pc_subs/` after analysis.


## Tech stack

- Python 3 (`fetch.py`, `analyze.py`, `compact.py`, `backfill_channel.py`, `errors_summary.py`, `gen_page_data.py`)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) for video lists, metadata, and captions
- `youtube_transcript_api` (tried first for transcripts)
- Optional `faster_whisper` when captions are missing (`--no-whisper` skips it; nightly runs use that flag)

```bash
pip install -U yt-dlp youtube_transcript_api
# optional, only if you want local transcription:
# pip install faster-whisper
python3 fetch.py --no-whisper
```

Raw transcripts, `analysis/` JSON, `data/` mention dumps, and run logs are omitted from this copy.


## What was removed and how to run it yourself

**Removed (size / privacy):**
- Raw transcripts (`transcripts/`), per-video `analysis/` JSON, and the full `data/mentions.json` history.
- Operational files: `state.json`, fetch logs, and a Cursor Page identifier (`data/canvas.json`).
- Personal machine identifiers and Windows account paths that had appeared in the captions-fallback notes (the steps themselves are kept, with generic paths).

**Included instead:** `examples/sample-mentions.json`, `examples/sample-scores.json`, and `examples/sample-nightly-report.md` (a real nightly note, with no secrets).

There is no API key to configure. The fetcher uses yt-dlp and `youtube_transcript_api` against public YouTube pages (YouTube may still rate-limit or block datacenter IPs; the README's PC captions fallback covers that).

```bash
pip install -r requirements.txt
# optional, only if a video has no captions and you want local transcription:
# pip install faster-whisper

python3 fetch.py --no-whisper
# Then, for each pending video id, read the transcript (python3 compact.py <id>)
# and write analysis/<id>.json. After that:
python3 analyze.py
```

Copy `examples/sample-mentions.json` to `data/mentions.json` if you only want to inspect the schema or feed the dashboard sample. Do not commit raw transcripts or a full production dump if they are large or contain quoted speech you would rather not publish.
