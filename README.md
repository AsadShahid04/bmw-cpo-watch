# bmw-cpo-watch

Watches BMW USA Certified Pre-Owned inventory for the cars you describe in
[`config.toml`](config.toml) and alerts on what changes. Two searches run by default:

| Search | Wants | Requests |
|---|---|---|
| `g20-msport-dap-pro` | 3 Series with M Sport (337) + Driving Assistant Professional (5AU), Brooklyn Grey or Portimao Blue | 1 (filtered on BMW's side) |
| `dap-pro-hud` | any CPO 3 Series with Driving Assistant Professional (5AU) + Head-up Display (6U3/610), any color | ~11 (nationwide scan) |

Add your own in `config.toml`, or in a git-ignored `config.local.toml`. Each run reports **new
matches**, **price drops**, **sold cars** and **health problems**, as text and as
`data/last_run.json` for an agent to act on. It fetches its own API token, so no browser is
needed.

## Quick start

    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    pytest                              # no network
    python -m bmwcpo.run --dry-run      # check config, show requests, no network
    python -m bmwcpo.run                # real run

    [g20-msport-dap-pro] 79 cars, 1 request(s), 5 matches (0 new, 0 price drops, 0 gone)
    [dap-pro-hud] 1081 cars, 11 request(s), 49 matches (0 new, 1 price drops, 0 gone)
    status=ok requests=12 alerts=1

## Docs

| Doc | What's in it |
|---|---|
| [docs/how-it-works.md](docs/how-it-works.md) | The run as a flowchart, the API token, alerts, health checks, storage, code map |
| [docs/searches.md](docs/searches.md) | **Tuning:** writing searches, every API filter and value, match rules, option codes |
| [docs/api-reference.md](docs/api-reference.md) | The two BMW endpoints: requests, responses, fields |
| [docs/operations.md](docs/operations.md) | Commands, exit codes, queries, scheduling, troubleshooting |
| [docs/history.md](docs/history.md) | How the token and filter questions were solved, and the decisions behind them |
| [AGENTS.md](AGENTS.md) | Runbook for the agent (Muse, Grokbot, ...) that runs this daily and alerts Asad |

## Rules

- `data/` is git-ignored. It holds the cached token (`data/auth.txt`), the database, logs and
  reports. Never print or commit the token.
- Keep volume low: one or two runs a day. BMW's terms likely restrict automated access; this
  is for personal use.
