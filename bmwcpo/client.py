"""Config-driven HTTP client + response normalizer.

Everything specific to BMW's API (URL, payload shape, JSON paths) lives in
config.toml; the Authorization token comes from bmwcpo.auth.
"""

from __future__ import annotations

import json
import random
import sqlite3
import time
from typing import Any, Iterator

import requests

from . import auth, db

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def get_path(obj: Any, path: str) -> Any:
    """Dotted path lookup. 'a.b' walks dicts; 'a[].b' maps over a list and flattens."""
    if not path:
        return None
    cur = [obj]
    for seg in path.split("."):
        flatten = seg.endswith("[]")
        key = seg[:-2] if flatten else seg
        nxt: list[Any] = []
        for item in cur:
            val = item.get(key) if isinstance(item, dict) and key else item
            if flatten:
                nxt.extend(val or [])
            else:
                nxt.append(val)
        cur = nxt
    if "[]" in path:
        return [c for c in cur if c is not None]
    return cur[0]


def _fill(template: Any, ctx: dict[str, Any]) -> Any:
    if isinstance(template, str):
        if template.startswith("{") and template.endswith("}") and template[1:-1] in ctx:
            return ctx[template[1:-1]]  # keep native type (ints etc.)
        return template.format(**ctx)
    if isinstance(template, dict):
        return {k: _fill(v, ctx) for k, v in template.items()}
    if isinstance(template, list):
        return [_fill(v, ctx) for v in template]
    return template


def normalize(raw: dict[str, Any], fields: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {"raw": raw}
    for name, path in fields.items():
        out[name] = get_path(raw, path)
    for list_key in ("option_codes", "option_names"):
        v = out.get(list_key)
        if isinstance(v, str):  # the BMW API returns pipe-delimited strings
            v = [p for p in v.split("|") if p]
        out[list_key] = [str(x) for x in v] if isinstance(v, list) else ([] if v is None else [str(v)])
    return out


def fetch_pages(cfg: dict[str, Any], conn: sqlite3.Connection) -> Iterator[dict[str, Any]]:
    api = cfg["api"]
    search = cfg["search"]
    sess = requests.Session()
    sess.headers.update(DEFAULT_HEADERS)
    sess.headers.update(api.get("headers", {}))
    # The inventory API requires an Authorization header. auth.ensure() uses BMW_AUTH,
    # else data/auth.txt if still valid, else fetches a fresh token (see docs/how-it-works.md).
    token_source = None
    if api.get("auth_required", True):
        try:
            token, token_source = auth.ensure(cfg)
        except auth.AuthError as e:
            raise SystemExit(f"error: {e}") from None
        sess.headers["Authorization"] = token
    retried_auth = False

    page = api.get("page_start", 0)
    page_size = api.get("page_size", 50)
    max_pages = api.get("max_pages", 40)
    cache_ttl = cfg.get("cache_ttl_seconds", 3600)

    for _ in range(max_pages):
        ctx = {**search, "page": page, "page_size": page_size, "offset": page * page_size}
        params = _fill(api.get("params", {}), ctx)
        body = _fill(api.get("body", {}), ctx) if api.get("body") else None
        key = db.cache_key(api["url"], {"p": params, "b": body})

        cached = db.cache_get(conn, key, cache_ttl)
        if cached is not None:
            text = cached
        else:
            resp = sess.request(
                api.get("method", "GET"), api["url"], params=params or None,
                json=body, timeout=30,
            )
            if (
                resp.status_code in (401, 403)
                and token_source in ("file", "fetched")
                and not retried_auth
                and cfg.get("token", {}).get("auto_refresh", True)
            ):
                # Token rejected before its stated expiry: fetch a new one and retry once.
                retried_auth = True
                try:
                    sess.headers["Authorization"] = auth.refresh(cfg)
                except auth.AuthError as e:
                    raise SystemExit(f"error: API returned {resp.status_code}; {e}") from None
                resp = sess.request(
                    api.get("method", "GET"), api["url"], params=params or None,
                    json=body, timeout=30,
                )
            resp.raise_for_status()
            text = resp.text
            db.cache_put(conn, key, api["url"], text)
            time.sleep(random.uniform(*cfg.get("delay_range_seconds", [2.0, 5.0])))

        data = json.loads(text)
        items = get_path(data, api["results_path"]) or []
        if not items:
            return
        yield from items
        if len(items) < page_size:
            return
        page += 1
