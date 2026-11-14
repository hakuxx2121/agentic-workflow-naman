#!/usr/bin/env python3
"""levels.json read/write (atomic) + CLI to rebuild from a plan folder.
CLI: levels_io.py build <plan_dir> [--week-of YYYY-MM-DD] [--out PATH]
Default out: ${NDTL_PIPELINE_ROOT}/week_MMDD/levels.json (MMDD of the Monday)."""
import csv, datetime as dt, json, os, re, sys, tempfile
SCHEMA_VERSION = 1
ROLES = {"support", "resistance", "trigger", "target", "stop"}
ROOT = os.environ.get("NDTL_PIPELINE_ROOT", os.path.dirname(os.path.abspath(__file__)))

class LevelsError(ValueError): pass

def validate(d):
    if not isinstance(d, dict): raise LevelsError("data must be an object")
    if d.get("schema_version") != SCHEMA_VERSION: raise LevelsError(f"schema_version must be {SCHEMA_VERSION}")
    try: wd = dt.date.fromisoformat(d.get("week_of", ""))
    except Exception: raise LevelsError("week_of must be YYYY-MM-DD")
    if wd.weekday() != 0: raise LevelsError("week_of must be a Monday")
    tu = d.get("thread_url")
    if tu is not None and not (isinstance(tu, str) and re.fullmatch(r"https://(?:\w+\.)?discord(?:app)?\.com/channels/\d+/\d+/threads/\d+", tu)):
        raise LevelsError("thread_url must be a full Discord thread URL or null")
    if not isinstance(d.get("generated_at"), str): raise LevelsError("generated_at required")
    ts = d.get("tickers")
    if not isinstance(ts, list): raise LevelsError("tickers must be a list")
    seen = set()
    for t in ts:
        s = t.get("symbol") if isinstance(t, dict) else None
        if not s or not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", s): raise LevelsError(f"bad symbol {s!r}")
        if s in seen: raise LevelsError(f"duplicate symbol {s}")
        seen.add(s)
        if not isinstance(t.get("levels"), list): raise LevelsError(f"{s}: levels must be a list")
        for L in t["levels"]:
            p = L.get("price")
            if not isinstance(p, (int, float)) or isinstance(p, bool) or p <= 0: raise LevelsError(f"{s}: bad price {p!r}")
            if L.get("role") not in ROLES: raise LevelsError(f"{s}: bad role {L.get('role')!r}")
            if not isinstance(L.get("note", ""), str): raise LevelsError(f"{s}: note must be str")
    return d

def write_levels(path, data):
    validate(data)
    d = os.path.dirname(os.path.abspath(path)); os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".levels.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False); f.write("\n"); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
        dfd = os.open(d, os.O_RDONLY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
    except BaseException:
        if os.path.exists(tmp): os.unlink(tmp)
        raise

def read_levels(path):
    with open(path, encoding="utf-8") as f: d = json.load(f)
    if d.get("schema_version") != SCHEMA_VERSION:
        raise LevelsError(f"{path}: schema_version {d.get('schema_version')!r} != {SCHEMA_VERSION}")
    return validate(d)

def latest_levels_path(root=ROOT):
    ws = sorted(n for n in os.listdir(root) if re.fullmatch(r"week_\d{4}", n) and os.path.exists(os.path.join(root, n, "levels.json")))
    # MMDD has no year; order by mtime of week_of inside the file to be safe across Dec/Jan
    if not ws: raise LevelsError(f"no week_*/levels.json under {root}")
    ws.sort(key=lambda n: json.load(open(os.path.join(root, n, "levels.json"))).get("week_of", ""))
    return os.path.join(root, ws[-1], "levels.json")

def _captions(plan_dir):
    p = os.path.join(plan_dir, "captions_verified.md"); out = {}
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            m = re.match(r"([A-Z][A-Z0-9.]{0,9})(?:\s*\([^)]*\))?:\s*(.+)", line.strip())
            if m: out[m.group(1)] = m.group(2)
    return out

def build_from_plan(plan_dir, week_of=None):
    if not week_of:
        m = re.search(r"(\d{2})(\d{2})$", os.path.basename(os.path.normpath(plan_dir)))
        if not m: raise LevelsError("cannot infer week_of; pass --week-of")
        week_of = f"{dt.date.today().year}-{m.group(1)}-{m.group(2)}"
    tu = None; tp = os.path.join(plan_dir, "thread_url.txt")
    if os.path.exists(tp): tu = open(tp).read().strip() or None
    caps = _captions(plan_dir); order = list(caps); tick = {}
    with open(os.path.join(plan_dir, "levels.csv"), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            s = r["ticker"].strip().upper()
            if s not in order: order.append(s)
            tick.setdefault(s, []).append({"price": float(r["price"]), "role": r["type"].strip().lower(), "note": r["label"].strip()})
    tickers = []
    for s in order:
        lv = sorted(tick.get(s, []), key=lambda L: L["price"])
        t = {"symbol": s, "levels": lv}
        if s in caps: t["plan_note"] = caps[s]
        tickers.append(t)
    return {"schema_version": SCHEMA_VERSION, "week_of": week_of, "thread_url": tu,
            "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "source": os.path.abspath(plan_dir), "tickers": tickers}

def main(argv):
    if len(argv) < 2 or argv[0] != "build": print(__doc__, file=sys.stderr); return 1
    plan = argv[1]; wk = out = None
    if "--week-of" in argv: wk = argv[argv.index("--week-of") + 1]
    if "--out" in argv: out = argv[argv.index("--out") + 1]
    d = build_from_plan(plan, wk)
    out = out or os.path.join(ROOT, "week_" + d["week_of"][5:7] + d["week_of"][8:10], "levels.json")
    write_levels(out, d)
    n = sum(len(t["levels"]) for t in d["tickers"]); empty = [t["symbol"] for t in d["tickers"] if not t["levels"]]
    print(json.dumps({"written": out, "tickers": len(d["tickers"]), "levels": n, "tickers_without_levels": empty}))
    return 0

if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
