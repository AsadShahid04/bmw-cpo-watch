# bmw-cpo-watch

Watches BMW USA Certified Pre-Owned inventory, nationwide, for a G20 3 Series with:

- M Sport Package (option 337)
- Driving Assistant Professional (option 5AU)
- Brooklyn Grey Metallic or Portimao Blue Metallic

Each run pulls every CPO 3 Series listing (about 1,100), stores listings and price history in
SQLite, and prints new matches. It fetches its own API token, so no browser is needed.

## Quick start

    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    pytest
    python -m bmwcpo.run

Output looks like:

    seen=1078 new_matches=5 no_longer_listed=0
      NEW MATCH 3MW39FF05P8D76364 2023 330e portimao blue $35888 20658mi @ 21188-01 https://...

## Docs

| Doc | What's in it |
|---|---|
| [docs/how-it-works.md](docs/how-it-works.md) | The whole pipeline, how the API token is obtained, matching, storage, code map |
| [docs/api-reference.md](docs/api-reference.md) | The two BMW endpoints: request/response shapes, paging quirk, option codes |
| [docs/operations.md](docs/operations.md) | Running it, daily scheduling, querying the database, troubleshooting |
| [docs/history.md](docs/history.md) | How the token problem was solved, and what was tried and dropped |
| [AGENTS.md](AGENTS.md) | Instructions for an AI agent that runs this on a schedule |

## Rules

- `data/` is git-ignored. It holds the cached token (`data/auth.txt`), the database and logs.
  Never print or commit the token.
- Keep volume low: about 12 requests per run, one or two runs a day. BMW's terms likely restrict
  automated access; this is for personal use.
