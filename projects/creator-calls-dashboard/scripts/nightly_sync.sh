#!/usr/bin/env bash
# Nightly refresh for a local/Windows copy of the dashboard.
#   nightly_sync.sh          -> check source freshness, run run_all.sh, stage changed data/*.json in .sync/, print their paths
#   nightly_sync.sh --mark   -> record staged files as copied (call after every copy succeeded)
#
# Mentions source defaults to the sibling youtube-ticker-tracker data file.
# Override with MENTIONS_JSON=/path/to/mentions.json if yours lives elsewhere.
set -uo pipefail
D="$(cd "$(dirname "$0")/.." && pwd)"; S=$D/.sync; H=$D/.synced_hashes
SRC="${MENTIONS_JSON:-../youtube-ticker-tracker/data/mentions.json}"
mkdir -p "$S"; touch "$H"
if [ "${1:-}" = "--mark" ]; then
  for f in "$S"/*.json; do [ -e "$f" ] || continue; n=$(basename "$f")
    grep -v "  $n\$" "$H" > "$H.tmp"; (cd "$S" && sha256sum "$n") >> "$H.tmp"; mv "$H.tmp" "$H"; done
  rm -f "$S"/*.json; echo "MARKED"; exit 0
fi
age_h=$(( ( $(date +%s) - $(stat -Lc %Y "$SRC") ) / 3600 ))
echo "SOURCE_AGE_HOURS=$age_h"
[ "$age_h" -gt 26 ] && echo "WARN_SOURCE_STALE"
cd "$D" && ./scripts/run_all.sh > "$D/.last_run.log" 2>&1 || { echo "FAIL_RUN_ALL (see $D/.last_run.log)"; tail -5 "$D/.last_run.log"; exit 1; }
rm -f "$S"/*.json
for f in "$D"/data/*.json; do n=$(basename "$f"); h=$(sha256sum < "$f" | cut -d' ' -f1)
  grep -q "^$h  $n\$" "$H" || { cp -L "$f" "$S/$n"; echo "CHANGED $S/$n"; }; done
echo "DONE"
