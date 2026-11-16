# Instructions for agents

You're running a personal BMW CPO inventory watcher for Asad. It needs no browser and no
credentials from Asad: it fetches its own short-lived API token.

## Run it

From the repo root:

    scripts/daily.sh            # appends to data/daily.log; exit code 0 = success

Or, to see the output directly:

    .venv/bin/python -m bmwcpo.run

First time on a new machine: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -m pytest -q`
(Python 3.11+).

## What to report

- The counts line: `seen=N new_matches=M no_longer_listed=K`
- Every `NEW MATCH` line: VIN, year/model, color, price, miles, dealer code, URL
- To list all current matches with distance from ZIP 95391:

      sqlite3 -header -column data/bmwcpo.sqlite "select vin, year, model, color_name, price, mileage, dealer, round(dealer_distance) mi from listings where is_match=1 and active=1 order by dealer_distance"

- On failure: the exact last line of output and the exit code. Don't retry in a loop.

## Rules

1. **Never print, log, paste or send the token.** Don't `cat data/auth.txt` or echo `BMW_AUTH`.
   To check it, run `.venv/bin/python -m bmwcpo.auth`, which prints only the expiry.
2. **Never commit `data/`** (token, database, logs). It's git-ignored; keep it that way.
3. **At most twice a day.** Each run makes about 12 requests to BMW. Don't lower
   `cache_ttl_seconds` or the delays.
4. **No browser automation and no bot-detection workarounds.** If the token endpoint returns
   401/403, stop and tell Asad. The fallback (`scripts/save_auth.sh`) needs a person at Chrome
   DevTools.
5. **Keep `data/` between runs.** Without the database, every match is reported as new.

How it all works: [docs/how-it-works.md](docs/how-it-works.md).
