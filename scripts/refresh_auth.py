#!/usr/bin/env python3
"""Refresh the BMW inventory API Authorization header.

Loads the BMW USA CPO search page in a headless browser and reads the
Authorization header the site's own JS app sends on the POST to
inventoryservices.bmwdealerprograms.com/vehicle, then writes it to
data/auth.txt (git-ignored).

Usage: python scripts/refresh_auth.py [--url <cpo results url>]

The header value is NEVER printed or logged. On success this prints only
"auth refreshed". Exit code 0 on success, 1 if no header was captured.

Network note: this VM reaches the internet through an egress proxy (see
HTTPS_PROXY) that intercepts TLS with its own CA. Chromium cannot use that
proxy directly (its CONNECT tunnels fail), so this script relays through a
tiny localhost TCP forwarder and tells the browser to ignore the proxy's
MITM certificate. The forwarder carries no credentials: the egress proxy
allows anonymous CONNECT.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
AUTH_FILE = REPO_ROOT / "data" / "auth.txt"
DEFAULT_URL = "https://www.bmwusa.com/certified-preowned-search/results"
TARGET_HOST = "inventoryservices.bmwdealerprograms.com/vehicle"


def _pipe(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def _handle_relay(client: socket.socket, upstream_host: str, upstream_port: int) -> None:
    try:
        buf = b""
        client.settimeout(15)
        while b"\r\n\r\n" not in buf and len(buf) < 65536:
            chunk = client.recv(4096)
            if not chunk:
                return
            buf += chunk
        up = socket.create_connection((upstream_host, upstream_port), timeout=15)
        up.sendall(buf)
        resp = b""
        up.settimeout(15)
        while b"\r\n\r\n" not in resp and len(resp) < 65536:
            chunk = up.recv(4096)
            if not chunk:
                break
            resp += chunk
        client.sendall(resp)
        t1 = threading.Thread(target=_pipe, args=(client, up), daemon=True)
        t2 = threading.Thread(target=_pipe, args=(up, client), daemon=True)
        t1.start()
        t2.start()
        t1.join(timeout=90)
        t2.join(timeout=90)
    except OSError:
        pass
    finally:
        try:
            client.close()
        except OSError:
            pass


def _start_forwarder(upstream_host: str, upstream_port: int) -> int:
    """Start a localhost TCP relay to the egress proxy; return its port."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(16)
    port = srv.getsockname()[1]

    def serve() -> None:
        while True:
            try:
                client, _ = srv.accept()
            except OSError:
                return
            threading.Thread(
                target=_handle_relay, args=(client, upstream_host, upstream_port),
                daemon=True,
            ).start()

    threading.Thread(target=serve, daemon=True).start()
    return port


def _launch(p):
    """Launch Chromium: Playwright-managed browser first, falling back to the
    machine's shipped Chromium (which may refuse to start outside its harness)."""
    args = ["--no-sandbox", "--disable-dev-shm-usage"]
    override = os.environ.get("PLAYWRIGHT_CHROMIUM_PATH")
    if override:
        return p.chromium.launch(executable_path=override, headless=True, args=args)
    try:
        return p.chromium.launch(headless=True, args=args)
    except Exception:
        return p.chromium.launch(
            executable_path="/opt/meta-chromium/chrome", headless=True, args=args
        )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    # Third-party trackers the BMW page loads (Bing Ads, analytics, etc.) are
    # not needed for the capture and only add noise; block them. Never block
    # bmwusa.com or the inventory API host.
    TRACKER_HOSTS = (
        "bat.bing.com",
        "clarity.ms",
        "google-analytics.com",
        "googletagmanager.com",
        "doubleclick.net",
        "facebook.com",
        "facebook.net",
        "twitter.com",
        "linkedin.com",
        "adobedtm.com",
        "demdex.net",
        "criteo.com",
        "hotjar.com",
    )

    captured: str | None = None
    seen_requests: list[str] = []

    def on_request(request):
        nonlocal captured
        url = request.url
        if "bmwdealerprograms.com" in url or "vehicle" in url.lower():
            seen_requests.append(f"{request.method} {url}")
        if captured:
            return
        if TARGET_HOST in url and request.method == "POST":
            value = request.headers.get("authorization")
            if value:
                captured = value.strip()

    def on_route(route):
        host = urlparse(route.request.url).hostname or ""
        if any(host == t or host.endswith("." + t) for t in TRACKER_HOSTS):
            route.abort()
        else:
            route.continue_()

    # Route the browser through a localhost relay to the egress proxy (see
    # module docstring). No proxy env -> browse directly.
    proxy = None
    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy_url:
        parts = urlparse(proxy_url)
        port = _start_forwarder(parts.hostname or "localhost", parts.port or 3128)
        proxy = {"server": f"http://127.0.0.1:{port}"}

    with sync_playwright() as p:
        browser = _launch(p)
        try:
            context = browser.new_context(
                ignore_https_errors=True,  # egress proxy intercepts TLS (own CA)
                proxy=proxy,
            )
            page = context.new_page()
            page.on("request", on_request)
            page.route("**/*", on_route)
            page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
            # Wait for the search results to actually render (the inventory
            # POST fires as part of the search); a fixed sleep was not enough.
            try:
                page.wait_for_selector("text=/\\d+ Vehicles/i", timeout=60000)
            except Exception:
                pass
            page.wait_for_timeout(10000)
            if not captured:
                # Some builds wait for user interaction; scroll to trigger it.
                try:
                    page.mouse.wheel(0, 800)
                except Exception:
                    pass
                page.wait_for_timeout(15000)
            context.close()
        finally:
            browser.close()

    if not captured:
        print("error: no Authorization header captured", file=sys.stderr)
        if seen_requests:
            print("vehicle-related requests seen:", file=sys.stderr)
            for line in seen_requests[:20]:
                print("  " + line, file=sys.stderr)
        return 1

    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTH_FILE.write_text(captured + "\n")
    print("auth refreshed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
