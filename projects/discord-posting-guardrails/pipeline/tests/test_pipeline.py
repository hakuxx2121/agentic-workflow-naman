"""Offline tests. Run: python3 -m pytest -q tests  (no network, no Discord)."""
import importlib.util, io, json, os, subprocess, sys, tempfile, time, contextlib, pytest
HERE = os.path.dirname(os.path.abspath(__file__))
P = os.environ.get("NDTL_PIPELINE_ROOT") or os.path.abspath(os.path.join(HERE, ".."))
POSTER = os.environ.get("NDTL_POST_WEBHOOK") or os.path.abspath(os.path.join(HERE, "..", "..", "poster", "post_webhook.py")); sys.path.insert(0, P)
FAKE = "https://discord.com/api/webhooks/000000000000000000/EXAMPLE_TOKEN_NOT_A_SECRET"
G, PAR, TH = "100000000000000001", "200000000000000002", "300000000000000003"
TURL = f"https://discord.com/channels/{G}/{PAR}/threads/{TH}"

def load_pw(root, monkeypatch):
    monkeypatch.setenv("NDTL_PIPELINE_ROOT", str(root)); monkeypatch.setenv("NDTL_WEBHOOK_URL", FAKE)
    monkeypatch.setenv("NDTL_DISCORD_CONFIG", str(root / "config.json"))
    s = importlib.util.spec_from_file_location("pw", POSTER); m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m

def run(m, argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf): code = m.main(argv)
    out = json.loads(buf.getvalue().strip().splitlines()[-1]); return code, out, json.load(open(out["receipt"]))

@pytest.fixture
def msg(tmp_path):
    f = tmp_path / "m.md"; f.write_text("hello NDTL\n"); return str(f)

def fake_http(calls, content="hello NDTL", parent=PAR, fail=None):
    def h(url, method="GET", body=None):
        calls.append((method, url))
        if method == "GET": return 200, {"channel_id": parent}
        if fail: raise fail
        return 200, {"id": "999", "channel_id": TH, "content": content}
    return h

def test_normal_post(tmp_path, msg, monkeypatch):
    m = load_pw(tmp_path, monkeypatch); calls = []; m.http_json = fake_http(calls)
    code, out, r = run(m, [msg, TURL, "--slot", "2026-11-04_0930"])
    assert code == 0 and r["status"] == "posted" and r["message_id"] == "999" and r["content_matches_file"] and r["thread_id"] == TH
    assert [c[0] for c in calls] == ["GET", "POST"] and f"thread_id={TH}" in calls[1][1]
    assert os.path.exists(tmp_path / "slots/2026-11-04_0930.lock") and len(r["content_sha256"]) == 64
    assert "EXAMPLE_TOKEN_NOT_A_SECRET" not in open(out["receipt"]).read()

def test_duplicate_slot(tmp_path, msg, monkeypatch):
    m = load_pw(tmp_path, monkeypatch); calls = []; m.http_json = fake_http(calls)
    assert run(m, [msg, TURL, "--slot", "s1"])[0] == 0
    code, out, r = run(m, [msg, TURL, "--slot", "s1"])
    assert code == 3 and r["status"] == "duplicate_slot" and len(calls) == 2  # no HTTP on 2nd
    assert out["receipt"] != json.dumps(None) and "__" in out["receipt"]  # first receipt preserved

@pytest.mark.parametrize("bad", ["", "   ", TH, f"https://discord.com/channels/{G}/{TH}", "https://evil.com/channels/1/2/threads/3"])
def test_missing_or_bad_thread_url(tmp_path, msg, monkeypatch, bad):
    m = load_pw(tmp_path, monkeypatch); calls = []; m.http_json = fake_http(calls)
    code, out, r = run(m, [msg, bad, "--slot", "x"])
    assert code == 4 and r["status"] == "skipped" and r["error"] and calls == [] and not os.path.exists(tmp_path / "slots/x.lock")

def test_missing_thread_arg_entirely(tmp_path, msg, monkeypatch):
    m = load_pw(tmp_path, monkeypatch); m.http_json = fake_http([])
    assert run(m, [msg])[0] == 4

def test_edit(tmp_path, msg, monkeypatch):
    m = load_pw(tmp_path, monkeypatch); calls = []; m.http_json = fake_http(calls)
    code, out, r = run(m, [msg, TURL, "--edit", "555", "--slot", "e1"])
    assert code == 0 and r["status"] == "edited" and calls[1][0] == "PATCH" and "/messages/555?thread_id=" in calls[1][1]

def test_content_mismatch_exit2(tmp_path, msg, monkeypatch):
    m = load_pw(tmp_path, monkeypatch); m.http_json = fake_http([], content="mangled")
    code, out, r = run(m, [msg, TURL, "--slot", "t_mismatch"]); assert code == 2 and r["content_matches_file"] is False

def test_precheck_wrong_channel_releases_slot(tmp_path, msg, monkeypatch):
    m = load_pw(tmp_path, monkeypatch); calls = []; m.http_json = fake_http(calls, parent="1" * 18)
    code, out, r = run(m, [msg, TURL, "--slot", "p"])
    assert code == 1 and r["status"] == "failed" and len(calls) == 1 and not os.path.exists(tmp_path / "slots/p.lock")

def test_http_error_redacts_url(tmp_path, msg, monkeypatch):
    m = load_pw(tmp_path, monkeypatch); m.http_json = fake_http([], fail=RuntimeError(f"boom at {FAKE}?wait=true"))
    code, out, r = run(m, [msg, TURL, "--slot", "t"])
    assert code == 1 and "EXAMPLE_TOKEN_NOT_A_SECRET" not in json.dumps(r) and "000000000000000000/" not in json.dumps(r)
    assert os.path.exists(tmp_path / "slots/t.lock")  # ambiguous delivery -> slot kept

def test_dry_run_cli_no_http(tmp_path, msg):
    env = {**os.environ, "NDTL_PIPELINE_ROOT": str(tmp_path), "NDTL_WEBHOOK_URL": "https://127.0.0.1:9/should-not-be-called"}
    p = subprocess.run([sys.executable, POSTER, msg, TURL, "--slot", "d", "--dry-run"], env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert os.path.exists(tmp_path / "dryrun/slots/d.lock")
    p2 = subprocess.run([sys.executable, POSTER, msg, TURL, "--slot", "d", "--dry-run"], env=env, capture_output=True, text=True)
    assert p2.returncode == 3
    p3 = subprocess.run([sys.executable, POSTER, msg, "", "--dry-run"], env=env, capture_output=True, text=True)
    assert p3.returncode == 4

# ---------- levels_io ----------
import levels_io
def test_levels_roundtrip_and_validation(tmp_path):
    d = levels_io.build_from_plan(str(tmp_path / "plan"), "2026-11-02"); p = tmp_path / "w/levels.json"
    levels_io.write_levels(str(p), d); assert levels_io.read_levels(str(p))["week_of"] == "2026-11-02"
    assert not [f for f in os.listdir(tmp_path / "w") if f.endswith(".tmp")]
    bad = json.loads(json.dumps(d)); bad["tickers"][0]["levels"] = [{"price": -1, "role": "support"}]
    with pytest.raises(levels_io.LevelsError): levels_io.write_levels(str(p), bad)
    assert levels_io.read_levels(str(p))["tickers"] == d["tickers"]  # old file untouched
    p.write_text(json.dumps({**d, "schema_version": 2}))
    with pytest.raises(levels_io.LevelsError): levels_io.read_levels(str(p))

# ---------- prices (offline classify) ----------
import prices
LV = [{"price": 90, "role": "support", "note": ""}, {"price": 100, "role": "resistance", "note": ""}]
@pytest.mark.parametrize("px,st", [(101, "above resistance"), (89, "below support"), (99.5, "within 1% of 100 (resistance)"), (95, "in range")])
def test_classify(px, st):
    assert prices.classify(px, LV, 1.0)[2] == st

def test_prices_fixture(tmp_path):
    lv = tmp_path / "week_1102"; lv.mkdir()
    levels_io.write_levels(str(lv / "levels.json"), {"schema_version": 1, "week_of": "2026-11-02", "thread_url": None, "generated_at": "x", "tickers": [{"symbol": "ABC", "levels": LV}]})
    fx = {"ABC": {"meta": {"regularMarketPrice": 95.0, "chartPreviousClose": 94.0, "regularMarketTime": 1, "currentTradingPeriod": {"regular": {"start": 100, "end": 200}}},
                  "timestamp": [150, 250], "indicators": {"quote": [{"close": [95.0, 101.0]}]}}}
    (tmp_path / "fx.json").write_text(json.dumps(fx))
    for sess, st, last in [("regular", "in range", 95.0), ("extended", "above resistance", 101.0)]:
        p = subprocess.run([sys.executable, f"{P}/prices.py", "--levels", str(lv / "levels.json"), "--session", sess, "--fixture", str(tmp_path / "fx.json")], capture_output=True, text=True)
        r = json.loads(p.stdout)["tickers"][0]; assert p.returncode == 0 and r["status"] == st and r["last"] == last and r["ext_session"] == "post"

# ---------- tv_lease ----------
def L(root, *a):
    p = subprocess.run([sys.executable, f"{P}/tv_lease.py", *a], env={**os.environ, "NDTL_PIPELINE_ROOT": str(root)}, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr

def lease(root): return json.load(open(root / "locks/tradingview.lease"))

def test_lease_all_paths(tmp_path):
    assert L(tmp_path, "status")[1].strip() == '{"state": "free"}'
    assert L(tmp_path, "acquire", "--owner", "a", "--ttl", "60")[0] == 0
    assert L(tmp_path, "acquire", "--owner", "b", "--ttl", "60")[0] == 3          # held, active
    assert L(tmp_path, "heartbeat", "--owner", "b")[0] == 4                       # not owner
    e0 = lease(tmp_path)["expires_at"]; time.sleep(1.1)
    assert L(tmp_path, "heartbeat", "--owner", "a")[0] == 0 and lease(tmp_path)["expires_at"] > e0
    assert L(tmp_path, "release", "--owner", "b")[0] == 4
    assert L(tmp_path, "release", "--owner", "a")[0] == 0 and L(tmp_path, "status")[1].strip() == '{"state": "free"}'
    # expiry
    assert L(tmp_path, "acquire", "--owner", "a", "--ttl", "1")[0] == 0; time.sleep(1.2)
    assert '"expired"' in L(tmp_path, "status")[1]
    assert L(tmp_path, "heartbeat", "--owner", "a")[0] == 5
    c, out = L(tmp_path, "acquire", "--owner", "b", "--ttl", "60")
    assert c == 5 and "expired lease held by a; verify a 4-pane screenshot of Jason's picks 1 shows no edit in progress, then rerun with --takeover-verified <screenshot_path>" in out
    assert L(tmp_path, "acquire", "--owner", "b", "--ttl", "60", "--takeover-verified", str(tmp_path / "nope.png"))[0] == 6
    old = tmp_path / "old.png"; old.write_bytes(b"x"); os.utime(old, (1, 1))
    assert L(tmp_path, "acquire", "--owner", "b", "--ttl", "60", "--takeover-verified", str(old))[0] == 6
    new = tmp_path / "new.png"; new.write_bytes(b"png")
    c, out = L(tmp_path, "acquire", "--owner", "b", "--ttl", "60", "--takeover-verified", str(new)); assert c == 0, out
    d = lease(tmp_path); assert d["owner"] == "b" and d["history"][-1]["event"] == "takeover" and d["history"][-1]["from"] == "a"
    assert "takeover" in (tmp_path / "locks/tradingview.history.jsonl").read_text()

# ---------- post_webhook --check-only ----------
def test_check_only_ok_and_failed(tmp_path, msg, monkeypatch):
    m = load_pw(tmp_path, monkeypatch); calls = []; m.http_json = fake_http(calls)
    code, out, r = run(m, [msg, TURL, "--slot", "c1", "--check-only"])
    assert code == 0 and r["status"] == "check_ok" and r["mode"] == "check" and r["thread_id"] == TH
    assert [c[0] for c in calls] == ["GET"]  # only the read-only GET
    assert not os.path.exists(tmp_path / "slots/c1.lock") and not os.path.exists(tmp_path / "check/slots")
    assert out["receipt"].startswith(str(tmp_path / "check/receipts")) and "EXAMPLE_TOKEN_NOT_A_SECRET" not in open(out["receipt"]).read()
    calls2 = []; m.http_json = fake_http(calls2, parent="1" * 18)
    code, out, r = run(m, [msg, TURL, "--slot", "c1", "--check-only"])
    assert code == 1 and r["status"] == "check_failed" and [c[0] for c in calls2] == ["GET"] and "not thread parent" in r["error"]
    m.http_json = lambda *a, **k: (_ for _ in ()).throw(RuntimeError(f"down {FAKE}"))
    code, out, r = run(m, [msg, TURL, "--check-only"])
    assert code == 1 and r["status"] == "check_failed" and "EXAMPLE_TOKEN_NOT_A_SECRET" not in json.dumps(r)
    assert run(m, [msg, "", "--check-only"])[0] == 4


def test_post_without_slot_refused(tmp_path, msg, monkeypatch):
    m = load_pw(tmp_path, monkeypatch); calls = []
    m.http_json = fake_http(calls)
    code, out, r = run(m, [msg, TURL]); assert code == 1 and r["status"] == "failed" and "slot is required" in r["error"] and calls == []

# ---------- post_webhook --image / --new-thread ----------
FURL = f"https://discord.com/channels/{G}/{PAR}"
NEWTH = "400000000000000004"

@pytest.fixture
def png(tmp_path):
    f = tmp_path / "c.png"; f.write_bytes(b"\x89PNG\r\n\x1a\nFAKEIMAGEBYTES"); return str(f)

def fake_mp(calls, content="hello NDTL", chan=TH, attach=True):
    def h(url, method="GET", body=None, ctype=None):
        calls.append((method, url, body, ctype))
        if method == "GET": return 200, {"channel_id": PAR}
        att = [{"filename": "c.png", "size": 22}] if attach else []
        return 200, {"id": "999", "channel_id": chan, "content": content, "attachments": att}
    return h

def test_image_multipart(tmp_path, msg, png, monkeypatch):
    m = load_pw(tmp_path, monkeypatch); calls = []; m.http_json = fake_mp(calls)
    code, out, r = run(m, [msg, TURL, "--slot", "i1", "--image", png])
    assert code == 0 and r["attachment_returned"] and r["attachment"]["size"] == 22 and len(r["attachment"]["sha256"]) == 64
    _, url, body, ct = calls[1]
    assert ct.startswith("multipart/form-data; boundary=") and f"thread_id={TH}" in url and "wait=true" in url
    assert b'name="payload_json"' in body and b'"content": "hello NDTL"' in body
    assert b'name="files[0]"; filename="c.png"' in body and b"FAKEIMAGEBYTES" in body

def test_image_missing_attachment_in_response(tmp_path, msg, png, monkeypatch):
    m = load_pw(tmp_path, monkeypatch); m.http_json = fake_mp([], attach=False)
    code, out, r = run(m, [msg, TURL, "--slot", "i2", "--image", png]); assert code == 2 and r["attachment_returned"] is False

def test_new_thread(tmp_path, msg, png, monkeypatch):
    m = load_pw(tmp_path, monkeypatch); calls = []; m.http_json = fake_mp(calls, chan=NEWTH)
    code, out, r = run(m, [msg, FURL, "--slot", "n1", "--image", png, "--new-thread", "AI Earnings - Week of 11/2/26"])
    assert code == 0 and r["mode"] == "new_thread" and r["thread_id"] == NEWTH
    assert r["thread_url"] == f"https://discord.com/channels/{G}/{PAR}/threads/{NEWTH}" and out["thread_url"] == r["thread_url"]
    _, url, body, _ = calls[1]
    assert url.endswith("?wait=true") and "thread_id" not in url and b'"thread_name": "AI Earnings - Week of 11/2/26"' in body

def test_new_thread_not_forum_fails(tmp_path, msg, monkeypatch):
    m = load_pw(tmp_path, monkeypatch); m.http_json = fake_mp([], chan=PAR)
    code, out, r = run(m, [msg, FURL, "--slot", "n2", "--new-thread", "x"]); assert code == 1 and "not a forum" in r["error"]

def test_new_thread_requires_slot_and_forum_url(tmp_path, msg, monkeypatch):
    m = load_pw(tmp_path, monkeypatch); calls = []; m.http_json = fake_mp(calls)
    code, out, r = run(m, [msg, FURL, "--new-thread", "x"]); assert code == 1 and "slot is required" in r["error"] and calls == []
    assert run(m, [msg, TURL, "--slot", "n3", "--new-thread", "x"])[0] == 4 and calls == []

def test_missing_image_fails_cleanly(tmp_path, msg, monkeypatch):
    m = load_pw(tmp_path, monkeypatch); calls = []; m.http_json = fake_mp(calls)
    code, out, r = run(m, [msg, TURL, "--slot", "i3", "--image", str(tmp_path / "nope.png")])
    assert code == 1 and "cannot read image" in r["error"] and calls == [] and not os.path.exists(tmp_path / "slots/i3.lock")


# ---------- post_webhook --new-thread config + dry-run ----------
def test_new_thread_config_mismatch_refused(tmp_path, msg, monkeypatch):
    m = load_pw(tmp_path, monkeypatch); calls = []; m.http_json = fake_mp(calls)
    (tmp_path / "config.json").write_text(json.dumps({"forum_channel_id": "999999999999999999"}))
    code, out, r = run(m, [msg, FURL, "--slot", "c1", "--new-thread", "x"])
    assert code == 1 and "forum_channel_id" in r["error"] and calls == [] and not os.path.exists(tmp_path / "slots/c1.lock")

def test_new_thread_dry_run_get_only(tmp_path, msg, png, monkeypatch):
    m = load_pw(tmp_path, monkeypatch); calls = []; m.http_json = fake_mp(calls)
    (tmp_path / "config.json").write_text(json.dumps({"forum_channel_id": PAR, "forum_type_confirmed": False}))
    code, out, r = run(m, [msg, FURL, "--slot", "d1", "--image", png, "--new-thread", "NDTL - Weekly Trade Plan 11/9/26", "--dry-run"])
    assert code == 0 and r["dry_run"] and [c[0] for c in calls] == ["GET"] and r["webhook_channel_id"] == PAR
    assert r["warnings"] and "dryrun" in out["receipt"] and not os.path.exists(tmp_path / "slots/d1.lock")
    assert "EXAMPLE_TOKEN_NOT_A_SECRET" not in open(out["receipt"]).read()

def test_new_thread_dry_run_wrong_webhook_channel(tmp_path, msg, monkeypatch):
    m = load_pw(tmp_path, monkeypatch); calls = []
    def h(url, method="GET", body=None, ctype=None):
        calls.append(method); return 200, {"channel_id": "777777777777777777"}
    m.http_json = h
    code, out, r = run(m, [msg, FURL, "--slot", "d2", "--new-thread", "x", "--dry-run"])
    assert code == 1 and calls == ["GET"] and "777777777777777777" in r["error"] and not os.path.exists(tmp_path / "dryrun/slots/d2.lock")

# ---------- render_update ----------
import render_update as ru
SUPL = [{"price": 15.0, "role": "support", "note": ""}, {"price": 16.0, "role": "support", "note": ""},
        {"price": 19.0, "role": "support", "note": ""}, {"price": 22.0, "role": "resistance", "note": ""}]

def test_fsly_after_hours_is_weak():
    assert ru.classify(17.61, SUPL)[0] == "Weak" and ru.classify(17.61, SUPL)[1]["price"] == 19.0

@pytest.mark.parametrize("px,sec", [
    (19.0, "At a level"), (19.08, "At a level"), (18.97, "At a level"),   # on support, within tolerances
    (18.94, "Weak"),                                                      # 0.32% under support > BREAK_TOL
    (22.10, "At a level"), (22.2, "Triggered / working"),                 # just over resistance vs cleared it
    (20.5, "In range / no change")])
def test_classify_tolerances(px, sec):
    assert ru.classify(px, SUPL)[0] == sec

def mk_levels(root, levels=SUPL):
    d = root / "week_1102"; d.mkdir(exist_ok=True)
    levels_io.write_levels(str(d / "levels.json"), {"schema_version": 1, "week_of": "2026-11-02", "thread_url": None, "generated_at": "x",
                           "tickers": [{"symbol": "FSLY", "levels": levels}, {"symbol": "SPY", "levels": []}]})
    return str(d / "levels.json")

def snap(path, fsly, fsly_reg=None, ext=None):
    row = {"symbol": "FSLY", "last": fsly, "price_basis": "extended" if ext is not None else "regular", "regular_price": fsly_reg or fsly,
           "change_pct": 0.0, "ext_change_pct": ext}
    path.write_text(json.dumps({"generated_at": "2026-11-04T20:00:00-05:00", "tickers": [row, {"symbol": "SPY", "last": 766.62, "regular_price": 766.62, "change_pct": 0.0}]}))
    return str(path)

def RU(root, *a):
    p = subprocess.run([sys.executable, f"{P}/render_update.py", *a], env={**os.environ, "NDTL_PIPELINE_ROOT": str(root)}, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr

def test_render_change_then_no_change(tmp_path):
    lv = mk_levels(tmp_path); ec = tmp_path / "e.md"; ec.write_text("| FSLY | unconfirmed | 11/04/26 AMC | this week | Nasdaq |\n")
    nf = tmp_path / "n.json"; nf.write_text(json.dumps({"FSLY": "reported tonight on earnings"}))
    s1 = snap(tmp_path / "a.json", 21.04)
    c, o, e = RU(tmp_path, "--levels", lv, "--snapshot", s1, "--date", "2026-11-04", "--time", "1530", "--out", str(tmp_path / "u1.md"), "--earnings", str(ec))
    assert c == 0 and os.path.exists(tmp_path / "snapshots/2026-11-04/1530.json")
    s2 = snap(tmp_path / "b.json", 17.61, 21.04, -16.3)
    c, o, e = RU(tmp_path, "--levels", lv, "--snapshot", s2, "--session", "extended", "--date", "2026-11-04", "--time", "2000",
                 "--out", str(tmp_path / "u2.md"), "--notes", str(nf), "--earnings", str(ec))
    summ = json.loads(o); md = (tmp_path / "u2.md").read_text()
    assert c == 0 and summ["changed_section"] == [{"symbol": "FSLY", "from": "In range / no change", "to": "Weak"}]
    assert summ["crossed"][0]["crossings"] == [{"level": 19.0, "role": "support", "direction": "down"}]
    assert md.startswith("**Wed 11/4 8 PM after-hours update (~8 PM ET, extended hours)**\nJason's 11/2 plan levels.")
    assert "**Weak**\n\u2022 **FSLY** 17.61 (21.04, \u221216.3% after hours): changed: reported tonight on earnings; under 19 support; 16 support next; reported tonight after the close" in md
    assert "\u2022 **SPY** 766.62 (" in md and "Since 3:30 PM: FSLY in range to weak; FSLY down through 19." in md
    c, o, e = RU(tmp_path, "--levels", lv, "--snapshot", s2, "--session", "extended", "--date", "2026-11-04", "--time", "2030", "--out", str(tmp_path / "u3.md"))
    assert c == 10 and json.loads(o)["no_change"] and not os.path.exists(tmp_path / "u3.md")

def test_render_fetch_via_prices_fixture_and_split(tmp_path):
    many = [{"symbol": f"T{i:02d}", "levels": SUPL} for i in range(70)]
    d = tmp_path / "week_1102"; d.mkdir()
    levels_io.write_levels(str(d / "levels.json"), {"schema_version": 1, "week_of": "2026-11-02", "thread_url": None, "generated_at": "x", "tickers": many})
    one = {"meta": {"regularMarketPrice": 20.5, "chartPreviousClose": 20.0, "regularMarketTime": 1, "currentTradingPeriod": {"regular": {"start": 100, "end": 200}}},
           "timestamp": [150], "indicators": {"quote": [{"close": [20.5]}]}}
    (tmp_path / "fx.json").write_text(json.dumps({t["symbol"]: one for t in many}))
    c, o, e = RU(tmp_path, "--fixture", str(tmp_path / "fx.json"), "--date", "2026-11-04", "--time", "1100", "--out", str(tmp_path / "u.md"), "--earnings", "")
    s = json.loads(o)
    assert c == 0 and len(s["files"]) == 2 and s["slots"] == ["2026-11-04_1100", "2026-11-04_1100b"]
    assert all(len(open(f).read().strip()) <= 2000 for f in s["files"]) and os.path.exists(tmp_path / "snapshots/2026-11-04/1100.json")

# ---------- post_earnings ----------
import hashlib
def chart(tmp_path, out="x_call_v3.png", body=b"\x89PNGv3", check="Result: **PASS**", ok_sha=None, ok=True):
    d = tmp_path / "earn" / "XYZ-2026-11-03"; (d / "review_ok").mkdir(parents=True)
    (d / "x_call_v3.png").write_bytes(body); (d / "claims.json").write_text(json.dumps({"output": out}))
    time.sleep(0.01); (d / "claims_check.md").write_text(f"# claims_check: XYZ → XYZ-2026-11-03/x_call_v3.png\n\n{check}\n- OK: a\n")
    if ok: (d / "review_ok/x_call_v3.png.ok").write_text(json.dumps({"image": "x_call_v3.png", "sha256": ok_sha or hashlib.sha256(body).hexdigest(), "reviewer": "Manager Bot", "reviewed_at": "2026-11-04T21:00:00-05:00"}))
    cap = tmp_path / "cap.md"; cap.write_text("XYZ call chart"); return str(d / "x_call_v3.png"), str(cap)

def PE(tmp_path, img, cap, *extra):
    env = {**os.environ, "NDTL_EARNINGS_ROOT": str(tmp_path / "earn"), "NDTL_PIPELINE_ROOT": str(tmp_path / "pipe"), "NDTL_WEBHOOK_URL": FAKE, "NDTL_DISCORD_CONFIG": str(tmp_path / "none.json")}
    p = subprocess.run(["bash", f"{P}/post_earnings.sh", "XYZ", img, cap, TURL, "earnings_test_XYZ", *extra], env=env, capture_output=True, text=True)
    return p.returncode, p.stdout

def test_earnings_missing_ok(tmp_path):
    img, cap = chart(tmp_path, ok=False); c, o = PE(tmp_path, img, cap, "--dry-run"); assert c == 20 and "refused" in o

def test_earnings_sha_mismatch_v3_image_v2_ok(tmp_path):
    img, cap = chart(tmp_path, ok_sha=hashlib.sha256(b"\x89PNGv2").hexdigest()); c, o = PE(tmp_path, img, cap, "--dry-run"); assert c == 21 and "sha256" in o

@pytest.mark.parametrize("kw", [{"check": "Result: **2 FAIL**\n- FAIL: price"}, {"out": "x_call_v2.png"}])
def test_earnings_failed_claims(tmp_path, kw):
    img, cap = chart(tmp_path, **kw); c, o = PE(tmp_path, img, cap, "--dry-run"); assert c == 22

def test_earnings_pass_dry_run(tmp_path):
    img, cap = chart(tmp_path); c, o = PE(tmp_path, img, cap, "--dry-run")
    r = json.loads(o.strip().splitlines()[-1])
    assert c == 0 and r["status"] == "posted" and r["http_status"] == "dry-run" and "/dryrun/" in r["receipt"]
    rc = json.load(open(r["receipt"])); assert rc["dry_run"] and rc["attachment"]["filename"] == "x_call_v3.png" and rc["slot"] == "earnings_test_XYZ"


# ---------- weekly candle ----------
import datetime as _dt
from zoneinfo import ZoneInfo as _ZI
def _ts(d): return int(_dt.datetime.fromisoformat(d + "T09:30").replace(tzinfo=_ZI("America/New_York")).timestamp())

def daily(rows):  # rows: (date, o, h, l)
    return {"timestamp": [_ts(r[0]) for r in rows], "indicators": {"quote": [{"open": [r[1] for r in rows], "high": [r[2] for r in rows], "low": [r[3] for r in rows], "close": [r[1] for r in rows]}]}}

ONE_MIN = lambda px: {"meta": {"regularMarketPrice": px, "chartPreviousClose": px, "regularMarketTime": 1, "currentTradingPeriod": {"regular": {"start": 100, "end": 200}}},
                      "timestamp": [150], "indicators": {"quote": [{"close": [px]}]}}

def test_parse_week_uses_monday_open_and_session_price():
    d = daily([("2026-10-30", 10, 11, 9), ("2026-11-02", 20, 21, 19.5), ("2026-11-03", 20.5, 22, 20), ("2026-11-04", 21, 21.5, 20.8)])
    w = prices.parse_week(d, _dt.date(2026, 11, 4), 23.0)
    assert w == {"week_start": "2026-11-02", "week_open": 20, "week_high": 23.0, "week_low": 19.5, "week_pct": 15.0, "color": "green"}

def test_render_green_red_and_failed_week(tmp_path):
    d = tmp_path / "week_1102"; d.mkdir()
    lv = [{"price": 50.0, "role": "support", "note": ""}]
    levels_io.write_levels(str(d / "levels.json"), {"schema_version": 1, "week_of": "2026-11-02", "thread_url": None, "generated_at": "x",
        "tickers": [{"symbol": s, "levels": lv} for s in ("GRN", "RED", "BAD")]})
    fx = {"GRN": ONE_MIN(107.8), "RED": ONE_MIN(97.9), "BAD": ONE_MIN(80.0),
          "GRN@1d": daily([("2026-11-02", 100, 105, 99)]), "RED@1d": daily([("2026-11-02", 100, 101, 97)])}  # no BAD@1d -> fetch fails
    (tmp_path / "fx.json").write_text(json.dumps(fx))
    c, o, e = RU(tmp_path, "--fixture", str(tmp_path / "fx.json"), "--date", "2026-11-04", "--time", "1100", "--out", str(tmp_path / "u.md"), "--earnings", "")
    md = (tmp_path / "u.md").read_text()
    assert c == 0
    assert "\u2022 **GRN** 107.80 (flat): over 50. Green wk +7.8%." in md
    assert "\u2022 **RED** 97.90 (flat): over 50. Red wk \u22122.1%." in md
    bad = [l for l in md.splitlines() if "**BAD**" in l][0]
    assert bad == "\u2022 **BAD** 80.00 (flat): over 50" and " wk" not in bad
    snap = json.load(open(tmp_path / "snapshots/2026-11-04/1100.json"))
    w = {r["symbol"]: r["week"] for r in snap["tickers"]}
    assert w["GRN"]["week_open"] == 100 and w["GRN"]["week_high"] == 107.8 and w["RED"]["week_low"] == 97 and "error" in w["BAD"]
