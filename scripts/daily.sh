#!/bin/bash
# Daily run for launchd / cron / an agent: runs the watcher (which refreshes the API
# token itself when needed) and appends to data/daily.log only:
#   - one line of counts
#   - any NEW MATCH lines
#   - a one-line error if it failed
# Never logs the token. Exit code is the watcher's.

set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY="$REPO/.venv/bin/python"
LOG="$REPO/data/daily.log"
cd "$REPO" || exit 1
mkdir -p data

ts() { date '+%Y-%m-%d %H:%M'; }

out="$("$PY" -m bmwcpo.run 2>&1)"
code=$?
if (( code != 0 )); then
  echo "$(ts) FAILED (exit $code): $(printf '%s' "$out" | tail -1)" >> "$LOG"
  exit "$code"
fi

printf '%s\n' "$out" | grep -E '^seen=' | sed "s/^/$(ts) /" >> "$LOG"
printf '%s\n' "$out" | grep -E 'NEW MATCH' >> "$LOG" || true
