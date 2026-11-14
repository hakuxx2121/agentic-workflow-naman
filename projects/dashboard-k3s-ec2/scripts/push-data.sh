#!/usr/bin/env bash
# Publish the Creator Calls dashboard to S3 (the k3s pod pulls it from there every 10 minutes).
#
#   push-data.sh --bucket NAME               nightly: the 4 data/*.json files only
#   push-data.sh --bucket NAME --with-site   also index.html, css/, js/, vendor/ (first deploy, or after a UI change)
#
# Options:
#   --src DIR          dashboard folder (default ${DASHBOARD_SRC:-../creator-calls-dashboard})
#   --prefix P         key prefix in the bucket (default site/, must match terraform output data_prefix)
#   --keep-holdings    DON'T strip the "My holdings" ticker list from the public build (default: strip)
#   --dryrun           show what would upload, change nothing
#
# Credentials: the `dashboard-publisher` AWS profile (override with AWS_PROFILE). Never pass keys as arguments.
# Only allow-listed files are published: v1/, scripts/, README, screenshots, logs and dotfiles never leave the box.
set -euo pipefail

SRC="${DASHBOARD_SRC:-../creator-calls-dashboard}"
BUCKET=""
PREFIX="site/"
WITH_SITE=0
KEEP_HOLDINGS=0
DRYRUN=()
AWS="${AWS_BIN:-aws}"
export AWS_PROFILE="${AWS_PROFILE:-dashboard-publisher}"
HERE="$(cd "$(dirname "$0")" && pwd)"

DATA_FILES=(mentions.json scores.json insights.json prices.json)
SITE_ITEMS=(index.html css js vendor)

die() { echo "push-data: $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --bucket) BUCKET="$2"; shift 2 ;;
    --src) SRC="$2"; shift 2 ;;
    --prefix) PREFIX="$2"; shift 2 ;;
    --with-site) WITH_SITE=1; shift ;;
    --keep-holdings) KEEP_HOLDINGS=1; shift ;;
    --dryrun) DRYRUN=(--dryrun); shift ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) die "unknown option $1" ;;
  esac
done
[ -n "$BUCKET" ] || die "--bucket is required (terraform output -raw bucket_name)"
case "$PREFIX" in */) ;; *) PREFIX="$PREFIX/" ;; esac
DEST="s3://${BUCKET}/${PREFIX}"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/data"

# 1. Data: copy (dereferencing symlinks, keeping mtimes so unchanged files aren't re-uploaded) and validate.
for f in "${DATA_FILES[@]}"; do
  [ -f "$SRC/data/$f" ] || die "missing $SRC/data/$f"
  cp -pL "$SRC/data/$f" "$STAGE/data/$f"
  python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$STAGE/data/$f" || die "$f is not valid JSON; not publishing"
done

# 2. Site (optional), with the holdings view stripped by default.
if [ "$WITH_SITE" -eq 1 ]; then
  for i in "${SITE_ITEMS[@]}"; do
    [ -e "$SRC/$i" ] || die "missing $SRC/$i"
    cp -pRL "$SRC/$i" "$STAGE/$i"
  done
  if [ "$KEEP_HOLDINGS" -eq 0 ]; then
    # Public config: same data paths, empty holdings, no comments.
    cat > "$STAGE/js/config.js" <<'JS'
window.DASHBOARD_CONFIG = {
  dataUrl: "./data/mentions.json",
  scoresUrl: "./data/scores.json",
  insightsUrl: "./data/insights.json",
  pricesUrl: "./data/prices.json",
  holdings: []
};
JS
    # v2.js also hard-codes the list as a fallback default: blank it in the COPY (source untouched).
    sed -i -E 's/holdings: *\[[^]]*\]/holdings: []/' "$STAGE/js/v2.js"
    # Hide the "My holdings" button (kept in the DOM so v2.js's reset handler still finds it).
    sed -i 's/id="holdings"/id="holdings" hidden/' "$STAGE/index.html"
    # Keep source mtimes so a nightly --with-site doesn't re-upload unchanged files.
    touch -r "$SRC/js/config.js" "$STAGE/js/config.js"
    touch -r "$SRC/js/v2.js" "$STAGE/js/v2.js"
    touch -r "$SRC/index.html" "$STAGE/index.html"
  fi
fi

# 3. Safety net: refuse to publish anything the public-exposure audit flags.
if [ "$KEEP_HOLDINGS" -eq 0 ]; then
  "$HERE/audit-public.sh" "$STAGE" --strict
else
  echo "push-data: --keep-holdings set; skipping the strict audit" >&2
fi

# 4. Upload. Data: always revalidate. Site: short cache. (nginx sets its own browser headers;
#    these S3 headers matter if you later put CloudFront in front of S3.)
"$AWS" s3 sync "$STAGE/data" "${DEST}data" --delete --no-progress \
  --content-type application/json --cache-control "no-cache" "${DRYRUN[@]}"

if [ "$WITH_SITE" -eq 1 ]; then
  # --exclude keeps this pass from touching data/ (excluded keys are never deleted).
  "$AWS" s3 sync "$STAGE" "$DEST" --delete --no-progress --exclude "data/*" \
    --cache-control "public, max-age=300" "${DRYRUN[@]}"
fi

echo "push-data: done -> ${DEST} (site: $([ "$WITH_SITE" -eq 1 ] && echo yes || echo no), holdings stripped: $([ "$KEEP_HOLDINGS" -eq 0 ] && echo yes || echo no))"
