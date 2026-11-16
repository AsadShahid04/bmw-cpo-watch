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

## Decisions

- **No browser automation and no evasion.** The token request is the same single call the site
  makes for every visitor.
- **The token is never printed** in output, logs, errors or git. It exists only in
  `data/auth.txt` or `BMW_AUTH`.
- **Low volume.** About 12 requests per run, with a 1-hour response cache and random 1.5–4 s
  delays between pages. One or two runs a day.
- **Manual fallback kept** (`scripts/save_auth.sh`) in case BMW changes the token endpoint.
