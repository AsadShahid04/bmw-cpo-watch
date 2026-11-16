#!/usr/bin/env python3
"""Find the inventory API call inside a HAR export.

Chrome: DevTools > Network > (do a CPO search) > right-click > "Save all as HAR with content".
Usage: python scripts/har_extract.py capture.har [--show-body N]

Prints JSON responses that look like vehicle lists, largest first, with the request
method, URL, request body and the top-level JSON keys, so you can fill config.toml.
"""

from __future__ import annotations

import argparse
import json
import sys


def looks_like_inventory(text: str) -> bool:
    t = text.lower()
    return '"vin"' in t or "vehicleidentificationnumber" in t


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("har")
    ap.add_argument("--show-body", type=int, default=0, help="print first N chars of response")
    args = ap.parse_args()

    with open(args.har, encoding="utf-8") as f:
        entries = json.load(f)["log"]["entries"]

    hits = []
    for e in entries:
        content = e["response"].get("content", {})
        text = content.get("text") or ""
        mime = content.get("mimeType", "")
        if "json" in mime and looks_like_inventory(text):
            hits.append((len(text), e, text))

    if not hits:
        sys.exit("No JSON responses containing VINs found. Did the capture include the search?")

    for size, e, text in sorted(hits, key=lambda h: -h[0]):
        req = e["request"]
        print("=" * 80)
        print(req["method"], req["url"])
        print("status:", e["response"]["status"], "size:", size)
        if req.get("postData"):
            print("request body:", req["postData"].get("text", "")[:2000])
        # Header names only; values may include cookies/tokens, so they are not printed.
        print("request header names:", sorted({h["name"] for h in req["headers"]}))
        try:
            data = json.loads(text)
            keys = list(data)[:20] if isinstance(data, dict) else f"list[{len(data)}]"
            print("top-level keys:", keys)
        except json.JSONDecodeError:
            pass
        if args.show_body:
            print(text[: args.show_body])


if __name__ == "__main__":
    main()
