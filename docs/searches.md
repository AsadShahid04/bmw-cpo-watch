# Searches and filters

Everything you'd tune lives in [`config.toml`](../config.toml). Each `[[searches]]` block is
one saved search, and every search with `enabled = true` runs on each run.

## How a search works

A search has two parts:

| Part | Runs where | What it does |
|---|---|---|
| `filters` | **BMW's API** | BMW returns only the cars that pass. Narrow filters mean fewer cars and fewer requests: about 1 request per 100 cars. |
| `match` | **Locally** | Each returned car is checked against these rules. Only cars that pass all of them become matches and trigger alerts. |

Use `filters` for anything the API can filter **exactly**, and `match` for everything else.
The default search shows why both are needed:

```toml
[[searches]]
name = "g20-msport-dap-pro"
enabled = true
zip = "95391"        # distances are measured from here
radius = 3000        # miles (3000 is about nationwide)
filters = { Series = ["3 Series"], Type = ["CPO"], Option = ["M Sport Package"], ExteriorColor = ["Blue", "Gray"] }

[searches.match]
required_codes = ["337", "5AU"]
colors = ["Brooklyn Grey", "Portimao Blue"]
```

- `Option = ["M Sport Package"]` is exact. It selects precisely the cars with option code 337
  (158 of 158 on 2026-11-15).
- There is **no API filter for Driving Assistant Professional** (code 5AU), so it's checked
  locally with `required_codes`. The API's "Driving Assistance Package" is a different, more
  basic package, so don't use it as a stand-in.
- `ExteriorColor` only knows broad colors (Blue, Gray, ...). It cuts the list down, and
  `colors` then checks the exact paint names.
- Result: 79 cars in 1 request instead of 1,078 cars in 11, with the same 5 matches.

## Filter reference (API side)

The format is `filters = { Name = ["value", ...] }`. Values must match the API's facet strings
**exactly**, including case. These were all live on 2026-11-15:

| Filter | Values |
|---|---|
| `Series` | 1 Series, 2 Series, 3 Series, 4 Series, 5 Series, 6 Series, 7 Series, 8 Series, i3, i4, i5, i7, i8, iX, X1, X2, X3, X4, X5, X6, X7, XM, Z3, Z4, Z8 |
| `Type` | CPO, Used |
| `CPOType` | All Pre-Owned, BMW Certified |
| `Model` | depends on Series. For 3 Series: 330e, 330e xDrive, 330i, 330i xDrive, 340i, M3, Other |
| `Year` | 2021 through 2027 |
| `Price` | $20,000 - $29,999, $30,000 - $39,999, $40,000 - $49,999, $50,000 - $59,999, $60,000 - $69,999, $70,000 - $79,999, $80,000 - $89,999, $90,000+ |
| `Odometer` | 10,000 or less, 20,000 or less, ... 100,000 or less, All |
| `ExteriorColor` | Black, Blue, Gray, Green, Red, White |
| `InteriorColor` | Beige, Black, Brown, Ivory, Red, Other |
| `Option` | Convenience Package, Driving Assistance Package, Head-up Display, Keyless Entry, Moonroof, M Sport Package, Parking Assist, Premium Sound System, Rear View Camera, Sport Line, Sport Package |
| `Drivetrain` | RWD, AWD, Other |
| `FuelType` | Gasoline, Electric, Hybrid, Other |
| `BodyStyle` | Coupe, Sedan, Other |
| `Transmission` | Automatic, Other |
| `Upholstery` | Leatherette, Other |
| `HighwayMpg` | Greater than 10, Greater than 20, Greater than 30, All |
| `DealerCode` | one of about 255 codes like `04497-01` (pin a search to specific dealers) |
| `HasVdpUrl` | Yes |

**How values combine** (tested live):

| Case | Logic | Evidence |
|---|---|---|
| Several values in **`Option`** | **AND**: the car must have all of them | M Sport + Head-up Display → 0 cars |
| Several values in any **other** filter | **OR**: any one of them | Blue + Gray → 177 + 268 = 445; 2023 + 2024 → 243 + 354 = 597 |
| Different filters | **AND** | M Sport and (Blue or Gray) → 79 |

`Price` and `Odometer` work in buckets, so use them for rough cuts and `max_price` /
`max_miles` in `match` for exact limits.

### Seeing live values and counts

```bash
python -m bmwcpo.facets                              # every filter, for the first enabled search
python -m bmwcpo.facets --search m340i-west --only Model Year Price
```

This costs one request. Each line reads `<cars in this search with this value> of <all BMW USA
inventory>`. For a filter the search already uses, the counts show what each value would give
if that filter were removed. That's why White and Black still appear with counts while the
search is filtered to Blue/Gray.

## Match reference (local side)

Every rule you set must pass. Leave a rule out to skip it.

| Rule | Type | Passes when |
|---|---|---|
| `required_codes` | list | the car has **all** these option codes (`337`, `5AU`, `ZDY`...; padding like `0337` is handled) |
| `colors` | list | the paint name contains **any** of these (accents and grey/gray don't matter) |
| `models` | list | the model contains **any** of these (`"330e"`, `"xDrive"`) |
| `max_price` | number | price ≤ this |
| `max_miles` | number | odometer ≤ this |
| `max_distance` | number | miles from the search's `zip` ≤ this |
| `min_year` / `max_year` | number | year within range |

A car with no listed price, miles or distance **passes** that limit, so an unknown value never
hides a match.

Option codes, checked against the API's own code descriptions (`allCodes` / `allDescriptions`):

| Code | API description |
|---|---|
| 337 | M Sport Package |
| 5AU | Active Driving Assistant Pro (part of ZDY, Driving Assistance Professional Package) |
| ZDY | Driving Assistance Professional Package |
| 5AS | Active Driving Assistant (the basic one) |
| ZPP | Premium Package |
| 322 | Comfort Access keyless entry |
| 688 | Harman Kardon surround sound system |
| 610 | Head-up Display |
| 6U3 | BMW Curved Display with HUD |
| 302 | Alarm System |

To see one car's codes:
`sqlite3 data/bmwcpo.sqlite "select option_codes from listings where vin='<VIN>'"`.

## Adding a search

1. Copy the example `m340i-west` block, give it a new `name` (letters, digits, `-`, `_`), and
   set `enabled = true`.
2. Check it with no network: `python -m bmwcpo.run --dry-run`. A typo in a rule name is an
   error, and an unknown filter name is a warning.
3. Look at real counts: `python -m bmwcpo.facets --search <name>`.
4. Run just that search once: `python -m bmwcpo.run --search <name>`.

The **first run of a new search is a baseline**. Its current matches are listed once as
`search_started` and are **not** alerted as "new". After that, only changes alert.

Renaming a search starts a new baseline. Changing its filters, zip or radius resets its
"sharp drop" health baseline.
