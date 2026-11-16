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
 "filters": [{"name": "Series", "values": ["3 Series"]}, {"name": "Type", "values": ["cpo"]}]}
```

- **Paging quirk:** `pageIndex` is an item **offset** (0, 100, 200, ...), not a page number.
  Stepping by 100 returned all 1,078 nationwide CPO 3 Series with no duplicate VINs.
- `PageSize` 100 works. `radius` up to at least 3000 miles works (about nationwide).
- Filters are `{name, values}` pairs. Facet names seen: Series, Type (`cpo`), Model, Year,
  Price, Odometer, ExteriorColor (coarse: Black/Blue/Grey...), Drivetrain, FuelType, DealerCode,
  Option. Set `includeFacets: true` to see the exact value strings.
- The request shape lives in `config.toml` `[api.body]`, so changes don't need code edits.

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

### Option and paint codes

| Code | Meaning |
|---|---|
| 337 (`0337`, S337A) | M Sport Package |
| 5AU (`05AU`, SA5AU) | Driving Assistant Professional; package ZDY also appears |
| C4P | Brooklyn Grey Metallic (not in the API response; color matches by name) |
| C31 | Portimao Blue Metallic (C1M is Phytonic Blue, not Portimao) |
