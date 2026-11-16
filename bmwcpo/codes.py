"""Option / paint code knowledge for the G20 3 Series.

Verified against the live inventory API (Nov 2026): vehicles carry an `allCodes` string like
"01PP|02VF|0337|05AS|..." with a leading-zero pad, so M Sport = "0337" and Driving Assistant
Professional = "05AU" (package ZDY also appears). Paint is only given as a name string in
`exterior` (e.g. "Brooklyn Grey Metallic"), not as a code, so colors match by name.

Original sources (secondary):
- 337  = M Sport package (long form S337A)
- 5AU  = Active Driving Assistant Pro, part of the Driving Assistance
         Professional package (ZDY). NHTSA SIBs write it as SA5AU.
- C4P  = Brooklyn Grey Metallic
- C31  = Portimao Blue Metallic (some touch-up catalogs also list D13)
NOTE: C1M is Phytonic Blue, NOT Portimao.
"""

from __future__ import annotations


def normalize_code(raw: str) -> str:
    """Collapse S337A / SA5AU / S5AU / 337 / 5AU style codes to the bare code."""
    c = (raw or "").strip().upper()
    if len(c) == 4 and c.startswith("0"):  # BMW inventory API pads codes: 0337 -> 337, 05AU -> 5AU
        return c[1:]
    if len(c) == 5 and c.startswith("SA"):
        return c[2:]
    if len(c) == 5 and c.startswith("S") and c.endswith("A"):
        return c[1:-1]
    if len(c) == 4 and c.startswith("S"):
        return c[1:]
    return c


# What we are hunting for. Edit freely; config.yaml overrides these.
REQUIRED_OPTION_CODES = {"337", "5AU"}
OPTION_NAME_FALLBACKS = {
    "337": ["m sport package"],
    "5AU": ["driving assistant professional", "driving assistance professional"],
}
WANTED_COLORS = {
    "brooklyn grey": {"codes": {"C4P"}, "names": ["brooklyn grey", "brooklyn gray"]},
    "portimao blue": {"codes": {"C31", "D13"}, "names": ["portimao blue", "portimão blue"]},
}
