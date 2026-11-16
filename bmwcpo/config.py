"""Load and validate config.toml, and turn each [[searches]] entry into an API request body.

A search has two halves:
  filters  -> sent to BMW's API (exact facet values; see docs/searches.md). Narrows what comes back.
  match    -> checked locally on each returned car. Decides what counts as an alert.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

# Facet names the inventory API reported (Nov 2026). Others may work; they produce a warning.
KNOWN_FILTERS = {
    "BodyStyle", "CPOType", "DealerCode", "Drivetrain", "ExteriorColor", "FuelType",
    "HasVdpUrl", "HighwayMpg", "InteriorColor", "Model", "Odometer", "Option", "Price",
    "Series", "Transmission", "Type", "Upholstery", "Year",
}
MATCH_LIST_KEYS = {"required_codes", "any_codes", "colors", "models"}
MATCH_NUM_KEYS = {"max_price", "max_miles", "max_distance", "min_year", "max_year"}
BODY_DEFAULTS = {
    "formatResponse": False, "includeFacets": False,
    "includeDealers": False, "includeVehicles": True,
}
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class ConfigError(ValueError):
    pass


def local_path(path: str) -> Path:
    """config.toml -> config.local.toml (git-ignored, machine-specific overrides)."""
    p = Path(path)
    return p.with_name(f"{p.stem}.local{p.suffix}")


def _merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, val in over.items():
        if key == "searches" and isinstance(val, list):
            # Same name -> the keys set locally override the shared search's keys
            # (a local `match` or `filters` table replaces the shared one whole).
            # New name -> added.
            merged = {s.get("name"): s for s in base.get("searches", [])}
            for s in val:
                merged[s.get("name")] = {**merged.get(s.get("name"), {}), **s}
            out["searches"] = list(merged.values())
        elif isinstance(val, dict) and isinstance(base.get(key), dict):
            out[key] = _merge(base[key], val)
        else:
            out[key] = val
    return out


def load(path: str = "config.toml", *, local: bool = True) -> dict[str, Any]:
    """Load config.toml, then apply config.local.toml on top if it exists (and local=True).

    Put machine- or agent-specific changes in config.local.toml so `git pull` never
    conflicts with them. A [[searches]] entry there with the same name overrides just the
    keys it sets (e.g. only `enabled = false`); a new name adds a search.
    """
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    lp = local_path(path)
    if local and lp.exists():
        with open(lp, "rb") as f:
            cfg = _merge(cfg, tomllib.load(f))
        cfg["_local_config"] = str(lp)
    return cfg


def searches(cfg: dict[str, Any], only: str | None = None) -> list[dict[str, Any]]:
    """Normalized searches: enabled ones, or just `only` (by name, even if disabled)."""
    out = []
    for raw in cfg.get("searches", []):
        s = {
            "name": str(raw.get("name", "")),
            "description": raw.get("description", ""),
            "enabled": bool(raw.get("enabled", True)),
            "zip": str(raw.get("zip", "")),
            "radius": raw.get("radius", 3000),
            "filters": {k: [str(v) for v in vals] for k, vals in (raw.get("filters") or {}).items()},
            "match": dict(raw.get("match") or {}),
        }
        if only is None and s["enabled"]:
            out.append(s)
        elif only is not None and s["name"] == only:
            out.append(s)
    if only is not None and not out:
        raise ConfigError(f"no search named {only!r} in config")
    return out


def validate(cfg: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors stop a run; warnings are reported."""
    errors: list[str] = []
    warnings: list[str] = []
    raw_searches = cfg.get("searches")
    if not isinstance(raw_searches, list) or not raw_searches:
        return ["config has no [[searches]] entries"], warnings
    seen: set[str] = set()
    for i, raw in enumerate(raw_searches):
        name = str(raw.get("name", ""))
        where = f"search {name or f'#{i + 1}'}"
        if not NAME_RE.match(name):
            errors.append(f"{where}: name must be letters/digits/-/_/. (got {name!r})")
        if name in seen:
            errors.append(f"{where}: duplicate name")
        seen.add(name)
        if not re.fullmatch(r"\d{5}", str(raw.get("zip", ""))):
            errors.append(f"{where}: zip must be a 5-digit string")
        radius = raw.get("radius", 3000)
        if not isinstance(radius, int) or radius <= 0:
            errors.append(f"{where}: radius must be a positive integer (miles)")
        filters = raw.get("filters") or {}
        if not isinstance(filters, dict):
            errors.append(f"{where}: filters must be a table like {{ Series = [\"3 Series\"] }}")
            filters = {}
        for fname, vals in filters.items():
            if not isinstance(vals, list) or not vals or not all(isinstance(v, (str, int)) for v in vals):
                errors.append(f"{where}: filter {fname} must be a non-empty list of values")
            if fname not in KNOWN_FILTERS:
                warnings.append(f"{where}: filter {fname!r} is not a known API facet; check spelling")
        match = raw.get("match") or {}
        for key, val in match.items():
            if key in MATCH_LIST_KEYS:
                if not isinstance(val, list) or not all(isinstance(v, str) for v in val):
                    errors.append(f"{where}: match.{key} must be a list of strings")
            elif key in MATCH_NUM_KEYS:
                if not isinstance(val, (int, float)) or isinstance(val, bool):
                    errors.append(f"{where}: match.{key} must be a number")
            else:
                errors.append(f"{where}: unknown match rule {key!r}")
        if not filters and not match:
            warnings.append(f"{where}: no filters and no match rules; every CPO car would match")
    for section in ("api", "fields"):
        if section not in cfg:
            errors.append(f"config is missing the [{section}] section")
    if cfg.get("api", {}).get("auth_required", True) and not cfg.get("token", {}).get("client_auth"):
        warnings.append("[token] client_auth is not set; tokens can't be refreshed automatically")
    return errors, warnings


def build_body(
    cfg: dict[str, Any], search: dict[str, Any], *, offset: int, page_size: int,
    include_facets: bool = False,
) -> dict[str, Any]:
    """The JSON body bmwusa.com's own page sends. NOTE: pageIndex is an item offset."""
    body: dict[str, Any] = {
        "pageIndex": offset,
        "PageSize": page_size,
        "postalCode": search["zip"],
        "radius": search["radius"],
        **BODY_DEFAULTS,
        **cfg.get("api", {}).get("body_defaults", {}),
        "filters": [{"name": k, "values": v} for k, v in search["filters"].items()],
    }
    if include_facets:
        body["includeFacets"] = True
    return body
