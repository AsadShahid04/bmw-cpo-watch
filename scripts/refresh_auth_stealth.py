#!/usr/bin/env python3
"""Stealth variant of refresh_auth.py (option 3).

Same goal — capture the Authorization header on the POST to
inventoryservices.bmwdealerprograms.com/vehicle — but with a real-looking
browser fingerprint, because the plain headless run never saw the search
app fire its inventory request:

- realistic desktop Chrome UA, viewport, locale, timezone
- --disable-blink-features=AutomationControlled + navigator.webdriver hidden
- accepts the cookie banner if one appears (the app may wait for consent)
- reloads once if the first load produced no inventory request
- logs every request host (counts only) on failure, for diagnosis

Usage: python scripts/refresh_auth_stealth.py [--url <cpo results url>]

The header value is NEVER printed or logged. On success prints only
"auth refreshed". Exit code 0 on success, 1 if nothing was captured.

Network: reuses the localhost relay from refresh_auth.py (see that file's
docstring for why the relay exists).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from refresh_auth import _start_forwarder, TARGET_HOST  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
AUTH_FILE = REPO_ROOT / "data" / "auth.txt"
DEFAULT_URL = "https://www.bmwusa.com/certified-preowned-search/results"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)

STEALTH_INIT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
window.chrome = window.chrome || {runtime: {}};
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    captured: str | None = None
    hosts: Counter = Counter()
    target_seen: list[str] = []

    def on_request(request):
        nonlocal captured
        hosts[urlparse(request.url).hostname or "?"] += 1
        if captured:
            return
        if TARGET_HOST in request.url and request.method == "POST":
            target_seen.append(f"{request.method} {request.url}")
            value = request.headers.get("authorization")
            if value:
                captured = value.strip()

    proxy = None
    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy_url:
        parts = urlparse(proxy_url)
        port = _start_forwarder(parts.hostname or "localhost", parts.port or 3128)
        proxy = {"server": f"http://127.0.0.1:{port}"}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--window-size=1920,1000",
            ],
        )
        try:
            context = browser.new_context(
                ignore_https_errors=True,
                proxy=proxy,
                user_agent=UA,
                viewport={"width": 1920, "height": 1000},
                locale="en-US",
                timezone_id="America/Los_Angeles",
            )
            context.add_init_script(STEALTH_INIT)
            page = context.new_page()
            page.on("request", on_request)

            for attempt in (1, 2):
                if captured:
                    break
                page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
                # Cookie consent can gate the search app; accept if offered.
                try:
                    page.get_by_role(
                        "button", name=re.compile(r"accept|allow all", re.I)
                    ).first.click(timeout=8000)
                except Exception:
                    pass
                try:
                    page.wait_for_selector("text=/\\d+ Vehicles/i", timeout=90000)
                except Exception:
                    pass
                page.wait_for_timeout(10000)
                if not captured and not target_seen:
                    try:
                        page.mouse.wheel(0, 800)
                    except Exception:
                        pass
                    page.wait_for_timeout(15000)
                if not captured and attempt == 1:
                    print("no inventory request on first load; reloading", file=sys.stderr)
            context.close()
        finally:
            browser.close()

    if not captured:
        print("error: no Authorization header captured", file=sys.stderr)
        print("request hosts seen:", file=sys.stderr)
        for host, n in hosts.most_common(20):
            print(f"  {n:5d}  {host}", file=sys.stderr)
        if target_seen:
            for line in target_seen[:5]:
                print("  target: " + line, file=sys.stderr)
        return 1

    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTH_FILE.write_text(captured + "\n")
    print("auth refreshed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
