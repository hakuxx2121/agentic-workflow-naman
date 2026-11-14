#!/usr/bin/env python3
"""TradingView edit lease (one editor at a time).
  tv_lease.py acquire --owner NAME --ttl SECONDS [--takeover-verified SCREENSHOT]
  tv_lease.py heartbeat --owner NAME [--ttl SECONDS]
  tv_lease.py release --owner NAME
  tv_lease.py status
Lease: ${NDTL_PIPELINE_ROOT}/locks/tradingview.lease (override dir with NDTL_PIPELINE_ROOT).
Exit: 0 ok; 1 usage/error; 3 held by another active owner; 4 not the owner / no lease;
      5 expired lease needs verified takeover; 6 takeover screenshot missing or not newer than expires_at."""
import argparse, datetime as dt, json, os, sys, tempfile, time
ROOT = os.environ.get("NDTL_PIPELINE_ROOT", os.path.dirname(os.path.abspath(__file__)))
LEASE = os.path.join(ROOT, "locks", "tradingview.lease")
HIST = os.path.join(ROOT, "locks", "tradingview.history.jsonl")
iso = lambda t: dt.datetime.fromtimestamp(t).astimezone().isoformat(timespec="seconds")
ts = lambda s: dt.datetime.fromisoformat(s).timestamp()

def read():
    try: return json.load(open(LEASE))
    except FileNotFoundError: return None

def rewrite(d):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(LEASE), prefix=".lease.")
    with os.fdopen(fd, "w") as f: json.dump(d, f, indent=2); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, LEASE)

def log(ev):
    with open(HIST, "a") as f: f.write(json.dumps(ev) + "\n"); f.flush(); os.fsync(f.fileno())

def new_lease(owner, ttl, history=None):
    n = time.time()
    return {"owner": owner, "ttl": ttl, "acquired_at": iso(n), "heartbeat_at": iso(n), "expires_at": iso(n + ttl), "history": history or []}

def create_excl(d):
    fd = os.open(LEASE, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    with os.fdopen(fd, "w") as f: json.dump(d, f, indent=2); f.flush(); os.fsync(f.fileno())

def acquire(o):
    os.makedirs(os.path.dirname(LEASE), exist_ok=True)
    try:
        create_excl(new_lease(o.owner, o.ttl)); log({"event": "acquire", "owner": o.owner, "at": iso(time.time())})
        print(f"acquired by {o.owner} for {o.ttl}s"); return 0
    except FileExistsError: pass
    cur = read()
    if cur is None: return acquire(o)  # released in between
    exp = ts(cur["expires_at"])
    if exp > time.time():
        if cur["owner"] == o.owner: print(f"already held by {o.owner} until {cur['expires_at']} (use heartbeat)"); return 3
        print(f"lease held by {cur['owner']} until {cur['expires_at']}", file=sys.stderr); return 3
    if not o.takeover_verified:
        print(f"expired lease held by {cur['owner']}; verify a 4-pane screenshot of Jason's picks 1 shows no edit in progress, "
              f"then rerun with --takeover-verified <screenshot_path>", file=sys.stderr); return 5
    p = o.takeover_verified
    if not os.path.isfile(p) or os.path.getsize(p) == 0:
        print(f"takeover screenshot not found or empty: {p}", file=sys.stderr); return 6
    if os.path.getmtime(p) <= exp:
        print(f"takeover screenshot {p} is not newer than lease expiry {cur['expires_at']}; take a fresh one", file=sys.stderr); return 6
    ev = {"event": "takeover", "from": cur["owner"], "to": o.owner, "expired_at": cur["expires_at"], "screenshot": os.path.abspath(p),
          "screenshot_mtime": iso(os.path.getmtime(p)), "at": iso(time.time())}
    hist = (cur.get("history") or []) + [ev]
    # compare-and-swap: only replace if the file is still the expired lease we inspected
    if read() != cur: print("lease changed during takeover; rerun", file=sys.stderr); return 3
    rewrite(new_lease(o.owner, o.ttl, hist)); log(ev)
    print(f"took over expired lease from {cur['owner']}; acquired by {o.owner} for {o.ttl}s"); return 0

def heartbeat(o):
    cur = read()
    if not cur: print("no lease", file=sys.stderr); return 4
    if cur["owner"] != o.owner: print(f"lease owned by {cur['owner']}, not {o.owner}", file=sys.stderr); return 4
    if ts(cur["expires_at"]) <= time.time():
        print(f"lease expired at {cur['expires_at']}; re-acquire with --takeover-verified", file=sys.stderr); return 5
    ttl = o.ttl or cur.get("ttl") or 600; n = time.time()
    cur.update(heartbeat_at=iso(n), expires_at=iso(n + ttl), ttl=ttl); rewrite(cur)
    print(f"heartbeat ok; expires {cur['expires_at']}"); return 0

def release(o):
    cur = read()
    if not cur: print("no lease"); return 0
    if cur["owner"] != o.owner: print(f"lease owned by {cur['owner']}, not {o.owner}", file=sys.stderr); return 4
    os.unlink(LEASE); log({"event": "release", "owner": o.owner, "at": iso(time.time())}); print("released"); return 0

def status(o):
    cur = read()
    if not cur: print(json.dumps({"state": "free"})); return 0
    cur["state"] = "active" if ts(cur["expires_at"]) > time.time() else "expired"
    print(json.dumps(cur, indent=2)); return 0

def main(a=None):
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    x = sp.add_parser("acquire"); x.add_argument("--owner", required=True); x.add_argument("--ttl", type=int, required=True); x.add_argument("--takeover-verified")
    x = sp.add_parser("heartbeat"); x.add_argument("--owner", required=True); x.add_argument("--ttl", type=int)
    x = sp.add_parser("release"); x.add_argument("--owner", required=True)
    sp.add_parser("status")
    o = ap.parse_args(a)
    if getattr(o, "ttl", None) is not None and o.ttl <= 0: ap.error("--ttl must be > 0")
    return {"acquire": acquire, "heartbeat": heartbeat, "release": release, "status": status}[o.cmd](o)

if __name__ == "__main__": sys.exit(main())
