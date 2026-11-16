# Operations

Run everything from the repo root. Paths in `config.toml` (`data/...`) are relative to it.

## Setup (once)

    python3 -m venv .venv && source .venv/bin/activate     # Python 3.11+ (uses tomllib)
    pip install -r requirements.txt
    pytest                                                  # all tests, no network
    python -m bmwcpo.run --dry-run                          # config check, no network

Settings for one machine only go in `config.local.toml` (git-ignored, merged on top of
`config.toml`). See [searches.md](searches.md#machine-specific-changes-configlocaltoml).

## Commands

| Command | What it does | Requests to BMW |
|---|---|---|
| `python -m bmwcpo.run` | Run every enabled search, alert on changes, write `data/last_run.json` | ~1 per 100 cars per search (0 if cached) |
| `python -m bmwcpo.run --dry-run` | Validate the config and print each request body. **No network, no writes.** | 0 |
| `python -m bmwcpo.run --search NAME` | Run one search, even a disabled one | same as above |
| `python -m bmwcpo.run --json` | Print the JSON report instead of text | — |
| `python -m bmwcpo.facets [--search NAME] [--only F ...]` | Show filter values and counts for tuning | 1 |
| `python -m bmwcpo.auth [--force]` | Token status, or force a refresh; never prints the token | 0 or 1 |
| `scripts/daily.sh` | `bmwcpo.run`, plus append the summary to `data/daily.log` | same as run |
| `scripts/save_auth.sh` | Manual token fallback (see Troubleshooting) | 0 |

### Exit codes

| Code | `status` | Meaning |
|---|---|---|
| 0 | `ok` | Ran cleanly. There may still be alerts (new matches, price drops). |
| 1 | `warning` | Finished, but with a health warning (e.g. 0 results, sharp drop) |
| 2 | `error` | A search or the whole run failed (token, HTTP, config, crash) |

### Text output

```
[g20-msport-dap-pro] 79 cars, 1 request(s), 5 matches (1 new, 1 price drops, 0 gone)
  NEW MATCH   [g20-msport-dap-pro] 2025 330i xDrive Brooklyn Grey Metallic | $43,383 | 2,191 mi | dealer 40713-01 | 2460 mi away | VIN | URL
  PRICE DROP  [g20-msport-dap-pro] $36,888 -> $35,888 (-$1,000) 2023 330e Portimao Blue Metallic | ...
  GONE        [g20-msport-dap-pro] no longer listed (sold or changed): ...
  HEALTH WARNING [zero-test] 0 cars returned; filters may be too narrow or the API changed
status=ok requests=1 alerts=2
```

### JSON report (`data/last_run.json`)

Written on every real run, including failed ones. Its structure and how an agent should act
on it are in [AGENTS.md](../AGENTS.md). Past reports are in the `runs` table.

## Useful queries

All current matches, across searches:

    sqlite3 -header -column data/bmwcpo.sqlite "select h.search, l.vin, l.year, l.model, l.color_name, l.price, l.mileage, l.dealer, round(h.distance) mi from search_hits h join listings l using(vin) where h.is_match=1 and h.active=1 order by h.search, h.distance"

Price history of matching cars:

    sqlite3 data/bmwcpo.sqlite "select vin, price, datetime(seen_at,'unixepoch','localtime') from price_history where vin in (select vin from search_hits where is_match=1) order by vin, seen_at"

Recent runs:

    sqlite3 -header -column data/bmwcpo.sqlite "select id, datetime(started_at,'unixepoch','localtime') at, status, requests from runs order by id desc limit 10"

## Daily schedule

### Option A: an AI agent (Muse, Grokbot, ...)

Give it [AGENTS.md](../AGENTS.md). It covers setup, the daily command, which alerts to send and
the health checks to run.

### Option B: launchd on the Mac

[`scripts/com.asadshahid.bmwcpo-watch.plist`](../scripts/com.asadshahid.bmwcpo-watch.plist)
runs `scripts/daily.sh` every day at 9:17 am, or on wake if the Mac was asleep. This only
logs; it doesn't notify you.

    cp scripts/com.asadshahid.bmwcpo-watch.plist ~/Library/LaunchAgents/
    launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.asadshahid.bmwcpo-watch.plist

Remove it with `launchctl bootout gui/$(id -u)/com.asadshahid.bmwcpo-watch`, then delete the
plist file.

**Caveat:** macOS privacy protection can block launchd jobs from reading `~/Desktop`. If
`data/launchd.err` says "Operation not permitted", move the repo out of `~/Desktop` and update
the plist paths.

Don't run both A and B against the same `data/` folder. Each would see the other's changes as
already known.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `token endpoint returned HTTP 401` (or 403) | BMW rotated the website credential | Search the `bmwusa-universal-inventory...min.js` bundle for `token/cpo`, copy the new `Basic ...` value into `[token] client_auth`. Meanwhile, use the manual fallback. |
| `inventory API rejected the token (HTTP 401/403)` | The API changed its authentication | Compare a fresh DevTools capture of the `vehicle` POST with `config.toml` |
| `0 cars returned` | Filter value misspelled, or the API changed | `python -m bmwcpo.facets --search NAME` and compare values |
| `filter 'X' is not a known API facet` | Typo in a filter name | See [searches.md](searches.md) for the names |
| `fetched N of M cars` | More cars than `max_pages × page_size` | Raise `[api] max_pages`, or narrow the filters |
| `lack option codes, color or price` | The API response shape changed | Check `[fields]` against a raw vehicle in `listings.raw_json` |
| `token request failed: ConnectionError` | No network, or a proxy blocks bmwusa.com | Check connectivity from that machine |
| `token endpoint returned HTTP 411` | The token POST went out with no body | Pull the latest code: `auth.py` sends a 1-byte body |
| `git pull --ff-only` refuses (local changes) | Tracked files were edited on that machine | `git stash`, then pull. Keep machine-specific settings in `config.local.toml`. |

**Manual token fallback:** run `scripts/save_auth.sh`. It opens the CPO page in Chrome, walks
you through copying the `Authorization` request header from DevTools, and saves it to
`data/auth.txt`. A valid saved token is used until it expires.

## Security

- The token lives only in `data/auth.txt` (mode 600, git-ignored) or `BMW_AUTH`. It never
  appears in output, logs, reports or errors. To see its expiry, run `python -m bmwcpo.auth`.
- `[token] client_auth` in `config.toml` is BMW's public website credential, not a personal
  secret.
- HAR exports contain tokens and are git-ignored (`*.har`).
