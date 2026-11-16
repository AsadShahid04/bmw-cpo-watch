"""SQLite storage: listings, price history, raw-response cache."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"


def connect(path: str = "data/bmwcpo.sqlite") -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA.read_text())
    return conn


def cache_key(url: str, payload: Any) -> str:
    blob = url + json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def cache_get(conn: sqlite3.Connection, key: str, max_age_s: int) -> str | None:
    row = conn.execute(
        "SELECT body, fetched_at FROM raw_responses WHERE key = ?", (key,)
    ).fetchone()
    if row and time.time() - row["fetched_at"] <= max_age_s:
        return row["body"]
    return None


def cache_put(conn: sqlite3.Connection, key: str, url: str, body: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO raw_responses(key, url, body, fetched_at) VALUES (?,?,?,?)",
        (key, url, body, int(time.time())),
    )
    conn.commit()


def upsert_listing(conn: sqlite3.Connection, l: dict[str, Any], is_match: bool) -> bool:
    """Insert/update a listing. Returns True if the VIN is new."""
    now = int(time.time())
    existing = conn.execute("SELECT vin, price FROM listings WHERE vin = ?", (l["vin"],)).fetchone()
    fields = (
        l.get("year"), l.get("model"), l.get("trim"), l.get("color_name"),
        l.get("color_code"), l.get("price"), l.get("mileage"), l.get("dealer"),
        l.get("dealer_distance"), l.get("url"),
        json.dumps(l.get("option_codes", [])), json.dumps(l.get("option_names", [])),
        int(is_match), json.dumps(l.get("raw", {}), default=str),
    )
    if existing is None:
        conn.execute(
            """INSERT INTO listings(vin, year, model, trim, color_name, color_code, price,
               mileage, dealer, dealer_distance, url, option_codes, option_names,
               is_match, raw_json, first_seen, last_seen, active)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
            (l["vin"], *fields, now, now),
        )
        new = True
    else:
        conn.execute(
            """UPDATE listings SET year=?, model=?, trim=?, color_name=?, color_code=?,
               price=?, mileage=?, dealer=?, dealer_distance=?, url=?, option_codes=?,
               option_names=?, is_match=?, raw_json=?, last_seen=?, active=1 WHERE vin=?""",
            (*fields, now, l["vin"]),
        )
        new = False
    if l.get("price") is not None and (new or existing["price"] != l.get("price")):
        conn.execute(
            "INSERT INTO price_history(vin, price, seen_at) VALUES (?,?,?)",
            (l["vin"], l["price"], now),
        )
    conn.commit()
    return new


def mark_inactive(conn: sqlite3.Connection, run_started: int) -> int:
    cur = conn.execute(
        "UPDATE listings SET active = 0 WHERE last_seen < ? AND active = 1", (run_started,)
    )
    conn.commit()
    return cur.rowcount
