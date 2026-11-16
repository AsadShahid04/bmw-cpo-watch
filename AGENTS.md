# Agent runbook: bmw-cpo-watch

You (Muse, Grokbot, or any other agent) run a personal BMW Certified Pre-Owned watcher for
**Asad**. You run it once a day, read its report, and **alert Asad** about:

- new cars that match one of his searches
- price drops on matching cars
- problems with the watcher itself (health alerts)

The watcher needs no browser and no credentials from Asad. It gets its own short-lived BMW
API token. How it works: [docs/how-it-works.md](docs/how-it-works.md).

## 1. Setup (once per machine)

```bash
git clone https://github.com/AsadShahid04/bmw-cpo-watch && cd bmw-cpo-watch
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # Python 3.11+
.venv/bin/python -m pytest -q                                        # must all pass, no network
.venv/bin/python -m bmwcpo.run --dry-run                             # config check, no network
```

Requirements:
- Outbound HTTPS to `www.bmwusa.com` and `inventoryservices.bmwdealerprograms.com`.
- **A `data/` folder that survives between runs.** It holds the database, so the watcher knows
  what's new. If `data/` is wiped, the next run is just a new baseline. That doesn't spam
  Asad, but it misses one day of changes.
- Run from the repo root.

## 2. Each run (once a day, at a random minute, not on the hour)

```bash
cd bmw-cpo-watch && git pull --ff-only     # pick up Asad's config changes
scripts/daily.sh                           # runs every enabled search; appends to data/daily.log
echo $?                                    # 0 ok, 1 health warning, 2 failed
```

Then read **`data/last_run.json`** and send alerts using section 3. Don't parse the text output
for alerts. The JSON report is the contract.

If you need it, `.venv/bin/python -m bmwcpo.run --json` prints the same report to stdout.

### The report (`data/last_run.json`)

```json
{
  "run_at": "2026-11-16T09:17:03",
  "status": "ok",                  // ok | warning | error
  "requests": 1,                   // HTTP requests made to BMW this run
  "token_expires_at": "2026-11-17T09:17:00",
  "searches": [
    { "name": "g20-msport-dap-pro", "description": "...", "fetched": 79, "matches": 5,
      "baseline": false, "current_matches": [ <car>, ... ],
      "new_matches": [...], "price_drops": [...], "gone_matches": [...] }
  ],
  "alerts": [ <alert>, ... ]       // everything you need to act on
}
```

`<car>` = `{vin, year, model, color, price, miles, dealer, distance, url}`. `distance` is in
miles from the search's ZIP, and `dealer` is BMW's dealer code.

## 3. What to alert, and how

Go through `alerts` in order. One message per alert is fine. For several alerts, send one
message with a line for each.

| `type` | Send? | Message (fill in from the alert) |
|---|---|---|
| `new_match` | **Yes, right away** | 🚗 **New match** ({search}): {year} {model}, {color}, {price}, {miles} mi, {distance} mi away (dealer {dealer}). VIN {vin}. {url} |
| `price_drop` | **Yes, right away** | 💸 **Price drop** ({search}): {year} {model} {color} {old_price} → {new_price} (−{drop}). {miles} mi, {distance} mi away. {url} |
| `match_gone` | Yes, low priority | 👋 No longer listed ({search}): {year} {model} {color}, last {price}. Probably sold. |
| `search_started` | Yes, once | 🆕 Now watching "{search}": {N} current matches. List each `matches[]` car on one line. |
| `health` level `error` | **Yes, right away** | 🔧 **bmw-cpo-watch FAILED**: {message}. Add what you tried, if anything. |
| `health` level `warning` | Yes, unless it's an exact repeat (see below) | ⚠️ bmw-cpo-watch warning ({search}): {message} |

Format prices as dollars with commas ($35,888), and always include the dealer URL. A car can
appear in more than one search; that's fine.

**Nothing in `alerts`?** Send nothing. Asad doesn't want "no news" messages, except the
weekly heartbeat below.

### Health alerts (watch the watcher)

Alert Asad about health problems even when the run "worked":

1. **Exit code 2 or `status: "error"`**: always alert, with the `message`. Common causes:
   - `token endpoint returned HTTP 401/403`: BMW changed its website credential. Asad
     needs to update `[token] client_auth` (docs/operations.md, Troubleshooting).
   - `inventory API rejected the token`: the API changed how it authenticates.
   - `token request failed: ConnectionError`: your machine can't reach BMW.
   - `crashed: ...`: a bug. Include the message.
2. **Exit code 1 or `status: "warning"`**: alert, but don't repeat the same warning every
   day. Compare with the previous run:
   `sqlite3 data/bmwcpo.sqlite "select report_json from runs order by id desc limit 2"`.
   Re-send a warning that's still there after 3 days.
3. **Stale watcher**: if the last successful run is more than 36 hours old, alert. This
   catches your own scheduler failing.
   `sqlite3 data/bmwcpo.sqlite "select datetime(max(started_at),'unixepoch','localtime') from runs where status != 'error'"`
4. **The command itself won't start** (missing `.venv`, Python error, `git pull` conflict):
   alert with the last lines of output.
5. **Weekly heartbeat (Mondays):** one short message, for example: "bmw-cpo-watch OK: N runs
   this week, M current matches, {requests} requests yesterday." That way silence never hides a
   dead watcher.

## 4. Rules

1. **Never print, log, paste or send the API token.** Don't `cat data/auth.txt` or echo
   `BMW_AUTH`. To check it: `.venv/bin/python -m bmwcpo.auth`, which prints only the expiry.
   The report's `token_expires_at` is safe to share.
2. **Never commit or push `data/`** (token, database, logs). It's git-ignored; keep it that way.
3. **At most twice a day.** A run is about 1 request per 100 cars per search; today that's
   1 request in total. Don't lower `cache_ttl_seconds` or `delay_range_seconds`, and don't
   loop on failures. One retry later in the day is fine.
4. **No browser automation and no bot-detection workarounds.** If BMW blocks the token or the
   API, stop and alert Asad. The manual fallback (`scripts/save_auth.sh`) needs a person in
   Chrome DevTools.
5. **Don't change `config.toml` on your own.** If Asad asks for a new search or a different
   limit, follow [docs/searches.md](docs/searches.md): edit, `--dry-run`, then
   `--search <name>` once. Tell him what changed.
6. **Don't "fix" the code on your own** when the API changes. Alert Asad with the exact error
   and what you observed.

## 5. Handy commands

| Command | Purpose |
|---|---|
| `.venv/bin/python -m bmwcpo.run --dry-run` | Validate config and show the requests. No network. |
| `.venv/bin/python -m bmwcpo.run --search NAME` | Run one search (even a disabled one) |
| `.venv/bin/python -m bmwcpo.facets --search NAME` | Show filter values and counts (1 request) |
| `.venv/bin/python -m bmwcpo.auth` | Token status (expiry only) |
| `sqlite3 -header -column data/bmwcpo.sqlite "select h.search, l.vin, l.year, l.model, l.color_name, l.price, l.mileage, l.dealer, round(h.distance) mi from search_hits h join listings l using(vin) where h.is_match=1 and h.active=1 order by h.search, h.distance"` | All current matches |
| `sqlite3 data/bmwcpo.sqlite "select vin, price, datetime(seen_at,'unixepoch','localtime') from price_history where vin='VIN' order by seen_at"` | One car's price history |
