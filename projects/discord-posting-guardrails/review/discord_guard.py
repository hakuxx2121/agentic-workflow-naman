#!/usr/bin/env python3
"""Discord guard for Manager Bot's daily review. Read-only. Never prints a webhook token.
Usage: discord_guard.py [--since 'YYYY-MM-DD HH:MM'] [--json out.json]
Checks:
  C  scripts (other than the official poster) that reference discord(app).com/api/webhooks or the Discord REST API
  D  any readable file containing a LIVE webhook URL (id + token) -> location + numeric id only
  A  browser history: discord.com page visits since --since in every box Chrome profile (send must be judged by context)
Exit 0 clean, 1 findings."""
import argparse, datetime as dt, json, os, re, shutil, sqlite3, sys, tempfile
OFFICIAL = {os.environ.get("NDTL_POST_WEBHOOK", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "poster", "post_webhook.py")))}
SECRET_OK = {os.environ.get("NDTL_WEBHOOK_FILE", "")}
ROOTS = os.environ.get("NDTL_GUARD_ROOTS", os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))).split(":")
SKIP_DIRS = re.compile(r"/(\.git|node_modules|\.venv|__pycache__|\.gradle|Cache|Code Cache|GPUCache|Service Worker|\.cache|build|frames|videos?|footage|chrome-profile)(/|$)")
WH = re.compile(rb"discord(?:app)?\.com/api/(?:v\d+/)?webhooks/(\d{15,22})(?:/([A-Za-z0-9_\-]{20,}))?")
API = re.compile(rb"discord(?:app)?\.com/api/v\d+/(channels|guilds|users)|Authorization['\"]?\s*[:=]\s*['\"]?Bot\s")
SCRIPT_EXT = (".py", ".sh", ".js", ".ts", ".mjs", ".rb", ".pl", ".bash")
MAXSZ = 60_000_000

def scan(since):
    c_hits, d_hits = [], []
    for root in ROOTS:
        for dp, dns, fns in os.walk(root):
            if SKIP_DIRS.search(dp + "/"): dns[:] = []; continue
            for fn in fns:
                p = os.path.join(dp, fn)
                try:
                    st = os.stat(p)
                    if not os.path.isfile(p) or st.st_size > MAXSZ: continue
                    with open(p, "rb") as f: b = f.read()
                except Exception: continue
                ws = WH.findall(b); api = API.search(b)
                if not ws and not api: continue
                is_script = fn.endswith(SCRIPT_EXT)
                is_test = "/tests/" in p or fn.startswith("test_")
                if is_script and p not in OFFICIAL:
                    c_hits.append({"file": p, "webhook_ids": sorted({w[0].decode() for w in ws}), "rest_api": bool(api), "test": is_test})
                live = sorted({w[0].decode() for w in ws if w[1]})
                if live and p not in SECRET_OK:
                    d_hits.append({"file": p, "webhook_ids": live, "mtime": dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"), "test": is_test})
    return c_hits, d_hits

def history(since):
    out = []; epoch = dt.datetime(1601, 1, 1)
    cutoff = int((since.astimezone(dt.timezone.utc).replace(tzinfo=None) - epoch).total_seconds() * 1e6)
    base = os.environ.get("NDTL_CHROME_PROFILE", "")
    for prof in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        h = os.path.join(base, prof, "Default", "History")
        if not os.path.exists(h): continue
        tmp = tempfile.mktemp(suffix=".db"); shutil.copy(h, tmp)
        try:
            con = sqlite3.connect(tmp)
            rows = con.execute("select v.visit_time,u.url,u.title from visits v join urls u on u.id=v.url where u.url like '%discord%' and v.visit_time>? order by v.visit_time", (cutoff,)).fetchall()
            for t, url, title in rows:
                ts = (epoch + dt.timedelta(microseconds=t)).replace(tzinfo=dt.timezone.utc).astimezone()
                url = re.sub(r"(webhooks/\d+/)[\w\-]+", r"\1<redacted>", url)
                out.append({"profile": prof, "time": ts.strftime("%Y-%m-%d %H:%M:%S %Z"), "url": url[:160], "title": (title or "")[:80]})
        finally:
            os.remove(tmp)
    return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--since", default=None); ap.add_argument("--json")
    a = ap.parse_args()
    since = dt.datetime.strptime(a.since, "%Y-%m-%d %H:%M").astimezone() if a.since else dt.datetime.now().astimezone() - dt.timedelta(hours=24)
    c, d = scan(since); hv = history(since)
    res = {"since": since.isoformat(timespec="minutes"), "C_scripts": c, "D_live_webhook_urls": d, "A_browser_discord_visits": hv}
    print(json.dumps(res, indent=1))
    if a.json: json.dump(res, open(a.json, "w"), indent=1)
    bad = [x for x in c if not x["test"]] or d
    sys.exit(1 if bad or hv else 0)
