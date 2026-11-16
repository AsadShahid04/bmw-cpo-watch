"""Run every enabled search once: fetch, match, store, and report alerts.

    python -m bmwcpo.run                  # all enabled searches
    python -m bmwcpo.run --search NAME    # just one search (even if disabled)
    python -m bmwcpo.run --dry-run        # validate config + show the requests; no network, no writes
    python -m bmwcpo.run --json           # print the JSON report instead of text

Every real run writes the full report to data/last_run.json (see docs/operations.md).
Exit codes: 0 = ok, 1 = finished with health warnings, 2 = failed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Any

from . import auth, config, db
from .client import Client, FatalError, SearchError, normalize
from .filters import matches

EXIT_CODES = {"ok": 0, "warning": 1, "error": 2}


def money(v: Any) -> str:
    return f"${v:,.0f}" if isinstance(v, (int, float)) else "$?"


def car(src: Any, distance: Any = None) -> dict[str, Any]:
    """Compact, alert-ready description of a car from a listing dict or DB row."""
    get = (lambda k: src.get(k)) if isinstance(src, dict) else (lambda k: src[k] if k in src.keys() else None)
    dist = distance if distance is not None else get("distance") or get("dealer_distance")
    return {
        "vin": get("vin"), "year": get("year"), "model": get("model"), "color": get("color_name"),
        "price": get("price"), "miles": get("mileage"), "dealer": get("dealer"),
        "distance": round(dist) if isinstance(dist, (int, float)) else None, "url": get("url"),
    }


def run_searches(
    cfg: dict[str, Any], conn, searches: list[dict[str, Any]], client: Any, now: int,
    config_warnings: list[str] | None = None, all_searches: bool = True,
) -> dict[str, Any]:
    alerts_cfg = cfg.get("alerts", {})
    health_cfg = cfg.get("health", {})
    min_drop = alerts_cfg.get("min_price_drop", 1)
    max_drop_ratio = health_cfg.get("max_drop_ratio", 0.5)
    max_missing = health_cfg.get("max_missing_fields_ratio", 0.5)
    fields = cfg["fields"]

    report: dict[str, Any] = {
        "run_at": dt.datetime.fromtimestamp(now).isoformat(timespec="seconds"),
        "status": "ok", "requests": 0, "token_expires_at": None, "searches": [], "alerts": [],
    }
    alerts = report["alerts"]

    def health(level: str, message: str, search: str | None = None) -> None:
        alerts.append({"type": "health", "level": level, "search": search, "message": message})

    for w in config_warnings or []:
        health("warning", f"config: {w}")

    # 1. Fetch every search (one shared client: one token, one request counter).
    fetched: dict[str, tuple[list[dict[str, Any]], dict[str, Any]]] = {}
    fatal: str | None = None
    for s in searches:
        if fatal:
            health("error", f"skipped because of an earlier error: {fatal}", s["name"])
            continue
        try:
            raw, meta = client.fetch_search(s)
        except FatalError as e:
            fatal = str(e)
            health("error", fatal, s["name"])
            continue
        except SearchError as e:
            health("error", str(e), s["name"])
            continue
        listings = [l for l in (normalize(v, fields) for v in raw) if l.get("vin")]
        fetched[s["name"]] = (listings, meta)

    # 2. Store each VIN once; remember price changes for the price-drop check.
    by_vin: dict[str, dict[str, Any]] = {}
    any_match: dict[str, bool] = {}
    for s in searches:
        for l in fetched.get(s["name"], ([], {}))[0]:
            by_vin.setdefault(l["vin"], l)
            any_match[l["vin"]] = any_match.get(l["vin"], False) or matches(l, s["match"])
    prev_price: dict[str, float | None] = {}
    for vin, l in by_vin.items():
        _, prev_price[vin] = db.upsert_listing(conn, l, any_match[vin], now=now)

    # 3. Per-search: matches, transitions, health.
    all_healthy = not fatal and len(fetched) == len(searches)
    for s in searches:
        name = s["name"]
        entry: dict[str, Any] = {"name": name, "description": s.get("description", "")}
        report["searches"].append(entry)
        if name not in fetched:
            entry["error"] = True
            continue
        listings, meta = fetched[name]
        baseline = not db.has_hits(conn, name)
        new_cars, drops, gone_cars = [], [], []
        for l in listings:
            is_match = matches(l, s["match"])
            if db.record_hit(conn, name, l["vin"], is_match, l.get("dealer_distance"), now) and not baseline:
                new_cars.append(car(l))
            old, new = prev_price.get(l["vin"]), l.get("price")
            if (is_match and isinstance(old, (int, float)) and isinstance(new, (int, float))
                    and old - new >= min_drop):
                drops.append({**car(l), "old_price": old, "new_price": new, "drop": old - new})

        # Health checks. A suspicious result must not mark cars as gone (no false "sold" alerts).
        # A sharp drop is reported once (the new count becomes the baseline); the other
        # problems keep warning on every run until fixed.
        suspicious = sharp_drop = False
        total, n = meta.get("total_records"), len(listings)
        signature = json.dumps([s["zip"], s["radius"], s["filters"]], sort_keys=True)
        prev_total = db.last_total(conn, name, signature)
        if n == 0:
            suspicious = True
            health("warning", "0 cars returned; filters may be too narrow or the API changed", name)
        elif prev_total and n < prev_total * (1 - max_drop_ratio):
            suspicious = sharp_drop = True
            health("warning", f"only {n} cars returned vs {prev_total} last time (sharp drop); "
                              "gone-checks skipped this run", name)
        if total is not None and n < total:
            suspicious, sharp_drop = True, False
            health("warning", f"fetched {n} of {total} cars; raise [api] max_pages", name)
        if n:
            missing = sum(1 for l in listings if not l["option_codes"] or not l.get("color_name")
                          or l.get("price") is None)
            if missing / n > max_missing:
                suspicious, sharp_drop = True, False
                health("warning", f"{missing} of {n} cars lack option codes, color or price; "
                                  "the API response shape may have changed", name)
        if suspicious:
            all_healthy = False
            if sharp_drop:
                db.set_stats(conn, name, signature, n, now)
        else:
            for vin in db.mark_gone(conn, name, now):
                if not baseline:
                    row = db.get_listing(conn, vin)
                    gone_cars.append(car(row) if row else {"vin": vin})
            db.set_stats(conn, name, signature, n, now)

        current = [car(r) for r in db.current_matches(conn, name)]
        entry.update({
            "total_records": total, "fetched": n, "requests": meta.get("requests", 0),
            "matches": len(current), "baseline": baseline, "current_matches": current,
            "new_matches": new_cars, "price_drops": drops, "gone_matches": gone_cars,
        })
        if baseline:
            alerts.append({"type": "search_started", "search": name, "matches": current})
        alerts.extend({"type": "new_match", "search": name, **c} for c in new_cars)
        alerts.extend({"type": "price_drop", "search": name, **c} for c in drops)
        alerts.extend({"type": "match_gone", "search": name, **c} for c in gone_cars)

    if all_healthy and all_searches:  # listings.active = "returned by the latest full run"
        db.mark_inactive(conn, now)

    levels = {a["level"] for a in alerts if a["type"] == "health"}
    report["status"] = "error" if "error" in levels else "warning" if "warning" in levels else "ok"
    report["requests"] = getattr(client, "requests", 0)
    token_value = getattr(getattr(client, "sess", None), "headers", {}).get("Authorization")
    auth_file = Path(cfg.get("api", {}).get("auth_file", "data/auth.txt"))
    if not token_value and auth_file.exists():  # no request this run: report the cached token's expiry
        token_value = auth_file.read_text()
    if token_value:
        exp = auth.token_expiry(token_value)
        if exp:
            report["token_expires_at"] = dt.datetime.fromtimestamp(exp).isoformat(timespec="seconds")
    db.record_run(conn, now, report["status"], report["requests"], report)
    return report


def car_line(c: dict[str, Any]) -> str:
    dist = f"{c['distance']} mi away" if c.get("distance") is not None else "? mi away"
    miles = f"{c['miles']:,} mi" if isinstance(c.get("miles"), int) else "? mi"
    return (f"{c.get('year')} {c.get('model')} {c.get('color')} | {money(c.get('price'))} | {miles} | "
            f"dealer {c.get('dealer')} | {dist} | {c.get('vin')} | {c.get('url') or ''}")


def format_text(report: dict[str, Any]) -> str:
    out = []
    for e in report["searches"]:
        if e.get("error"):
            out.append(f"[{e['name']}] FAILED (see health)")
            continue
        out.append(
            f"[{e['name']}] {e['fetched']} cars, {e['requests']} request(s), {e['matches']} matches "
            f"({len(e['new_matches'])} new, {len(e['price_drops'])} price drops, "
            f"{len(e['gone_matches'])} gone)"
        )
    for a in report["alerts"]:
        t = a["type"]
        if t == "new_match":
            out.append(f"  NEW MATCH   [{a['search']}] {car_line(a)}")
        elif t == "price_drop":
            out.append(f"  PRICE DROP  [{a['search']}] {money(a['old_price'])} -> {money(a['new_price'])} "
                       f"(-{money(a['drop'])}) {car_line(a)}")
        elif t == "match_gone":
            out.append(f"  GONE        [{a['search']}] no longer listed (sold or changed): {car_line(a)}")
        elif t == "search_started":
            out.append(f"  STARTED     [{a['search']}] now tracking; {len(a['matches'])} current matches "
                       "(baseline, not alerted as new)")
            out.extend(f"                - {car_line(c)}" for c in a["matches"])
        elif t == "health":
            where = f"[{a['search']}] " if a.get("search") else ""
            out.append(f"  HEALTH {a['level'].upper():7} {where}{a['message']}")
    out.append(f"status={report['status']} requests={report['requests']} "
               f"alerts={sum(1 for a in report['alerts'] if a['type'] != 'search_started')}")
    return "\n".join(out)


def dry_run_text(cfg: dict[str, Any], searches: list[dict[str, Any]], warnings: list[str]) -> str:
    api = cfg["api"]
    out = ["DRY RUN: config is valid. No token fetched, no requests sent, nothing written."]
    out.extend(f"  config warning: {w}" for w in warnings)
    for s in searches:
        body = config.build_body(cfg, s, offset=0, page_size=api.get("page_size", 100))
        out.append(f"\n[{s['name']}] {s.get('description', '')}".rstrip())
        out.append(f"  POST {api['url']}")
        out.append(f"  body: {json.dumps(body)}")
        out.append(f"  match rules: {json.dumps(s['match']) if s['match'] else '(none: every returned car matches)'}")
    out.append(f"\n{len(searches)} search(es); each needs about 1 request per 100 cars returned.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the BMW CPO searches in config.toml.")
    ap.add_argument("--config", default="config.toml")
    ap.add_argument("--db", default="data/bmwcpo.sqlite")
    ap.add_argument("--report", default="data/last_run.json")
    ap.add_argument("--search", help="run only this search (by name)")
    ap.add_argument("--dry-run", action="store_true", help="validate and show requests; no network")
    ap.add_argument("--json", action="store_true", help="print the JSON report instead of text")
    args = ap.parse_args(argv)

    try:
        cfg = config.load(args.config)
        errors, warnings = config.validate(cfg)
        if errors:
            raise config.ConfigError("; ".join(errors))
        searches = config.searches(cfg, args.search)
        if not searches:
            raise config.ConfigError("no enabled searches")
    except (OSError, ValueError) as e:  # ValueError covers ConfigError and TOML syntax errors
        print(f"config error: {e}", file=sys.stderr)
        return EXIT_CODES["error"]

    if args.dry_run:
        print(dry_run_text(cfg, searches, warnings))
        return 0

    now = int(time.time())
    conn = db.connect(args.db)
    client = Client(cfg, conn)
    try:
        report = run_searches(cfg, conn, searches, client, now, warnings,
                              all_searches=args.search is None)
    except Exception as e:  # never die silently: still write an error report for the agent
        report = {
            "run_at": dt.datetime.fromtimestamp(now).isoformat(timespec="seconds"),
            "status": "error", "requests": client.requests, "token_expires_at": None,
            "searches": [], "alerts": [{"type": "health", "level": "error", "search": None,
                                        "message": f"crashed: {type(e).__name__}: {e}"}],
        }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2) if args.json else format_text(report))
    return EXIT_CODES[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
