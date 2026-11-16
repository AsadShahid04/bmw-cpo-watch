"""Match normalized listings against what we want."""

from __future__ import annotations

from typing import Any, Iterable

from .codes import (
    OPTION_NAME_FALLBACKS,
    REQUIRED_OPTION_CODES,
    WANTED_COLORS,
    normalize_code,
)


def _has_option(listing: dict[str, Any], code: str) -> bool:
    codes = {normalize_code(c) for c in listing.get("option_codes", [])}
    if code in codes:
        return True
    names = " | ".join(n.lower() for n in listing.get("option_names", []))
    return any(frag in names for frag in OPTION_NAME_FALLBACKS.get(code, []))


def color_match(listing: dict[str, Any], wanted=WANTED_COLORS) -> str | None:
    code = (listing.get("color_code") or "").strip().upper()
    name = (listing.get("color_name") or "").strip().lower()
    for label, spec in wanted.items():
        if code and code in spec["codes"]:
            return label
        if any(frag in name for frag in spec["names"]):
            return label
    return None


def is_three_series(listing: dict[str, Any]) -> bool:
    series = (listing.get("series") or listing.get("model") or "").lower()
    return "3 series" in series or series.startswith("3") or "330" in series or "m340" in series


def matches(
    listing: dict[str, Any],
    required: Iterable[str] = REQUIRED_OPTION_CODES,
) -> bool:
    return (
        is_three_series(listing)
        and color_match(listing) is not None
        and all(_has_option(listing, c) for c in required)
    )
