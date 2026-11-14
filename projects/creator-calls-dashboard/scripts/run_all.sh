#!/usr/bin/env bash
# Refresh prices, scores, and insights. No bot needed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 scripts/fetch_prices.py
python3 scripts/score.py
python3 scripts/analyze.py
echo "Done. Serve with ./serve.sh and refresh the browser."
