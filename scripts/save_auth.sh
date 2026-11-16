#!/usr/bin/env bash
# Save the BMW inventory API Authorization header to data/auth.txt.
#
# Opens the CPO search page in Chrome, waits while you copy the header from
# DevTools, then writes the clipboard to data/auth.txt (mode 600) and clears
# the clipboard. The value is never printed.
#
# Usage:  scripts/save_auth.sh             # interactive (opens Chrome, reads clipboard)
#         scripts/save_auth.sh --stdin     # read the value from stdin instead
#
# Env:    BMW_AUTH_FILE  override output path (default: <repo>/data/auth.txt)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AUTH_FILE="${BMW_AUTH_FILE:-$REPO_ROOT/data/auth.txt}"
URL="https://www.bmwusa.com/certified-preowned-search/results"

if [[ "${1:-}" == "--stdin" ]]; then
  raw="$(cat)"
else
  open -a "Google Chrome" "$URL" 2>/dev/null || open "$URL"
  cat <<'EOF'
In the Chrome tab that just opened:
  1. Cmd+Option+I  ->  Network tab  ->  type "vehicle" in the filter box
  2. Cmd+R to reload
  3. Click the POST to inventoryservices.bmwdealerprograms.com/vehicle
  4. Headers -> Request Headers -> right-click "Authorization" -> Copy value
EOF
  read -r -p "Press Enter once it's copied... " _
  raw="$(pbpaste)"
fi

# Trim whitespace/newlines; tolerate a copied "Authorization: ..." line.
value="$(printf '%s' "$raw" | tr -d '\r\n' | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//; s/^[Aa]uthorization:[[:space:]]*//')"

if [[ -z "$value" ]]; then
  echo "error: clipboard is empty; nothing saved" >&2
  exit 1
fi
if (( ${#value} < 20 )); then
  echo "error: copied value is too short to be the header; nothing saved" >&2
  exit 1
fi

mkdir -p "$(dirname "$AUTH_FILE")"
umask 077
tmp="$(mktemp "$(dirname "$AUTH_FILE")/.auth.XXXXXX")"
printf '%s\n' "$value" > "$tmp"
mv -f "$tmp" "$AUTH_FILE"
chmod 600 "$AUTH_FILE"

[[ "${1:-}" == "--stdin" ]] || pbcopy < /dev/null   # clear the clipboard
echo "auth saved"
