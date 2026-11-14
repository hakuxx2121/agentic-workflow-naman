#!/usr/bin/env python3
"""Fetch new videos + transcripts for tracked channels.
Usage: python3 fetch.py [--days 7] [--max 5] [--no-whisper]
Writes transcripts/<channel>/<id>.txt, meta/<channel>/<id>.json, updates state.json,
and writes data/last_fetch.json listing what was newly fetched (and failures)."""
import time, json, os, re, subprocess, sys, glob, datetime, argparse, tempfile, shutil
BASE = os.path.dirname(os.path.abspath(__file__))
CHANNELS = ["StockedUp","ThePlainBagel","DumbMoneyLive","futurenvesting","StockswithJosh",
            "TradeBrigade","JosephCarlsonAfterHours","OptionsWithRyan","wickedstocksofficial","amitinvesting",
            "joinschoolofgains"]  # Paper Gains, now branded School of Gains
CLIENTS = [None, "tv", "ios", "web_safari", "mweb", "android"]
SLEEP = 3
STATE = os.path.join(BASE, "state.json")

def ytdlp(args, timeout=300):
    last = None
    for c in CLIENTS:
        cmd = ["yt-dlp", "--no-warnings", "--ignore-no-formats-error"] + (["--extractor-args", f"youtube:player_client={c}"] if c else []) + args
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            last = "timeout"; continue
        if r.returncode == 0: time.sleep(SLEEP); return r.stdout
        last = r.stderr[-400:]
        if "429" in last:
            time.sleep(30); continue
        if "Sign in to confirm" not in last and "bot" not in last.lower(): break
    raise RuntimeError(last)

def vtt_to_text(path):
    out, prev = [], None
    for line in open(path, encoding="utf-8", errors="ignore"):
        line = line.strip()
        m = re.match(r"(\d\d):(\d\d):(\d\d)\.\d+ -->", line)
        if m:
            ts = int(m[1])*3600+int(m[2])*60+int(m[3]); continue
        if not line or line.startswith(("WEBVTT","Kind:","Language:","NOTE")) or "-->" in line: continue
        line = re.sub(r"<[^>]+>", "", line).strip()
        if line and line != prev and (not out or line not in out[-1]):
            out.append(f"[{ts//60}:{ts%60:02d}] {line}"); prev = line
    return "\n".join(out)

def whisper(vid, maxsec):
    from faster_whisper import WhisperModel
    tmp = tempfile.mkdtemp()
    ytdlp(["-f", "bestaudio", "--download-sections", f"*0-{maxsec}", "-x", "--audio-format", "mp3",
           "-o", f"{tmp}/a.%(ext)s", f"https://www.youtube.com/watch?v={vid}"], timeout=900)
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segs, _ = model.transcribe(glob.glob(f"{tmp}/a.*")[0], language="en")
    txt = "\n".join(f"[{int(s.start)//60}:{int(s.start)%60:02d}] {s.text.strip()}" for s in segs)
    shutil.rmtree(tmp); return txt

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--days", type=int, default=None)
    ap.add_argument("--max", type=int, default=1); ap.add_argument("--no-whisper", action="store_true")
    ap.add_argument("--whisper-max-sec", type=int, default=1800); ap.add_argument("--channels", nargs="*")
    a = ap.parse_args()
    state = json.load(open(STATE)) if os.path.exists(STATE) else {"processed": {}}
    known_channels = {v.get("channel") for v in state.get("processed", {}).values()}
    # Default: only videos uploaded since the previous run (newest first, no backfill).
    # --days N overrides with a fixed lookback window.
    lf = os.path.join(BASE, "data", "last_fetch.json")
    if a.days is None and os.path.exists(lf):
        last = datetime.date.fromisoformat(json.load(open(lf))["run"][:10])
        cutoff = last.strftime("%Y%m%d")  # upload_date is day-granular, so include the last run's day
    else:
        cutoff = (datetime.date.today() - datetime.timedelta(days=a.days or 7)).strftime("%Y%m%d")
    report = {"run": datetime.datetime.now().isoformat(timespec="seconds"), "new": [], "channels": {}, "needs_pc": []}
    whisper_used = 0
    for ch in a.channels or CHANNELS:
        info = {"new": 0, "errors": []}
        first_run = ch not in known_channels
        if first_run:
            info["first_run"] = True
        ch_cutoff = "00000000" if first_run else cutoff
        ch_max = 1 if first_run else a.max
        cands = []
        for tab in ("videos", "streams"):
            try:
                out = ytdlp(["--flat-playlist", "-I", "1:10", "--print", "%(id)s", f"https://www.youtube.com/@{ch}/{tab}"], 120)
                cands += [(tab, x) for x in out.split() if x not in [c[1] for c in cands]]
            except Exception as e:
                if tab == "videos": info["errors"].append(f"list {tab}: {str(e)[-150:]}")
        # First pass for a brand-new channel: take only its single newest eligible
        # long-form video across both tabs, even if it is older than the since-last-run cutoff.
        # Do not use videos-tab order alone; some channels (e.g. joinschoolofgains) post
        # newer finished streams than their latest videos-tab upload.
        if first_run and cands:
            newest_on_tab = {}
            for tab, vid in cands:
                if tab in newest_on_tab:
                    continue
                try:
                    m = json.loads(ytdlp(["-j", "--skip-download", f"https://www.youtube.com/watch?v={vid}"], 120))
                except Exception as e:
                    info["errors"].append(f"{vid} meta: {str(e)[-150:]}"); continue
                if (m.get("duration") or 0) <= 180 or "/shorts/" in (m.get("webpage_url") or ""):
                    continue
                if m.get("live_status") in ("is_live", "is_upcoming"):
                    continue
                newest_on_tab[tab] = (m.get("upload_date") or "0", tab, vid)
                if len(newest_on_tab) >= 2:
                    break
            cands = [max(newest_on_tab.values())[1:]] if newest_on_tab else []
        got = 0
        stopped = set()  # tabs where we hit an already-seen or too-old video (lists are newest-first)
        for tab, vid in cands:
            if got >= ch_max: break
            if tab in stopped: continue
            if vid in state["processed"]: stopped.add(tab); continue  # reached already-seen videos in this tab: no backfill
            try:
                m = json.loads(ytdlp(["-j", "--skip-download", f"https://www.youtube.com/watch?v={vid}"], 120))
            except Exception as e:
                info["errors"].append(f"{vid} meta: {str(e)[-150:]}"); continue
            if (m.get("upload_date") or "0") < ch_cutoff: stopped.add(tab); continue  # older than window
            if (m.get("duration") or 0) <= 180 or "/shorts/" in (m.get("webpage_url") or ""): continue
            if m.get("live_status") in ("is_live", "is_upcoming"): continue
            meta = {k: m.get(k) for k in ("id","title","upload_date","duration","live_status")}
            meta.update(url=f"https://www.youtube.com/watch?v={vid}", channel=ch)
            tdir = os.path.join(BASE, "transcripts", ch); os.makedirs(tdir, exist_ok=True)
            txt = ""; src = None
            pc = sorted(glob.glob(os.path.join(BASE, "data", "pc_subs", f"{vid}*.vtt")))
            if pc:  # captions pulled through Naman's PC when the box is blocked
                txt = vtt_to_text(pc[0]); src = "pc_captions"
            for att in range(0 if txt else 3):
                try:
                    from youtube_transcript_api import YouTubeTranscriptApi
                    t = YouTubeTranscriptApi().fetch(vid, languages=["en"])
                    txt = "\n".join(f"[{int(s.start)//60}:{int(s.start)%60:02d}] {s.text}" for s in t); src = "yta"; break
                except Exception as e:
                    if "429" in str(e) or "Too Many" in str(e): time.sleep(20*(att+1)); continue
                    break
            if src != "pc_captions": time.sleep(SLEEP)
            tmp = tempfile.mkdtemp()
            if not txt:
              try:
                ytdlp(["--write-auto-subs", "--write-subs", "--sub-langs", "en.*,en", "--sub-format", "vtt", "--sleep-subtitles", "5",
                       "--skip-download", "-o", f"{tmp}/%(id)s.%(ext)s", meta["url"]], 180)
                vtts = sorted(glob.glob(f"{tmp}/*.vtt"), key=lambda p: ("orig" not in p, p))
                if vtts: txt = vtt_to_text(vtts[0]); src = "captions"
              except Exception as e:
                info["errors"].append(f"{vid} subs: {str(e)[-150:]}")
            shutil.rmtree(tmp, ignore_errors=True)
            if not txt and not a.no_whisper and whisper_used < 3:
                try: txt = whisper(vid, a.whisper_max_sec); src = "whisper"; whisper_used += 1
                except Exception as e: info["errors"].append(f"{vid} whisper: {str(e)[-150:]}")
            if not txt:
                info["errors"].append(f"{vid} no transcript")
                report["needs_pc"].append(vid); continue
            meta["transcript_source"] = src
            open(os.path.join(tdir, f"{vid}.txt"), "w").write(txt)
            os.makedirs(os.path.join(BASE, "meta", ch), exist_ok=True)
            json.dump(meta, open(os.path.join(BASE, "meta", ch, f"{vid}.json"), "w"), indent=1)
            state["processed"][vid] = {"channel": ch, "fetched": report["run"], "analyzed": False}
            report["new"].append(meta); got += 1; info["new"] += 1
            json.dump(state, open(STATE, "w"), indent=1)
        report["channels"][ch] = info
        print(ch, info, flush=True)
    json.dump(state, open(STATE, "w"), indent=1)
    if os.path.exists(lf):  # keep the previous night's results for errors_summary.py
        shutil.copyfile(lf, os.path.join(BASE, "data", "prev_fetch.json"))
    json.dump(report, open(lf, "w"), indent=1)

if __name__ == "__main__": main()
