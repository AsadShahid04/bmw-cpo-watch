"""SQLite storage: listings, price history, per-search hits, run log, raw-response cache."""

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


# ---------------------------------------------------------------- response cache

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


# ---------------------------------------------------------------- listings (one row per VIN)

def upsert_listing(
    conn: sqlite3.Connection, l: dict[str, Any], is_match: bool, now: int | None = None
) -> tuple[bool, float | None]:
    """Insert/update a listing. Returns (is_new_vin, previous_price)."""
    now = int(time.time()) if now is None else now
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
    else:
        conn.execute(
            """UPDATE listings SET year=?, model=?, trim=?, color_name=?, color_code=?,
               price=?, mileage=?, dealer=?, dealer_distance=?, url=?, option_codes=?,
               option_names=?, is_match=?, raw_json=?, last_seen=?, active=1 WHERE vin=?""",
            (*fields, now, l["vin"]),
        )
    old_price = existing["price"] if existing is not None else None
    if l.get("price") is not None and (existing is None or old_price != l.get("price")):
        conn.execute(
            "INSERT INTO price_history(vin, price, seen_at) VALUES (?,?,?)",
            (l["vin"], l["price"], now),
        )
    conn.commit()
    return existing is None, old_price


def mark_inactive(conn: sqlite3.Connection, run_started: int) -> int:
    """Listings not seen by any search since run_started -> active = 0."""
    cur = conn.execute(
        "UPDATE listings SET active = 0 WHERE last_seen < ? AND active = 1", (run_started,)
    )
    conn.commit()
    return cur.rowcount


# ---------------------------------------------------------------- per-search hits

def has_hits(conn: sqlite3.Connection, search: str) -> bool:
    return conn.execute("SELECT 1 FROM search_hits WHERE search = ? LIMIT 1", (search,)).fetchone() is not None


def record_hit(
    conn: sqlite3.Connection, search: str, vin: str, is_match: bool,
    distance: float | None, now: int,
) -> bool:
    """Record that `search` returned `vin` this run. Returns True if it just became a match
    (new VIN that matches, a known VIN that now matches, or a match that was relisted)."""
    row = conn.execute(
        "SELECT is_match, active, first_matched FROM search_hits WHERE search = ? AND vin = ?",
        (search, vin),
    ).fetchone()
    was_active_match = bool(row and row["is_match"] and row["active"])
    first_matched = row["first_matched"] if row else None
    if is_match and first_matched is None:
        first_matched = now
    if row is None:
        conn.execute(
            """INSERT INTO search_hits(search, vin, is_match, distance, first_seen, last_seen,
               first_matched, active) VALUES (?,?,?,?,?,?,?,1)""",
            (search, vin, int(is_match), distance, now, now, first_matched),
        )
    else:
        conn.execute(
            """UPDATE search_hits SET is_match=?, distance=?, last_seen=?, first_matched=?, active=1
               WHERE search=? AND vin=?""",
            (int(is_match), distance, now, first_matched, search, vin),
        )
    conn.commit()
    return bool(is_match and not was_active_match)


def mark_gone(conn: sqlite3.Connection, search: str, run_started: int) -> list[str]:
    """Deactivate this search's rows not seen this run. Returns VINs that were active matches."""
    gone = [
        r["vin"] for r in conn.execute(
            """SELECT vin FROM search_hits WHERE search = ? AND active = 1 AND is_match = 1
               AND last_seen < ?""", (search, run_started),
        )
    ]
    conn.execute(
        "UPDATE search_hits SET active = 0 WHERE search = ? AND active = 1 AND last_seen < ?",
        (search, run_started),
    )
    conn.commit()
    return gone


def current_matches(conn: sqlite3.Connection, search: str) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT l.vin, l.year, l.model, l.color_name, l.price, l.mileage, l.dealer, l.url,
                  h.distance, h.first_matched
           FROM search_hits h JOIN listings l ON l.vin = h.vin
           WHERE h.search = ? AND h.is_match = 1 AND h.active = 1
           ORDER BY h.distance""",
        (search,),
    ).fetchall()


def get_listing(conn: sqlite3.Connection, vin: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM listings WHERE vin = ?", (vin,)).fetchone()


# ---------------------------------------------------------------- run bookkeeping

def last_total(conn: sqlite3.Connection, search: str, signature: str) -> int | None:
    """Previous healthy result count, or None if the search's filters/zip/radius changed."""
    row = conn.execute(
        "SELECT last_total, signature FROM search_stats WHERE search = ?", (search,)
    ).fetchone()
    return row["last_total"] if row and row["signature"] == signature else None


def set_stats(conn: sqlite3.Connection, search: str, signature: str, total: int, now: int) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO search_stats(search, signature, last_total, last_success)
           VALUES (?,?,?,?)""",
        (search, signature, total, now),
    )
    conn.commit()


def record_run(conn: sqlite3.Connection, started: int, status: str, requests: int, report: dict) -> None:
    conn.execute(
        "INSERT INTO runs(started_at, status, requests, report_json) VALUES (?,?,?,?)",
        (started, status, requests, json.dumps(report)),
    )
    conn.commit()
