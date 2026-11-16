"""Entry point: python -m bmwcpo.run [--config config.toml] [--db data/bmwcpo.sqlite]"""

from __future__ import annotations

import argparse
import time
import tomllib

from . import db
from .client import fetch_pages, normalize
from .filters import color_match, matches


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.toml")
    ap.add_argument("--db", default="data/bmwcpo.sqlite")
    args = ap.parse_args()

    with open(args.config, "rb") as f:
        cfg = tomllib.load(f)

    conn = db.connect(args.db)
    started = int(time.time())
    seen = new_matches = 0
    alerts = []

    for raw in fetch_pages(cfg, conn):
        l = normalize(raw, cfg["fields"])
        if not l.get("vin"):
            continue
        seen += 1
        is_match = matches(l)
        is_new = db.upsert_listing(conn, l, is_match)
        if is_match and is_new:
            new_matches += 1
            alerts.append(l)

    gone = db.mark_inactive(conn, started)
    print(f"seen={seen} new_matches={new_matches} no_longer_listed={gone}")
    for l in alerts:
        print(
            f"  NEW MATCH {l['vin']} {l.get('year')} {l.get('model')} "
            f"{color_match(l)} ${l.get('price')} {l.get('mileage')}mi "
            f"@ {l.get('dealer')} {l.get('url') or ''}"
        )


if __name__ == "__main__":
    main()
