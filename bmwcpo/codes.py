"""Option / paint code knowledge for the G20 3 Series.

Verified against the live inventory API (Nov 2026): vehicles carry an `allCodes` string like
"01PP|02VF|0337|05AS|..." with a leading-zero pad, so M Sport = "0337" and Driving Assistant
Professional = "05AU" (package ZDY also appears). Paint is only given as a name string in
`exterior` (e.g. "Brooklyn Grey Metallic") plus a coarse `exteriorMeta` ("Gray", "Blue").

Reference:
- 337  = M Sport Package (long form S337A). The API's Option filter "M Sport Package" selects
         exactly the cars with 337 (158 of 1,078 CPO 3 Series on 2026-11-15).
- 5AU  = Driving Assistant Professional (package ZDY). NO API filter exists for it.
- 5AS  = Driving Assistant (the basic one).
- 6U3  = "BMW Curved Display with HUD": the usual Head-up Display code (677 of 1,078 cars;
         8 older cars describe 6U3 as Live Cockpit Pro). 610 = standalone HUD (only 3 cars),
         and it's the ONLY code the API's Option "Head-up Display" filter matches.
- C4P  = Brooklyn Grey Metallic, C31 = Portimao Blue Metallic. C1M is Phytonic Blue, NOT Portimao.

What to look for is configured per search in config.toml ([searches.match]).
"""

from __future__ import annotations


def normalize_code(raw: str) -> str:
    """Collapse S337A / SA5AU / S5AU / 0337 / 337 style codes to the bare code."""
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


# If a car lists no codes, a required code can also be satisfied by its package name.
OPTION_NAME_FALLBACKS = {
    "337": ["m sport package"],
    "5AU": ["driving assistant professional", "driving assistance professional"],
}
