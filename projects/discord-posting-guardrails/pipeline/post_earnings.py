#!/usr/bin/env python3
"""Post one earnings chart into a Discord thread, but only after its checks passed.
Usage: post_earnings.py <TICKER> <image.png> <caption_file.md> <thread_url> <slot> [--dry-run]
       (post_earnings.sh is a thin wrapper with the same arguments.)
The chart dir is the image's directory and must be named <TICKER>-YYYY-MM-DD (under ${NDTL_EARNINGS_ROOT},
override with env NDTL_EARNINGS_ROOT). Refuses (no post) unless ALL hold:
 claims  (exit 22)  <dir>/claims.json exists and its "output" equals the image basename;
                    <dir>/claims_check.md exists, names the image basename in its first line, contains
                    "Result: **PASS**" (or "RESULT: PASS"), has no "- FAIL" line, and is not older than claims.json.
 review  (exit 20)  <dir>/review_ok/<image basename>.ok exists (missing -> 20);
         (exit 21)  it is JSON {"image": <basename>, "sha256": <sha256 of the PNG>, "reviewer": "Manager Bot",
                    "reviewed_at": <ISO-8601 with offset>} and sha256 equals the CURRENT image bytes (mismatch/invalid -> 21).
Then runs ${NDTL_POST_WEBHOOK} (../poster/post_webhook.py by default) <caption_file.md> <thread_url> --slot <slot> --image <image> [--dry-run]
as a subprocess and returns its exit code (0 ok, 1 failed, 2 mismatch, 3 duplicate slot, 4 skipped).
Exit 23 bad arguments / unreadable image or caption."""
import datetime as dt, hashlib, json, os, re, subprocess, sys
EARN = os.environ.get("NDTL_EARNINGS_ROOT", "")
POST = os.environ.get("NDTL_POST_WEBHOOK", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "poster", "post_webhook.py")))
E_NO_OK, E_SHA, E_CLAIMS, E_ARGS = 20, 21, 22, 23

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()

def check(ticker, image):
    """Return (code, message). code 0 = all checks passed."""
    if not re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", ticker): return E_ARGS, f"bad ticker {ticker!r}"
    if not os.path.isfile(image) or not os.path.getsize(image): return E_ARGS, f"image missing or empty: {image}"
    img = os.path.realpath(image); d = os.path.dirname(img); name = os.path.basename(img)
    if os.path.dirname(d) != os.path.realpath(EARN) or not re.fullmatch(re.escape(ticker) + r"-\d{4}-\d{2}-\d{2}", os.path.basename(d)):
        return E_ARGS, f"image must be in {EARN}/{ticker}-YYYY-MM-DD/"
    cj, cm = os.path.join(d, "claims.json"), os.path.join(d, "claims_check.md")
    if not os.path.exists(cj): return E_CLAIMS, "claims.json missing"
    try: out = json.load(open(cj, encoding="utf-8")).get("output")
    except Exception as e: return E_CLAIMS, f"claims.json unreadable: {e}"
    if out != name: return E_CLAIMS, f"claims.json is for {out!r}, not {name}"
    if not os.path.exists(cm): return E_CLAIMS, "claims_check.md missing"
    txt = open(cm, encoding="utf-8").read(); first = txt.splitlines()[0] if txt else ""
    if name not in first: return E_CLAIMS, f"claims_check.md first line does not name {name}"
    if not re.search(r"Result: \*\*PASS\*\*|RESULT: PASS\b", txt): return E_CLAIMS, "claims_check.md has no PASS result"
    if re.search(r"^\s*-\s*FAIL\b", txt, re.M) or re.search(r"\d+ FAIL", txt): return E_CLAIMS, "claims_check.md lists FAIL items"
    if os.path.getmtime(cm) < os.path.getmtime(cj): return E_CLAIMS, "claims_check.md is older than claims.json (re-run the check)"
    okp = os.path.join(d, "review_ok", name + ".ok")
    if not os.path.exists(okp): return E_NO_OK, f"no Manager Bot OK file {okp}"
    try:
        ok = json.load(open(okp, encoding="utf-8"))
        dt.datetime.fromisoformat(ok["reviewed_at"])
    except Exception as e: return E_SHA, f"OK file invalid: {e}"
    if ok.get("reviewer") != "Manager Bot" or ok.get("image") != name: return E_SHA, "OK file reviewer/image mismatch"
    if ok.get("sha256") != sha256(img): return E_SHA, f"OK file sha256 does not match current {name} (image changed since review)"
    return 0, "checks passed"

def main(argv):
    a = list(argv); dry = "--dry-run" in a
    if dry: a.remove("--dry-run")
    if len(a) != 5: print(__doc__, file=sys.stderr); return E_ARGS
    ticker, image, caption, turl, slot = a
    if not os.path.isfile(caption): print(json.dumps({"status": "refused", "code": E_ARGS, "reason": "caption file not found (pass a file path, not text)"})); return E_ARGS
    code, why = check(ticker.upper(), image)
    if code: print(json.dumps({"status": "refused", "code": code, "reason": why})); return code
    cmd = [sys.executable, POST, caption, turl, "--slot", slot, "--image", image] + (["--dry-run"] if dry else [])
    return subprocess.run(cmd).returncode

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
