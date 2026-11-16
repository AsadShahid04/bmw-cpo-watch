#!/bin/bash
# Scheduled run for launchd / cron / an agent.
# Runs every enabled search (the watcher refreshes its own API token), then appends the
# compact text summary to data/daily.log with a timestamp. The full machine-readable
# report is always in data/last_run.json. Never logs the token.
#
# Exit code is the watcher's: 0 = ok, 1 = finished with health warnings, 2 = failed.

set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY="$REPO/.venv/bin/python"
LOG="$REPO/data/daily.log"
cd "$REPO" || exit 2
mkdir -p data

ts="$(date '+%Y-%m-%d %H:%M')"
out="$("$PY" -m bmwcpo.run 2>&1)"
code=$?
{
  echo "== $ts exit=$code"
  printf '%s\n' "$out"
} >> "$LOG"
exit "$code"
