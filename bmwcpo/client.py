"""HTTP client for BMW's inventory API, plus the response normalizer.

One Client is shared by all searches in a run: it gets the token lazily (only if a
request is actually needed), caches raw pages in SQLite, spaces requests out, counts
them, and refreshes the token once if the API rejects it.
"""

from __future__ import annotations

import json
import random
import sqlite3
import time
from typing import Any

import requests

from . import auth, config, db

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


class FatalError(RuntimeError):
    """Stops the whole run (e.g. no usable token). Message never contains the token."""


class SearchError(RuntimeError):
    """Fails one search (e.g. HTTP 500); other searches still run."""


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


def normalize(raw: dict[str, Any], fields: dict[str, Any]) -> dict[str, Any]:
    """Map raw API fields to our names. A list of paths means "first non-empty one"."""
    out: dict[str, Any] = {"raw": raw}
    for name, path in fields.items():
        if isinstance(path, list):
            out[name] = next((v for v in (get_path(raw, p) for p in path) if v not in (None, "")), None)
        else:
            out[name] = get_path(raw, path)
    for list_key in ("option_codes", "option_names"):
        v = out.get(list_key)
        if isinstance(v, str):  # the BMW API returns pipe-delimited strings
            v = [p for p in v.split("|") if p]
        out[list_key] = [str(x) for x in v] if isinstance(v, list) else ([] if v is None else [str(v)])
    return out


class Client:
    def __init__(self, cfg: dict[str, Any], conn: sqlite3.Connection):
        self.cfg = cfg
        self.conn = conn
        self.api = cfg["api"]
        self.sess = requests.Session()
        self.sess.headers.update(DEFAULT_HEADERS)
        self.sess.headers.update(self.api.get("headers", {}))
        self.token_source: str | None = None
        self.retried_auth = False
        self.requests = 0
        self._last_request = 0.0

    def _ensure_auth(self) -> None:
        if self.token_source is not None or not self.api.get("auth_required", True):
            return
        try:
            token, self.token_source = auth.ensure(self.cfg)
        except auth.AuthError as e:
            raise FatalError(str(e)) from None
        self.sess.headers["Authorization"] = token

    def _send(self, body: dict[str, Any]) -> requests.Response:
        lo, hi = self.cfg.get("delay_range_seconds", [2.0, 5.0])
        if self._last_request:
            wait = random.uniform(lo, hi) - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
        try:
            resp = self.sess.request(
                self.api.get("method", "POST"), self.api["url"], json=body, timeout=30
            )
        except requests.RequestException as e:
            raise SearchError(f"inventory request failed: {type(e).__name__}") from None
        finally:
            self.requests += 1
            self._last_request = time.monotonic()
        return resp

    def post(self, body: dict[str, Any]) -> str:
        """POST one body to the inventory API and return the response text."""
        self._ensure_auth()
        resp = self._send(body)
        if (
            resp.status_code in (401, 403)
            and self.token_source in ("file", "fetched")
            and not self.retried_auth
            and self.cfg.get("token", {}).get("auto_refresh", True)
        ):
            # Token rejected before its stated expiry: fetch a new one and retry once.
            self.retried_auth = True
            try:
                self.sess.headers["Authorization"] = auth.refresh(self.cfg)
            except auth.AuthError as e:
                raise FatalError(f"inventory API returned HTTP {resp.status_code}; {e}") from None
            self.token_source = "fetched"
            resp = self._send(body)
        if resp.status_code in (401, 403):
            raise FatalError(f"inventory API rejected the token (HTTP {resp.status_code})")
        if resp.status_code != 200:
            raise SearchError(f"inventory API returned HTTP {resp.status_code}")
        return resp.text

    def fetch_search(self, search: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """All vehicles for one search, paging by offset. Returns (vehicles, meta)."""
        page_size = self.api.get("page_size", 100)
        max_pages = self.api.get("max_pages", 30)
        cache_ttl = self.cfg.get("cache_ttl_seconds", 3600)
        before = self.requests
        items: list[dict[str, Any]] = []
        total: int | None = None
        pages = 0
        for page in range(max_pages):
            body = config.build_body(self.cfg, search, offset=page * page_size, page_size=page_size)
            key = db.cache_key(self.api["url"], body)
            text = db.cache_get(self.conn, key, cache_ttl)
            if text is None:
                text = self.post(body)
                db.cache_put(self.conn, key, self.api["url"], text)
            pages += 1
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                raise SearchError("inventory API returned non-JSON") from None
            if isinstance(data.get("totalRecords"), int):
                total = data["totalRecords"]
            batch = get_path(data, self.api.get("results_path", "vehicles")) or []
            items.extend(batch)
            if len(batch) < page_size or (total is not None and len(items) >= total):
                break
        meta = {
            "total_records": total,
            "fetched": len(items),
            "pages": pages,
            "requests": self.requests - before,
        }
        return items, meta
