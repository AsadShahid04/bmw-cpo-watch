# Operations

Run everything from the repo root. Paths in `config.toml` (`data/...`) are relative to it.

## Setup (once)

    python3 -m venv .venv && source .venv/bin/activate     # Python 3.11+ (uses tomllib)
    pip install -r requirements.txt
    pytest                                                  # 18 tests, no network

## Commands

| Command | What it does |
|---|---|
| `python -m bmwcpo.run` | Full run: token, about 11 inventory pages, match, store, print |
| `python -m bmwcpo.auth` | Check the cached token and refresh it only if needed; prints the expiry, never the token |
| `python -m bmwcpo.auth --force` | Always fetch a new token |
| `scripts/daily.sh` | Same as `bmwcpo.run`, but appends only counts, new matches and errors to `data/daily.log` |
| `scripts/save_auth.sh` | Manual fallback if the token endpoint ever breaks (see Troubleshooting) |

### Reading the output

    seen=1078 new_matches=0 no_longer_listed=2

- `seen`: listings returned this run (nationwide CPO 3 Series)
- `new_matches`: matching VINs never seen before, each printed as a `NEW MATCH` line
- `no_longer_listed`: VINs that were active last run and are gone now (sold or delisted)

Already-known matches don't print again. To list all current matches:

    sqlite3 -header -column data/bmwcpo.sqlite "select vin, year, model, color_name, price, mileage, dealer, round(dealer_distance) mi from listings where is_match=1 and active=1 order by dealer_distance"

Price drops on matches:

    sqlite3 data/bmwcpo.sqlite "select vin, price, datetime(seen_at,'unixepoch','localtime') from price_history where vin in (select vin from listings where is_match=1) order by vin, seen_at"

## Daily schedule

### Option A: launchd on the Mac

[`scripts/com.asadshahid.bmwcpo-watch.plist`](../scripts/com.asadshahid.bmwcpo-watch.plist)
runs `scripts/daily.sh` every day at 9:17 am. If the Mac is asleep then, it runs on wake.

    cp scripts/com.asadshahid.bmwcpo-watch.plist ~/Library/LaunchAgents/
    launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.asadshahid.bmwcpo-watch.plist
    launchctl kickstart gui/$(id -u)/com.asadshahid.bmwcpo-watch      # optional: run once now

Remove it:

    launchctl bootout gui/$(id -u)/com.asadshahid.bmwcpo-watch
    rm ~/Library/LaunchAgents/com.asadshahid.bmwcpo-watch.plist

**Caveat:** macOS privacy protection can stop launchd jobs from reading `~/Desktop`. If
`data/launchd.err` shows "Operation not permitted", move the repo out of `~/Desktop` (for
example to `~/CodingFiles`) and update the two paths in the plist.

### Option B: an AI agent

Give the agent [AGENTS.md](../AGENTS.md). The agent's machine needs the same setup, outbound
HTTPS to `www.bmwusa.com` and `inventoryservices.bmwdealerprograms.com`, and a `data/`
folder that survives between runs.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `error: token endpoint returned HTTP 401` (or 403) | BMW rotated the client credential or locked the endpoint | Find the new credential in the bundle (see [api-reference.md](api-reference.md)). Until then, use the manual fallback below. |
| `401/403` from `inventoryservices...` even after a refresh | The inventory API now wants something else (cookies, a new header) | Compare a fresh DevTools capture of the `vehicle` POST with `config.toml` |
| `seen=0` | Request body or filters changed | Same as above; try `includeFacets: true` |
| `token request failed: ConnectionError` | No network, or a proxy blocks bmwusa.com | Check connectivity from that machine |
| A rerun shows the same counts instantly | Pages are cached for 1 hour | Expected. Lower `cache_ttl_seconds` only for testing. |

**Manual fallback:** run `scripts/save_auth.sh`. It opens the CPO page in Chrome and walks you
through copying the `Authorization` request header from DevTools (Network → `vehicle` POST →
Headers → Request Headers → right-click → Copy value). Then it saves the clipboard to
`data/auth.txt`. Set `auto_refresh = false` in `config.toml` so the watcher doesn't overwrite it.

## Security

- The token lives only in `data/auth.txt` (mode 600, git-ignored) or the `BMW_AUTH` env var.
  Don't `cat` it. Use `python -m bmwcpo.auth` to see its expiry.
- The `[token] client_auth` value in `config.toml` is BMW's public website credential, not a
  personal secret. The repo is private, so committing it is low risk.
- HAR exports contain tokens and are git-ignored (`*.har`).
