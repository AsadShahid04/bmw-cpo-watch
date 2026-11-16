"""Local match rules for a search (the `match` table of a [[searches]] entry).

All rules that are set must pass. Unknown values (e.g. a car with no listed price)
pass numeric limits rather than being silently dropped.
"""

from __future__ import annotations

import unicodedata
from typing import Any

from .codes import OPTION_NAME_FALLBACKS, normalize_code


def fold(text: str | None) -> str:
    """Lowercase, strip accents (Portimão -> portimao), and treat gray/grey as the same."""
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return t.replace("gray", "grey")


def has_code(listing: dict[str, Any], code: str) -> bool:
    code = normalize_code(code)
    if code in {normalize_code(c) for c in listing.get("option_codes", [])}:
        return True
    names = " | ".join(fold(n) for n in listing.get("option_names", []))
    return any(fold(frag) in names for frag in OPTION_NAME_FALLBACKS.get(code, []))


def color_match(listing: dict[str, Any], colors: list[str]) -> str | None:
    """Return the configured color whose name appears in the car's paint name, if any."""
    name = fold(listing.get("color_name"))
    for c in colors:
        if fold(c) in name:
            return c
    return None


def failed_rules(listing: dict[str, Any], rules: dict[str, Any]) -> list[str]:
    """Names of the rules this car fails (empty list = it matches)."""
    failed = []
    for code in rules.get("required_codes", []):
        if not has_code(listing, code):
            failed.append(f"required_codes:{code}")
    if rules.get("any_codes") and not any(has_code(listing, c) for c in rules["any_codes"]):
        failed.append("any_codes")
    if rules.get("colors") and color_match(listing, rules["colors"]) is None:
        failed.append("colors")
    if rules.get("models"):
        model = fold(listing.get("model"))
        if not any(fold(m) in model for m in rules["models"]):
            failed.append("models")
    limits = (
        ("max_price", "price", lambda v, lim: v <= lim),
        ("max_miles", "mileage", lambda v, lim: v <= lim),
        ("max_distance", "dealer_distance", lambda v, lim: v <= lim),
        ("min_year", "year", lambda v, lim: v >= lim),
        ("max_year", "year", lambda v, lim: v <= lim),
    )
    for rule, field, ok in limits:
        if rule in rules:
            value = listing.get(field)
            try:
                if value is not None and not ok(float(value), float(rules[rule])):
                    failed.append(rule)
            except (TypeError, ValueError):
                pass
    return failed


def matches(listing: dict[str, Any], rules: dict[str, Any]) -> bool:
    return not failed_rules(listing, rules)
