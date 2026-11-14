#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PORT="${1:-8000}"
echo "Creator Calls · Ticker Timeline: http://localhost:${PORT}/"
echo "Previous dashboard: http://localhost:${PORT}/v1/"
echo "Ctrl-C to stop."
exec python3 -m http.server "$PORT"
