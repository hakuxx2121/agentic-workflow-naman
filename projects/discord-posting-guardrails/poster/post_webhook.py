#!/usr/bin/env python3
"""Post a UTF-8 text file as ONE message into a Discord thread via Naman's NDTL webhook.
Usage: post_webhook.py <file.md> <thread_url> [--edit <message_id>] [--slot <name>] [--image <file.png>] [--new-thread <name>] [--dry-run | --check-only]
Prints a JSON result. With --edit <message_id> edits that webhook message in place instead.
--slot NAME  REQUIRED for every new post; claim ${NDTL_PIPELINE_ROOT}/slots/NAME.lock (O_CREAT|O_EXCL) first; if taken, exit 3, post nothing.
--dry-run    do everything except HTTP (locks/receipts go under ${NDTL_PIPELINE_ROOT}/dryrun/).
--check-only only the read-only pre-check (GET webhook, compare channel_id with the thread's parent).
             Claims no slot, posts nothing; receipt (check_ok/check_failed) goes under ${NDTL_PIPELINE_ROOT}/check/.
--image PATH  send as multipart/form-data (payload_json + files[0]); .md text is the caption; receipt records name/size/sha256.
--new-thread NAME  pass the FORUM channel URL https://discord.com/channels/<guild>/<forum> instead of a thread URL;
             creates a forum post (thread_name) whose starter is this message; prints/records the new thread URL.
             The forum channel must equal forum_channel_id in the non-secret config (${NDTL_DISCORD_CONFIG} (defaults to ./config.json),
             override with env NDTL_DISCORD_CONFIG) when that key is set; otherwise exit 1 before anything else.
--new-thread with --dry-run validates everything (file, image, name, URL, config, slot) and runs the read-only
             webhook GET pre-check (channel_id must equal the forum channel), but sends NO POST. A webhook GET cannot
             tell a forum from a text channel; while config forum_type_confirmed is not true a warning is recorded.
Every attempt writes a receipt to <root>/receipts/YYYY-MM-DD/<slot or timestamp>.json.
Exit: 0 ok, 1 failed (pre-check/HTTP/other), 2 content mismatch, 3 duplicate slot, 4 skipped (bad/missing thread URL)."""
import datetime as dt, hashlib, json, os, re, sys, tempfile, urllib.error, urllib.request

ROOT = os.environ.get("NDTL_PIPELINE_ROOT", "${NDTL_PIPELINE_ROOT}")
SECRET = os.environ.get("NDTL_WEBHOOK_FILE", "")  # optional file; prefer NDTL_WEBHOOK_URL
CONFIG = os.environ.get("NDTL_DISCORD_CONFIG", "${NDTL_DISCORD_CONFIG} (defaults to ./config.json)")
UA = "NDTL-webhook (python)"
THREAD_RE = re.compile(r"^https://(?:\w+\.)?discord(?:app)?\.com/channels/(\d{15,})/(\d{15,})/threads/(\d{15,})/?$")
CHANNEL_RE = re.compile(r"^https://(?:\w+\.)?discord(?:app)?\.com/channels/(\d{15,})/(\d{15,})/?$")
_SECRETS = []

def redact(s):
    s = str(s)
    for x in _SECRETS:
        if x: s = s.replace(x, "<redacted>")
    s = re.sub(r"https://[^\s'\"]*/api/webhooks/\d+/[\w\-]+", "<webhook-url-redacted>", s)
    return re.sub(r"/webhooks/\d+/[\w\-]{20,}", "/webhooks/<redacted>", s)

def http_json(url, method="GET", body=None, ctype=None):
    """Only HTTP entry point (tests replace this). Returns (status, parsed_json)."""
    req = urllib.request.Request(url, data=body, method=method,
                                 headers={"Content-Type": ctype or "application/json; charset=utf-8", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.load(r)

def multipart(payload, fname, data):
    b = "----NDTL" + hashlib.sha256(os.urandom(16)).hexdigest()[:24]
    out = (f"--{b}\r\nContent-Disposition: form-data; name=\"payload_json\"\r\nContent-Type: application/json\r\n\r\n").encode()
    out += json.dumps(payload).encode("utf-8") + b"\r\n"
    out += (f"--{b}\r\nContent-Disposition: form-data; name=\"files[0]\"; filename=\"{fname}\"\r\nContent-Type: image/png\r\n\r\n").encode()
    out += data + f"\r\n--{b}--\r\n".encode()
    return out, f"multipart/form-data; boundary={b}"

def atomic_json(path, obj):
    d = os.path.dirname(path); os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".rcpt.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2); f.write("\n"); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)

def main(argv):
    args = list(argv); edit = slot = None; dry = False
    if "--dry-run" in args: args.remove("--dry-run"); dry = True
    check = False
    if "--check-only" in args: args.remove("--check-only"); check = True
    if check and dry: print("--check-only and --dry-run are exclusive", file=sys.stderr); return 1
    if "--edit" in args: i = args.index("--edit"); edit = args[i + 1]; del args[i:i + 2]
    if "--slot" in args: i = args.index("--slot"); slot = args[i + 1]; del args[i:i + 2]
    image = newthread = None
    if "--image" in args: i = args.index("--image"); image = args[i + 1]; del args[i:i + 2]
    if "--new-thread" in args: i = args.index("--new-thread"); newthread = args[i + 1]; del args[i:i + 2]
    if len(args) == 1: args.append("")
    if len(args) != 2: print(__doc__, file=sys.stderr); return 1
    path, thread_arg = args
    if slot is not None and not re.fullmatch(r"[\w.\-]{1,80}", slot):
        print("bad --slot name", file=sys.stderr); return 1
    root = os.path.join(ROOT, "dryrun") if dry else os.path.join(ROOT, "check") if check else ROOT
    now = dt.datetime.now().astimezone()
    rc = {"status": None, "slot": slot, "dry_run": dry, "mode": "check" if check else "edit" if edit else "new_thread" if newthread else "post", "file": os.path.abspath(path),
          "thread_id": None, "message_id": edit, "content_sha256": None, "content_matches_file": None,
          "http_status": None, "error": None, "thread_name": newthread, "thread_url": None, "attachment": None, "attachment_returned": None, "warnings": [], "timestamp": now.isoformat(timespec="seconds")}
    rname = slot or now.strftime("%H%M%S_%f")
    rpath = os.path.join(root, "receipts", now.strftime("%Y-%m-%d"), rname + ".json")
    if os.path.exists(rpath):  # earlier attempt for same slot (e.g. duplicate) -> keep both
        rpath = rpath[:-5] + "__" + now.strftime("%H%M%S_%f") + ".json"
    lock = None

    def finish(status, code, **kw):
        rc.update(status=status, **kw)
        if rc["error"]: rc["error"] = redact(rc["error"])[:1000]
        atomic_json(rpath, rc)
        print(json.dumps({k: rc[k] for k in ("status", "slot", "thread_id", "thread_url", "message_id", "content_matches_file", "attachment_returned", "http_status", "error", "warnings")} | {"receipt": rpath}))
        return code

    try:
        text = open(path, encoding="utf-8").read().strip()
    except Exception as e:
        return finish("failed", 1, error=f"cannot read file: {e}")
    rc["content_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if image:
        try:
            img = open(image, "rb").read()
        except Exception as e:
            return finish("failed", 1, error=f"cannot read image: {e}")
        if not img: return finish("failed", 1, error="empty image file")
        rc["attachment"] = {"filename": os.path.basename(image), "size": len(img), "sha256": hashlib.sha256(img).hexdigest(), "path": os.path.abspath(image)}
    if newthread is not None:
        if edit: return finish("failed", 1, error="--new-thread and --edit are exclusive")
        if not newthread.strip() or len(newthread) > 100: return finish("failed", 1, error="bad --new-thread name")
        m = CHANNEL_RE.match(thread_arg.strip())
        if not m: return finish("skipped", 4, error="--new-thread needs the forum channel URL https://discord.com/channels/<guild>/<forum>")
        guild, parent, thread = m.group(1), m.group(2), None
        try: cfg = json.load(open(CONFIG, encoding="utf-8")) if os.path.exists(CONFIG) else {}
        except Exception as e: return finish("failed", 1, error=f"bad config {CONFIG}: {e}")
        want = str(cfg.get("forum_channel_id") or "")
        if want and want != parent:
            return finish("failed", 1, error=f"channel {parent} is not the configured forum_channel_id {want} ({CONFIG})")
        if not cfg.get("forum_type_confirmed"):
            rc["warnings"].append(f"channel {parent} not confirmed as a forum (config forum_type_confirmed is not true); a real --new-thread POST to a text channel fails with HTTP 400")
    else:
        m = THREAD_RE.match(thread_arg.strip())
        if m: guild, parent, thread = m.group(1), m.group(2), m.group(3)
    if not m:
        why = "thread_url missing or empty" if not thread_arg.strip() else "thread_url is not a full https://discord.com/channels/<guild>/<parent>/threads/<thread> URL"
        return finish("skipped", 4, error=why)
    rc["thread_id"] = thread
    if len(text) > 2000: return finish("failed", 1, error=f"too long: {len(text)} > 2000")
    if not text: return finish("failed", 1, error="empty file")
    if not check and not edit and not slot:  # Naman, Nov 3 2026: every post needs a slot claim + receipt
        return finish("failed", 1, error="--slot is required for every new post")

    if check:  # read-only: GET the webhook only, no slot lock, no POST/PATCH
        try:
            base = (os.environ.get("NDTL_WEBHOOK_URL") or (open(SECRET).read() if SECRET else "")).strip()
            _SECRETS.append(base)
            st, info = http_json(base)
        except Exception as e:
            return finish("check_failed", 1, http_status=getattr(e, "code", None), error=f"pre-check: {type(e).__name__}: {e}")
        if info.get("channel_id") != parent:
            return finish("check_failed", 1, http_status=st, error=f"webhook points at channel {info.get('channel_id')}, not thread parent {parent}")
        return finish("check_ok", 0, http_status=st)

    if slot:
        lock = os.path.join(root, "slots", slot + ".lock"); os.makedirs(os.path.dirname(lock), exist_ok=True)
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            try: held = open(lock).read().strip()
            except Exception: held = "?"
            return finish("duplicate_slot", 3, error=f"slot already claimed: {held}")
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps({"pid": os.getpid(), "claimed_at": rc["timestamp"], "file": rc["file"], "mode": rc["mode"]})); f.flush(); os.fsync(f.fileno())

    def release():  # only when we KNOW nothing was posted, so a retry is safe
        if lock and os.path.exists(lock): os.unlink(lock)

    if dry and newthread:  # validate the webhook target read-only (GET), never POST
        try:
            base = (os.environ.get("NDTL_WEBHOOK_URL") or (open(SECRET).read() if SECRET else "")).strip()
            _SECRETS.append(base)
            st, info = http_json(base)
        except Exception as e:
            release(); return finish("failed", 1, http_status=getattr(e, "code", None), error=f"pre-check: {type(e).__name__}: {e}")
        if info.get("channel_id") != parent:
            release(); return finish("failed", 1, http_status=st, error=f"webhook points at channel {info.get('channel_id')}, not forum channel {parent}; not posting")
        rc["webhook_channel_id"] = info.get("channel_id")
    if dry:
        ok = True
        if newthread: rc.update(thread_id="DRYRUN", thread_url=f"https://discord.com/channels/{guild}/{parent}/threads/DRYRUN", attachment_returned=bool(image) or None)
        return finish("edited" if edit else "posted", 0, message_id=edit or "DRYRUN", content_matches_file=ok, http_status="dry-run")
    try:
        base = (os.environ.get("NDTL_WEBHOOK_URL") or (open(SECRET).read() if SECRET else "")).strip()
        _SECRETS.append(base)
        # Pre-check: the webhook must point at the thread's parent channel, or the post would land top-level elsewhere.
        st, info = http_json(base)
        if info.get("channel_id") != parent:
            release()
            return finish("failed", 1, http_status=st, error=f"webhook points at channel {info.get('channel_id')}, not thread parent {parent}; not posting")
    except Exception as e:
        release(); return finish("failed", 1, http_status=getattr(e, "code", None), error=f"pre-check: {type(e).__name__}: {e}")
    if edit: url, method = f"{base}/messages/{edit}?thread_id={thread}", "PATCH"
    elif newthread: url, method = f"{base}?wait=true", "POST"
    else: url, method = f"{base}?wait=true&thread_id={thread}", "POST"
    payload = {"content": text, "allowed_mentions": {"parse": []}}
    if newthread: payload["thread_name"] = newthread
    try:
        if image:
            payload["attachments"] = [{"id": 0, "filename": rc["attachment"]["filename"]}]
            body, ct = multipart(payload, rc["attachment"]["filename"], img)
            st, d = http_json(url, method, body, ctype=ct)
        else:
            st, d = http_json(url, method, json.dumps(payload).encode("utf-8"))
    except urllib.error.HTTPError as e:  # server answered with an error: nothing posted
        try: detail = e.read().decode("utf-8", "replace")[:300]
        except Exception: detail = ""
        release(); return finish("failed", 1, http_status=e.code, error=f"HTTP {e.code}: {detail}")
    except Exception as e:  # ambiguous (timeout etc.): keep slot lock to avoid a double post
        return finish("failed", 1, error=f"{type(e).__name__}: {e} (slot kept: delivery unknown)")
    if newthread:
        thread = d.get("channel_id")
        if not thread or thread == parent:
            return finish("failed", 1, http_status=st, message_id=d.get("id"), error=f"no new thread in response (channel_id={thread}); not a forum post")
        rc["thread_id"] = thread; rc["thread_url"] = f"https://discord.com/channels/{guild}/{parent}/threads/{thread}"
    if image:
        att = d.get("attachments") or []
        rc["attachment_returned"] = any(a.get("filename") == rc["attachment"]["filename"] and a.get("size") == rc["attachment"]["size"] for a in att)
        if not rc["attachment_returned"]:
            return finish("failed", 2, http_status=st, message_id=d.get("id"), content_matches_file=d.get("content") == text, error="attachment missing from response")
    if d.get("channel_id") != thread:
        return finish("failed", 1, http_status=st, message_id=d.get("id"), error=f"posted to {d.get('channel_id')}, expected {thread}")
    ok = d.get("content") == text
    return finish(("edited" if edit else "posted"), 0 if ok else 2, http_status=st, message_id=d.get("id"), content_matches_file=ok)

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
