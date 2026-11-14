#!/usr/bin/env python3
"""One-time backfill of long-form uploads/streams for a single channel.

Reuses fetch.py helpers (ytdlp, transcript fallbacks). Does not touch
data/last_fetch.json or data/prev_fetch.json. Append-only on state.json
for new video ids; existing state rows are left unchanged.

Usage:
  python3 backfill_channel.py --channel joinschoolofgains \\
      --start 2026-10-26 --end 2026-11-10 --no-whisper
"""
import argparse, datetime, json, os, shutil, sys, tempfile, time, glob

import fetch as F

BASE = F.BASE
STATE = F.STATE
SLEEP = F.SLEEP


def load_state():
    return json.load(open(STATE)) if os.path.exists(STATE) else {"processed": {}}


def save_state(state):
    tmp = STATE + ".tmp"
    json.dump(state, open(tmp, "w"), indent=1)
    os.replace(tmp, STATE)


def is_short(m):
    url = m.get("webpage_url") or m.get("url") or ""
    if "/shorts/" in url:
        return True
    # Missing/0 duration is common on flaky stream metadata; do not treat as a Short.
    dur = m.get("duration")
    return isinstance(dur, (int, float)) and 0 < dur <= 180


def is_liveish(m):
    return m.get("live_status") in ("is_live", "is_upcoming")


def is_members_only(m, err=""):
    avail = (m.get("availability") or "").lower()
    title = (m.get("title") or "")
    text = " ".join([avail, title, err or ""])
    if "subscriber_only" in avail or "premium" == avail:
        return True
    if "members only" in text.lower() or "members-only" in text.lower():
        return True
    if "join this channel" in text.lower():
        return True
    return False


def list_tab_ids(ch, tab, n=40):
    out = F.ytdlp(
        ["--flat-playlist", "-I", f"1:{n}", "--print", "%(id)s",
         f"https://www.youtube.com/@{ch}/{tab}"],
        180,
    )
    ids = []
    seen = set()
    for x in out.split():
        if x and x not in seen:
            seen.add(x)
            ids.append(x)
    return ids


def fetch_meta(vid):
    raw = F.ytdlp(["-j", "--skip-download", f"https://www.youtube.com/watch?v={vid}"], 120)
    return json.loads(raw)


def fetch_transcript(vid, url, no_whisper=True, whisper_used=0, whisper_max_sec=1800):
    txt, src = "", None
    err = None
    for att in range(3):
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            t = YouTubeTranscriptApi().fetch(vid, languages=["en"])
            txt = "\n".join(f"[{int(s.start)//60}:{int(s.start)%60:02d}] {s.text}" for s in t)
            src = "yta"
            break
        except Exception as e:
            err = str(e)
            if "429" in err or "Too Many" in err:
                time.sleep(20 * (att + 1))
                continue
            break
    time.sleep(SLEEP)
    if not txt:
        tmp = tempfile.mkdtemp()
        try:
            F.ytdlp(
                ["--write-auto-subs", "--write-subs", "--sub-langs", "en.*,en",
                 "--sub-format", "vtt", "--sleep-subtitles", "5", "--skip-download",
                 "-o", f"{tmp}/%(id)s.%(ext)s", url],
                180,
            )
            vtts = sorted(glob.glob(f"{tmp}/*.vtt"), key=lambda p: ("orig" not in p, p))
            if vtts:
                txt = F.vtt_to_text(vtts[0])
                src = "captions"
        except Exception as e:
            err = str(e)
        shutil.rmtree(tmp, ignore_errors=True)
    if not txt and not no_whisper and whisper_used < 3:
        try:
            txt = F.whisper(vid, whisper_max_sec)
            src = "whisper"
            whisper_used += 1
        except Exception as e:
            err = str(e)
    return txt, src, err, whisper_used


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default="joinschoolofgains")
    ap.add_argument("--start", default="2026-10-26")
    ap.add_argument("--end", default="2026-11-10")
    ap.add_argument("--no-whisper", action="store_true")
    ap.add_argument("--whisper-max-sec", type=int, default=1800)
    ap.add_argument("--list-n", type=int, default=40)
    args = ap.parse_args()

    start = args.start.replace("-", "")
    end = args.end.replace("-", "")
    ch = args.channel
    now = datetime.datetime.now().isoformat(timespec="seconds")

    report = {
        "run": now,
        "channel": ch,
        "start": args.start,
        "end": args.end,
        "found": [],
        "processed": [],
        "skipped": [],
        "errors": [],
        "already_in_state": [],
    }

    # 1) list both tabs
    cands = []
    for tab in ("videos", "streams"):
        try:
            ids = list_tab_ids(ch, tab, args.list_n)
            print(f"{ch} {tab}: {len(ids)} ids", flush=True)
            for vid in ids:
                if vid not in [c[1] for c in cands]:
                    cands.append((tab, vid))
        except Exception as e:
            msg = f"list {tab}: {str(e)[-200:]}"
            report["errors"].append(msg)
            print(msg, flush=True)

    state = load_state()
    whisper_used = 0
    past_cutoff_tabs = set()

    for tab, vid in cands:
        if tab in past_cutoff_tabs:
            continue
        try:
            m = fetch_meta(vid)
        except Exception as e:
            err = str(e)
            reason = "members-only" if is_members_only({}, err) else f"meta: {err[-150:]}"
            rec = {"id": vid, "tab": tab, "reason": reason}
            # If we can't date it, don't assume it's in-window. Still record the error.
            report["errors"].append(f"{vid} {reason}")
            report["skipped"].append(rec)
            print(f"SKIP {vid} {reason}", flush=True)
            continue

        upload = m.get("upload_date") or "0"
        title = m.get("title") or ""
        url = m.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}"
        duration = m.get("duration") or 0
        live_status = m.get("live_status")
        availability = m.get("availability")
        found = {
            "id": vid, "tab": tab, "title": title, "upload_date": upload,
            "duration": duration, "live_status": live_status,
            "availability": availability, "url": url,
        }

        if upload > end:
            # newer than window (shouldn't happen if end is today); keep walking
            report["skipped"].append({**found, "reason": f"after window ({upload})"})
            print(f"SKIP {vid} after window {upload} {title!r}", flush=True)
            continue
        if upload < start:
            # lists are newest-first; older than window ends this tab
            past_cutoff_tabs.add(tab)
            report["skipped"].append({**found, "reason": f"before window ({upload})"})
            print(f"STOP {tab} at {vid} before window {upload} {title!r}", flush=True)
            continue

        report["found"].append(found)

        if is_short(m):
            report["skipped"].append({**found, "reason": "short"})
            # Mark seen so a short isn't retried; skipped flag keeps it out of mentions.
            if vid not in state["processed"]:
                state["processed"][vid] = {
                    "channel": ch, "fetched": now, "analyzed": False,
                    "skipped": True, "note": "backfill: short",
                }
                save_state(state)
            print(f"SKIP {vid} short {title!r}", flush=True)
            continue
        if is_liveish(m):
            report["skipped"].append({**found, "reason": f"live_status={live_status}"})
            print(f"SKIP {vid} live {live_status} {title!r}", flush=True)
            continue
        if is_members_only(m):
            report["skipped"].append({**found, "reason": "members-only"})
            if vid not in state["processed"]:
                state["processed"][vid] = {
                    "channel": ch, "fetched": now, "analyzed": False,
                    "skipped": True, "note": "backfill: members-only",
                }
                save_state(state)
            print(f"SKIP {vid} members-only {title!r}", flush=True)
            continue

        if vid in state["processed"] and not state["processed"][vid].get("skipped") and (
            os.path.exists(os.path.join(BASE, "transcripts", ch, f"{vid}.txt"))
        ):
            # Already fetched; leave the existing state row untouched.
            report["already_in_state"].append(found)
            print(f"ALREADY {vid} {title!r}", flush=True)
            continue

        meta = {k: m.get(k) for k in ("id", "title", "upload_date", "duration", "live_status")}
        meta.update(url=f"https://www.youtube.com/watch?v={vid}", channel=ch)

        txt, src, err, whisper_used = fetch_transcript(
            vid, meta["url"], no_whisper=args.no_whisper,
            whisper_used=whisper_used, whisper_max_sec=args.whisper_max_sec,
        )
        if not txt:
            reason = "members-only" if (err and is_members_only(m, err)) else "no transcript"
            if err and reason != "members-only":
                reason = f"no transcript ({err[-120:]})"
            report["skipped"].append({**found, "reason": reason})
            report["errors"].append(f"{vid} {reason}")
            if vid not in state["processed"]:
                state["processed"][vid] = {
                    "channel": ch, "fetched": now, "analyzed": False,
                    "skipped": True, "note": f"backfill: {reason}",
                }
                save_state(state)
            print(f"SKIP {vid} {reason} {title!r}", flush=True)
            continue

        meta["transcript_source"] = src
        tdir = os.path.join(BASE, "transcripts", ch)
        os.makedirs(tdir, exist_ok=True)
        open(os.path.join(tdir, f"{vid}.txt"), "w").write(txt)
        os.makedirs(os.path.join(BASE, "meta", ch), exist_ok=True)
        json.dump(meta, open(os.path.join(BASE, "meta", ch, f"{vid}.json"), "w"), indent=1)

        # Insert a new row, or clear a prior backfill skip so a successful retry counts as seen.
        prev = state["processed"].get(vid)
        if prev is None or prev.get("skipped"):
            state["processed"][vid] = {"channel": ch, "fetched": now, "analyzed": False}
            save_state(state)

        rec = {**found, "transcript_source": src, "chars": len(txt)}
        report["processed"].append(rec)
        print(f"OK {vid} {upload} {src} {duration}s {title!r}", flush=True)

    outp = os.path.join(BASE, "data", "backfill_sog_fetch.json")
    json.dump(report, open(outp, "w"), indent=1)
    print(
        f"DONE found={len(report['found'])} processed={len(report['processed'])} "
        f"skipped={len(report['skipped'])} errors={len(report['errors'])} -> {outp}",
        flush=True,
    )


if __name__ == "__main__":
    main()
