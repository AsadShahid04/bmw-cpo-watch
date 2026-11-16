# How we got here

A record of how the token problem was solved, so the decisions make sense later.

## The problem (Nov 15, 2026)

The watcher itself was built and checked against live data from inside a browser. One problem
was left: the inventory API needs an `Authorization` header, and nobody knew where it came from
or how long it lasted. The plan was to capture it with a script.

## What we tried

| Attempt | Result |
|---|---|
| `refresh_auth.py`: headless Chromium (Playwright) loads the CPO page and records the header | Failed in the original sandbox VM and on the Mac. The page loaded, but the inventory POST never fired. Removed. |
| `refresh_auth_stealth.py`: same, plus a faked browser fingerprint | **Not run, on purpose.** Hiding automation is bot-detection evasion. Removed. |
| `refresh_auth_chrome.py`: real, visible Google Chrome driven by Playwright with its own profile | Failed: no inventory POST within 60 s, or within 180 s on a second try. Removed. |
| Manual: copy the header from Chrome DevTools into `data/auth.txt` | **Worked.** First full run: 1,078 listings, 1,078 unique VINs, no 401/403, 5 matches. |

The manual copy showed the token is a JWT that lasts 24 hours, so a manual step would have been
needed every day.

## The breakthrough

In the real Chrome tab, the page's localStorage had an `access_token` entry. Searching the
page's JS bundle for that key led to the function that fills it, described in
[how-it-works.md](how-it-works.md#the-api-token). The token comes from a plain POST to
`https://www.bmwusa.com/token/cpo/`, using a client credential that ships in the public bundle.
There's no login, CAPTCHA or browser check in that path. The headless and automated browsers
likely failed on something else in the page, not on the token.

Calling that endpoint directly returned a valid 24-hour token, and the inventory API accepted it
(HTTP 200). The token logic then moved into `bmwcpo/auth.py`, so `python -m bmwcpo.run`
refreshes it on its own and no browser is involved at all.

## Filter research → 1 request per run (Nov 15, late)

One request with `includeFacets: true` listed 18 filter types and their exact values (see
[searches.md](searches.md)). A handful of small test queries then established:

- `Option: "M Sport Package"` selects **exactly** the cars with code 337. Both counts were 158.
- Driving Assistant Professional (5AU) has **no** filter. "Driving Assistance Package" is a
  different, broader package.
- Values inside `Option` are ANDed (M Sport + Head-up Display → 0). Values inside other
  filters are ORed (Blue + Gray = 177 + 268 = 445). Different filters are ANDed.
- M Sport + Blue/Gray on BMW's side returns 79 cars in 1 request, and **all 5 known matches**
  are among them. The old way was 1,078 cars in 11 requests.

That led to the current design: several named searches in `config.toml`, each with
server-side `filters` and local `match` rules; alerts for new matches, price drops and sold
cars; health checks; a JSON report for an agent; and `--dry-run`.

Every alert path was checked on real data (a copy of the database with a changed price, a
removed match and a phantom match). The health paths were checked with the token endpoint
pointed at localhost (exit 2) and with a search that returns 0 cars (exit 1).

## Muse's first runs (Nov 16)

Running the repo on its own machine, Muse found three things. All are now upstream:

1. **411 Length Required** from the token endpoint on its network: an empty POST lost its
   `Content-Length: 0`. The token request now sends a 1-byte body, which the server ignores.
   It was re-tested from the Mac.
2. **HUD is code 6U3, not 610.** Only 3 of 1,078 cars have 610, and the API's
   `Option = ["Head-up Display"]` filter only matches 610, so it would find almost nothing.
   6U3 is described by BMW as "BMW Curved Display with HUD" on 652 of 677 cars. This led to
   the `any_codes` match rule and the `dap-pro-hud` search (DAP Pro + HUD, any color,
   nationwide). Its first run on the Mac: 1,081 cars, 11 requests, 49 matches, plus a real
   $1,000 price drop on a 2027 M3.
3. Muse had edited files in its clone, which would make every future `git pull` fail. That led
   to `config.local.toml` (git-ignored, merged on top of `config.toml`) for machine-specific
   changes.

The same live run showed the API now sends `model: null` for about half the cars, so `model`
falls back to `trimDescription` and then `modelDescription`.

## Decisions

- **No browser automation and no evasion.** The token request is the same single call the site
  makes for every visitor.
- **The token is never printed** in output, logs, reports, errors or git. It exists only in
  `data/auth.txt` or `BMW_AUTH`.
- **Low volume.** About 1 request per 100 cars per search (about 12 per run for the two default
  searches), with a 1-hour response cache and random 1.5–4 s delays between requests. One or two
  runs a day.
- **Filter on BMW's side where it's exact; check locally where it isn't.**
- **Baseline first.** A new search lists its current matches once instead of sending a flood
  of "new" alerts. Suspicious results never mark cars as sold.
- **Manual fallback kept** (`scripts/save_auth.sh`) in case BMW changes the token endpoint.
