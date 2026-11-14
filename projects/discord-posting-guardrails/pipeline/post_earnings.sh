#!/usr/bin/env bash
# post_earnings.sh <TICKER> <image.png> <caption_file.md> <thread_url> <slot> [--dry-run]  (see post_earnings.py)
exec python3 "$(dirname "$0")/post_earnings.py" "$@"
