#!/bin/sh
# Pull the published site + data from S3 into the shared emptyDir, then flip a symlink so nginx
# switches to the new copy in one step (no half-written prices.json served mid-sync).
#
#   /srv/stage            incremental mirror of s3://$BUCKET/$PREFIX  (aws s3 sync target)
#   /srv/releases/<ts>    immutable snapshot nginx serves
#   /srv/live -> releases/<ts>
#
# Credentials: none here. The AWS CLI picks up the EC2 instance role through IMDSv2.
# Usage: sync.sh --once   (init container)    sync.sh   (sidecar loop)
set -eu

: "${BUCKET:?BUCKET not set}"
PREFIX="${PREFIX:-site/}"
ROOT="${SITE_ROOT:-/srv}"
INTERVAL="${INTERVAL:-600}"
AWS="${AWS_BIN:-aws}"
HEARTBEAT="${HEARTBEAT_FILE:-/tmp/heartbeat}"
SRC="s3://${BUCKET}/${PREFIX}"
STAGE="$ROOT/stage"

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }

publish() {
  ts="$(date +%s)"
  new="$ROOT/releases/$ts"
  [ -e "$new" ] && new="${new}-$$"
  mkdir -p "$new"
  cp -a "$STAGE/." "$new/"
  echo "ok $(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$new/healthz.txt"
  ln -sfn "releases/$(basename "$new")" "$ROOT/live.tmp"
  mv -Tf "$ROOT/live.tmp" "$ROOT/live"
  # Keep the new release and the one before it (in-flight requests may still read it).
  keep_prev=""
  for d in $(ls -1 "$ROOT/releases" | sort -r); do
    if [ "$ROOT/releases/$d" = "$new" ]; then continue; fi
    if [ -z "$keep_prev" ]; then keep_prev="$d"; continue; fi
    rm -rf "${ROOT:?}/releases/$d"
  done
  log "published $(basename "$new")"
}

sync_once() {
  mkdir -p "$STAGE" "$ROOT/releases"
  # Output lists every download/delete; empty output = nothing changed.
  out="$("$AWS" s3 sync "$SRC" "$STAGE" --delete --no-progress --exact-timestamps)" || return 1
  if [ -n "$out" ]; then echo "$out"; fi
  if [ ! -f "$STAGE/index.html" ]; then
    log "WARN: $SRC has no index.html yet (run push-data.sh --with-site)"
    return 1
  fi
  if [ -n "$out" ] || [ ! -L "$ROOT/live" ]; then publish; else log "no changes"; fi
  date +%s > "$HEARTBEAT"
}

if [ "${1:-}" = "--once" ]; then
  # Init container: retry until the first copy exists so nginx never starts empty.
  n=0
  until sync_once; do
    n=$((n + 1))
    [ "$n" -ge 30 ] && { log "giving up after $n tries"; exit 1; }
    log "sync failed (try $n), retrying in 10s"
    sleep 10
  done
  exit 0
fi

while true; do
  sleep "$INTERVAL"
  sync_once || log "sync failed; keeping the current copy"
done
