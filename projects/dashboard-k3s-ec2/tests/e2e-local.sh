#!/usr/bin/env bash
# Offline end-to-end test of the data path, no AWS, no cluster:
#   push-data.sh (real dashboard files) -> fake S3 -> sync.sh (the chart's sidecar script) -> nginx with the chart's config
# Needs: python3, curl, an nginx binary (NGINX_BIN=/path/to/nginx; any 1.2x+ build).
set -euo pipefail
LAB="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${SRC:-../creator-calls-dashboard}"
NGINX_BIN="${NGINX_BIN:-nginx}"
HELM="${HELM:-helm}"
PORT="${PORT:-18080}"
W="$(mktemp -d)"; trap 'kill $(cat "$W/nginx.pid" 2>/dev/null) 2>/dev/null || true; rm -rf "$W"' EXIT
export FAKE_S3_ROOT="$W/s3" AWS_BIN="$LAB/tests/fake-aws"
mkdir -p "$FAKE_S3_ROOT"
pass=0; fail=0
ok()   { echo "PASS  $*"; pass=$((pass+1)); }
bad()  { echo "FAIL  $*"; fail=$((fail+1)); }
check(){ local d="$1"; shift; if "$@" >/dev/null 2>&1; then ok "$d"; else bad "$d"; fi; }

cp "$SRC/js/config.js" "$W/config.js.bak"
echo "== 1. push-data.sh --with-site (holdings stripped by default)"
"$LAB/scripts/push-data.sh" --bucket test-bucket --src "$SRC" --with-site | tail -1
B="$FAKE_S3_ROOT/test-bucket/site"
check "site + 4 data files uploaded"          test -f "$B/index.html" -a -f "$B/data/prices.json" -a -f "$B/data/mentions.json"
check "publisher profile used"                grep -q '^AWS_PROFILE=dashboard-publisher' "$FAKE_S3_ROOT/calls.log"
check "public config.js has empty holdings"   grep -q 'holdings: \[\]' "$B/js/config.js"
check "public v2.js has no ticker list"       bash -c "! grep -qE 'holdings: *\[ *\"' '$B/js/v2.js'"
check "holdings button hidden"                grep -q 'id="holdings" hidden' "$B/index.html"
check "v1/, scripts/, README, logs NOT published" bash -c "! ls '$B' | grep -qE '^(v1|scripts|README.md|serve.sh|screenshot.*|\.last_run\.log)$'"
check "source config.js untouched"            cmp -s "$SRC/js/config.js" "$W/config.js.bak"
check "strict audit passes on the uploaded tree" "$LAB/scripts/audit-public.sh" "$B" --strict

echo "== 2. second push with no changes uploads nothing"
before=$(wc -l < "$FAKE_S3_ROOT/calls.log")
out="$("$LAB/scripts/push-data.sh" --bucket test-bucket --src "$SRC" --with-site)"
check "idempotent (no upload: lines)" bash -c "! grep -q '^upload:' <<<'$out'"

echo "== 3. sync.sh --once (init container) into an emptyDir stand-in"
export BUCKET=test-bucket PREFIX=site/ SITE_ROOT="$W/srv" HEARTBEAT_FILE="$W/heartbeat"
sh "$LAB/charts/creator-dashboard/files/sync.sh" --once | tail -1
check "live symlink created"  test -L "$W/srv/live"
check "healthz.txt written"   test -f "$W/srv/live/healthz.txt"
check "heartbeat written"     test -s "$W/heartbeat"
first="$(readlink "$W/srv/live")"

echo "== 4. nginx with the chart's rendered config"
"$HELM" template t "$LAB/charts/creator-dashboard" --set sync.bucket=test-bucket \
  | python3 -c 'import sys,yaml
for d in yaml.safe_load_all(sys.stdin):
    if d and d["kind"]=="ConfigMap": print(d["data"]["default.conf"])' \
  | sed -e "s#/srv/live#$W/srv/live#" -e "s#listen 8080;#listen 127.0.0.1:$PORT;#" > "$W/default.conf"
mkdir -p "$W/ngx/logs"
cat > "$W/nginx.conf" <<NGX
pid $W/nginx.pid;
error_log $W/ngx/logs/error.log;
events {}
http {
  types { text/html html; text/css css; application/javascript js; application/json json; text/plain txt; }
  default_type application/octet-stream;
  access_log off;
  client_body_temp_path $W/ngx/cb; proxy_temp_path $W/ngx/p; fastcgi_temp_path $W/ngx/f; uwsgi_temp_path $W/ngx/u; scgi_temp_path $W/ngx/s;
  include $W/default.conf;
}
NGX
"$NGINX_BIN" -e "$W/ngx/logs/error.log" -t -p "$W/ngx" -c "$W/nginx.conf" 2>&1 | tail -1
"$NGINX_BIN" -e "$W/ngx/logs/error.log" -p "$W/ngx" -c "$W/nginx.conf"
sleep 0.5
U="http://127.0.0.1:$PORT"
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
check "GET /healthz = 200"              test "$(code "$U/healthz")" = 200
check "GET / = 200 (index.html)"        test "$(code "$U/")" = 200
check "GET /data/scores.json = 200"     test "$(code "$U/data/scores.json")" = 200
check "data has Cache-Control no-cache" bash -c "curl -sI '$U/data/scores.json' | grep -qi '^cache-control: no-cache'"
check "assets cached 300s"              bash -c "curl -sI '$U/js/v2.js' | grep -qi 'max-age=300'"
check "nosniff header on data too"      bash -c "curl -sI '$U/data/scores.json' | grep -qi '^x-content-type-options: nosniff'"
check "gzip for prices.json"            bash -c "curl -s -H 'Accept-Encoding: gzip' -D- -o /dev/null '$U/data/prices.json' | grep -qi '^content-encoding: gzip'"
check "POST = 405"                      test "$(code -X POST "$U/")" = 405
check "dotfiles = 404"                  test "$(code "$U/.env")" = 404
check "missing file = 404"              test "$(code "$U/v1/")" = 404
check "served config.js has no holdings" bash -c "curl -s '$U/js/config.js' | grep -q 'holdings: \[\]'"

echo "== 5. new nightly data -> next sync flips the symlink atomically"
sleep 1
cp -p "$SRC/data/insights.json" "$W/insights.json"; python3 - "$W/insights.json" <<'PY'
import json,sys; p=sys.argv[1]; d=json.load(open(p)); d["generated_at"]="test-new-run"; json.dump(d,open(p,"w"))
PY
mkdir -p "$W/src2/data"; cp -pL "$SRC"/data/*.json "$W/src2/data/"; cp "$W/insights.json" "$W/src2/data/insights.json"
"$LAB/scripts/push-data.sh" --bucket test-bucket --src "$W/src2" | tail -1
sleep 1
sh "$LAB/charts/creator-dashboard/files/sync.sh" --once | tail -1
second="$(readlink "$W/srv/live")"
check "symlink moved to a new release"  test "$first" != "$second"
check "nginx serves the new data"       bash -c "curl -s '$U/data/insights.json' | grep -q test-new-run"
check "previous release kept for in-flight reads" test -d "$W/srv/$first"
sh "$LAB/charts/creator-dashboard/files/sync.sh" --once | tail -1
check "no-change sync keeps the same release" test "$(readlink "$W/srv/live")" = "$second"

echo; echo "e2e: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
