CREATE TABLE IF NOT EXISTS listings (
    vin             TEXT PRIMARY KEY,
    year            INTEGER,
    model           TEXT,
    trim            TEXT,
    color_name      TEXT,
    color_code      TEXT,
    price           REAL,
    mileage         INTEGER,
    dealer          TEXT,
    dealer_distance REAL,
    url             TEXT,
    option_codes    TEXT,            -- JSON array
    option_names    TEXT,            -- JSON array
    is_match        INTEGER NOT NULL DEFAULT 0,
    raw_json        TEXT,
    first_seen      INTEGER NOT NULL,
    last_seen       INTEGER NOT NULL,
    active          INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS price_history (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    vin     TEXT NOT NULL REFERENCES listings(vin),
    price   REAL NOT NULL,
    seen_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_responses (
    key        TEXT PRIMARY KEY,     -- sha256(url + payload)
    url        TEXT,
    body       TEXT,
    fetched_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_listings_match ON listings(is_match, active);
CREATE INDEX IF NOT EXISTS idx_price_vin ON price_history(vin);
