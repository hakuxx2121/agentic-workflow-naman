#!/usr/bin/env bash
# Public-exposure scan: look for things that must not go on a public website.
#   audit-public.sh DIR            report findings (exit 0)
#   audit-public.sh DIR --strict   exit 1 if anything is found (push-data.sh uses this on the staged build)
# Follows symlinks (data/mentions.json is one on the box). Prints file:line: [category] match. Matches are truncated to 120 chars.
set -uo pipefail
DIR="${1:?usage: audit-public.sh DIR [--strict]}"
STRICT="${2:-}"
found=0

scan() { # category, extended-regex, [extra grep args...]
  local cat="$1" re="$2"; shift 2
  local out
  out="$(grep -RnoIE "$@" -- "$re" "$DIR" 2>/dev/null | cut -c1-200)"
  if [ -n "$out" ]; then
    found=1
    while IFS= read -r l; do printf '[%s] %s\n' "$cat" "${l#"$DIR"/}"; done <<<"$out"
  fi
}

scan aws-access-key   '(AKIA|ASIA)[A-Z0-9]{16}'
scan private-key      '-----BEGIN [A-Z ]*PRIVATE KEY-----'
scan token            '(ghp_|gho_|github_pat_)[A-Za-z0-9_]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{35}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.'
scan secret-assign    '(api[_-]?key|secret|passw(or)?d|bearer|auth[_-]?token)["'"'"' ]*[:=] *["'"'"'][^"'"'"']{6,}' -i
scan email            '[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}' --exclude=LICENSE --exclude=NOTICE
scan account-number   '(account|acct|routing|iban)[^0-9]{0,20}[0-9]{8,17}' -i
scan holdings-list    'holdings?["'"'"' ]*[:=] *\[ *["'"'"'][A-Z]'
scan holdings-const   'HOLDINGS *= *\[ *["'"'"'][A-Z]'
scan internal-path    '/workspace/[A-Za-z0-9_./-]+|/home/[a-z][A-Za-z0-9_./-]+|[A-Z]:\\\\Users\\\\[^"'"'"' ]+'
scan personal-name    'naman' -i

if [ "$found" -eq 0 ]; then echo "audit: no findings in $DIR"; fi
if [ "$STRICT" = "--strict" ] && [ "$found" -ne 0 ]; then
  echo "audit: FAILED (strict). Fix or exclude the items above before publishing." >&2
  exit 1
fi
exit 0
