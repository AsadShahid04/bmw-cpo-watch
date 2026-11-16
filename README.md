# bmw-cpo-watch

Watches BMW USA Certified Pre-Owned inventory for a G20 3 Series with:
- M Sport Package (option 337 / S337A)
- Driving Assistant Professional (option 5AU, package ZDY)
- Brooklyn Grey Metallic (C4P) or Portimao Blue Metallic (C31)

Stores listings, price history and cached API responses in SQLite, and prints new matches.

## How the API works (captured from bmwusa.com, Nov 2026)

The CPO search page is a JS app that calls one endpoint:

    POST https://inventoryservices.bmwdealerprograms.com/vehicle
    Headers: Accept, Content-Type: application/json, Accept-Language, Authorization

    {"pageIndex":0,"PageSize":100,"postalCode":"95391","radius":3000,
     "formatResponse":false,"includeFacets":false,"includeDealers":false,"includeVehicles":true,
     "filters":[{"name":"Series","values":["3 Series"]},{"name":"Type","values":["cpo"]}]}

- Filters are `{name, values}` pairs. Facet names seen: Series, Type (`cpo`), Model, Year, Price,
  Odometer, ExteriorColor (coarse: Black/Blue/Grey...), Drivetrain, FuelType, DealerCode, Option.
  Enable `includeFacets` to see the exact value strings.
- `pageIndex` acts as an item offset (0, 100, 200, ...), not a page number. Verified: stepping by 100
  returned all 1078 nationwide CPO 3 Series, 1078 unique VINs.
- PageSize 100 works. radius up to at least 3000 works. Each vehicle includes `distance`.
- Vehicle fields used: `vin, year, model, modelSeries, trimDescription, exterior, odometer,
  internetPrice, vdpUrl, dealerCode, distance, allCodes`.
- `allCodes` is a pipe-delimited string with a leading-zero pad: `0337` = M Sport (337),
  `05AU` = Driving Assistant Professional (5AU; package ZDY also present).
- Paint is only a name in `exterior` ("Brooklyn Grey Metallic", "Portimao Blue Metallic"); there is
  no paint code in the response, so colors match by name.

### Authorization header (you must supply this)

The API requires an `Authorization` header that the site's page adds itself. I could not read or
record its value, and I do not know how long it stays valid. Get it once from your own browser:
DevTools > Network > the `vehicle` POST > Request Headers > Authorization, then put the value in
the `BMW_AUTH` env var or `data/auth.txt` (git-ignored). If requests start returning 401/403, copy a
fresh one. If it turns out to expire quickly, switch to a Playwright-based token fetch.

## Status

- Request shape, paging, field mapping and code logic verified against live data (in-browser).
- NOT yet verified: running the Python client from a plain script (auth + bot protection may
  behave differently outside a browser; the sandbox I built this in could not reach bmwusa.com).
- A snapshot on 2026-11-15 found 5 nationwide matches, the nearest 357 miles from Mountain House.
  Validate on the dealer page / window sticker before acting.

## Setup

    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    pytest
    export BMW_AUTH='...'
    python -m bmwcpo.run

## Run

    python -m bmwcpo.run

Query the DB:

    sqlite3 data/bmwcpo.sqlite "select vin, year, color_name, price, mileage, dealer from listings where is_match=1 and active=1"

Schedule it once or twice a day (cron). Keep the delay and cache settings in `config.toml`
conservative; BMW's terms of use likely restrict automated access, so keep volume low and personal.
