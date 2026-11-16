"""Config-driven HTTP client + response normalizer.

Everything specific to BMW's API (URL, payload shape, JSON paths) lives in
config.toml so that once the real request is captured, no code changes are needed.
"""

from __future__ import annotations

import json
import os
import random
import sqlite3
import time
from typing import Any, Iterator

import requests

from . import db

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
    # The inventory API requires an Authorization header. Supply it via env var (preferred)
    # or a git-ignored file; never commit it.
    token = os.environ.get(api.get("auth_env", "BMW_AUTH"))
    if not token and api.get("auth_file"):
        try:
            token = open(api["auth_file"]).read().strip()
        except FileNotFoundError:
            token = None
    if api.get("auth_required", True) and not token:
        raise SystemExit(
            "No Authorization value found. Set the BMW_AUTH env var or put it in "
            f"{api.get('auth_file', 'data/auth.txt')} (see README)."
        )
    if token:
        sess.headers["Authorization"] = token
    if cfg.get("cookies_file"):
        # Optional: paste a Cookie header value into this file if the API needs a session.
        try:
            sess.headers["Cookie"] = open(cfg["cookies_file"]).read().strip()
        except FileNotFoundError:
            pass

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
