# API reference

Both endpoints were read from what bmwusa.com's own CPO search page sends (November 2026).
They're undocumented and can change without notice.

## 1. Token: `POST https://www.bmwusa.com/token/cpo/`

| | |
|---|---|
| Headers | `Accept: application/json`, `Content-Type: application/x-www-form-urlencoded`, `Authorization: Basic <client credential>` (in `config.toml` `[token] client_auth`) |
| Body | empty |
| Response | JSON with `access_token` (a JWT) and `expires` (when it stops working). The page caches the whole object in `localStorage["access_token"]`. |
| Lifetime | 24 hours (`exp - iat = 86400` in the JWT) |
| Used as | `Authorization: Bearer <access_token>` on the inventory call |

The client credential comes from bmwusa.com's public JS bundle. To find it again if it changes,
search the `bmwusa-universal-inventory...min.js` bundle for `token/cpo`.

## 2. Inventory: `POST https://inventoryservices.bmwdealerprograms.com/vehicle`

Headers: `Accept`, `Content-Type: application/json`, `Accept-Language`, `Authorization: Bearer ...`

```json
{"pageIndex": 0, "PageSize": 100, "postalCode": "95391", "radius": 3000,
 "formatResponse": false, "includeFacets": false, "includeDealers": false, "includeVehicles": true,
 "filters": [{"name": "Series", "values": ["3 Series"]}, {"name": "Type", "values": ["CPO"]},
             {"name": "Option", "values": ["M Sport Package"]},
             {"name": "ExteriorColor", "values": ["Blue", "Gray"]}]}
```

`bmwcpo/config.py` builds this body from each `[[searches]]` entry (`zip`, `radius`,
`filters`).

- **Paging quirk:** `pageIndex` is an item **offset** (0, 100, 200, ...), not a page number.
  Stepping by 100 returned all 1,078 nationwide CPO 3 Series with no duplicate VINs.
- `PageSize` 100 works. `radius` up to at least 3000 miles works (about nationwide).
- Filters are `{name, values}` pairs, and values must match facet strings exactly. Within
  `Option`, values are **AND**ed; within any other filter they're **OR**ed; different filters
  are ANDed. The full value list is in [searches.md](searches.md#filter-reference-api-side).

### Response

| Field | Meaning |
|---|---|
| `totalRecords` | cars matching the filters (used for the "fetched N of M" health check) |
| `resultRecords`, `pageIndex`, `pageSize` | this page |
| `vehicles` | the cars (see below) |
| `facets` | with `includeFacets: true`: `[{name, values: [{value, filterCount, totalCount, selected}]}]`. `filterCount` = cars in the current search with that value. For a filter already in use, it's computed as if that filter were removed. `totalCount` = all BMW USA inventory. |
| `filters`, `postalCode`, `radius`, `sortBy` (`PMA`), `sortDirection` | echo of the request |

### Vehicle fields we use

| API field | Our name | Notes |
|---|---|---|
| `vin` | vin | primary key |
| `year`, `model`, `modelSeries`, `trimDescription` | year, model, series, trim | |
| `exterior` | color_name | paint **name** only, e.g. "Portimao Blue Metallic" |
| `internetPrice` | price | |
| `odometer` | mileage | |
| `dealerCode` | dealer | e.g. `21188-01` |
| `distance` | dealer_distance | miles from `postalCode` |
| `vdpUrl` | url | dealer's listing page |
| `allCodes` | option_codes | pipe-delimited, zero-padded: `0337\|05AU\|0ZDY\|...` |
| `packageDescriptions` | option_names | pipe-delimited package names; fallback for `required_codes` |

Also present but not mapped: `allDescriptions` (descriptions in the same order as
`allCodes`), `exteriorMeta` (the coarse color the `ExteriorColor` filter uses), `interior`,
`upholstery`, `drivetrain`, `fuelType`, `msrp`, `stockNumber`, `photos`, `carfaxUrl`,
`carFaxNumOwners`, and others. Any of them can be added to `[fields]`.

### Option and paint codes

| Code | Meaning |
|---|---|
| 337 (`0337`, S337A) | M Sport Package |
| 5AU (`05AU`, SA5AU) | Active Driving Assistant Pro (in package ZDY, Driving Assistance Professional Package). No API filter. |
| C4P | Brooklyn Grey Metallic (not in the API response; color matches by name) |
| C31 | Portimao Blue Metallic (C1M is Phytonic Blue, not Portimao) |

More codes, checked against `allDescriptions`, are in [searches.md](searches.md#match-reference-local-side).
