"""List the API's filter values, with counts, for a search. Use it to tune config.toml.

    python -m bmwcpo.facets                          # facets for the first enabled search
    python -m bmwcpo.facets --search NAME            # for a specific search
    python -m bmwcpo.facets --search NAME --only Option ExteriorColor
    python -m bmwcpo.facets --json

Makes ONE request (1 car, facets on). Counts are "cars matching this search's current
filters that also have this value" (filterCount) out of all BMW USA inventory (totalCount).
"""

from __future__ import annotations

import argparse
import json
import sys

from . import config, db
from .client import Client, FatalError, SearchError


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="config.toml")
    ap.add_argument("--db", default="data/bmwcpo.sqlite")
    ap.add_argument("--search", help="search name (default: first enabled)")
    ap.add_argument("--only", nargs="*", help="facet names to show")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    cfg = config.load(args.config)
    s = config.searches(cfg, args.search)[0]
    client = Client(cfg, db.connect(args.db))
    body = config.build_body(cfg, s, offset=0, page_size=1, include_facets=True)
    try:
        data = json.loads(client.post(body))
    except (FatalError, SearchError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    facets = {
        f["name"]: [(v["value"], v.get("filterCount", 0), v.get("totalCount", 0)) for v in f["values"]]
        for f in data.get("facets") or []
        if not args.only or f["name"] in args.only
    }
    if args.json:
        print(json.dumps({"search": s["name"], "total_records": data.get("totalRecords"),
                          "facets": facets}, indent=2))
        return 0
    print(f"[{s['name']}] {data.get('totalRecords')} cars match the current filters "
          f"{json.dumps(s['filters'])}\n")
    for name, values in facets.items():
        print(f"{name}  (filter = {{ {name} = [\"...\"] }})")
        for value, fc, tc in sorted(values, key=lambda x: -x[1]):
            print(f"    {fc:6d} of {tc:6d}   {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
