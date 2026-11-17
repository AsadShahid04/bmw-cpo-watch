# CPO listings browser (GitHub Pages)

A simple, shareable read-only view of the bmw-cpo-watch inventory, published
with GitHub Pages from this `docs/` folder.

- `index.html` — the page (vanilla JS, no build step). Fetches `data.json`
  and renders search, region tabs, DAP Pro / HUD / M Sport filters, price
  and mileage caps, and per-car details with color swatches and dealer
  listing links.
- `data.json` — snapshot of the watcher SQLite database, regenerated daily
  after the morning hunt from the database backup (`backups/`). It holds
  active listings, DAP+HUD / G20 matches, recent price drops, and recently
  delisted matches. No API token or watcher internals are in it.

Refresh: the morning hunt run regenerates `data.json` from the fresh backup
and pushes it here; Pages rebuilds automatically.
