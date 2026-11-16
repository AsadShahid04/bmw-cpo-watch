"""Get a valid Authorization value for the BMW inventory API.

bmwusa.com's own CPO search page does this in its JS bundle: it POSTs to
`https://www.bmwusa.com/token/cpo/` with a fixed client credential (shipped in
that public bundle, the same for every visitor) and gets back JSON with an
`access_token` (a JWT that lives 24 hours) and `expires`. We do the same, once
per day at most, and cache the result in data/auth.txt (mode 600, git-ignored).

The token value is never printed or logged by this module.

CLI:
    python -m bmwcpo.auth            # refresh only if missing / expiring soon
    python -m bmwcpo.auth --force    # always fetch a new one
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import time
import tomllib
from pathlib import Path
from typing import Any

import requests

DEFAULT_TOKEN_URL = "https://www.bmwusa.com/token/cpo/"
DEFAULT_MARGIN_S = 600  # refresh if the token expires within 10 minutes
TOKEN_BODY = b" "


class AuthError(RuntimeError):
    """Raised when no usable token can be found or fetched. Never contains the token."""


def token_expiry(value: str) -> int | None:
    """Return the JWT `exp` (unix seconds) of a 'Bearer <jwt>' or bare JWT, or None."""
    try:
        jwt = value.strip().split()[-1]
        payload = jwt.split(".")[1]
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return int(data["exp"])
    except Exception:
        return None


def _auth_file(cfg: dict[str, Any]) -> Path:
    return Path(cfg.get("api", {}).get("auth_file", "data/auth.txt"))


def save(value: str, path: Path) -> None:
    """Atomically write the value with owner-only permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(value + "\n")
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def fetch(cfg: dict[str, Any]) -> str:
    """Request a new token from bmwusa.com. Returns 'Bearer <jwt>'."""
    tcfg = cfg.get("token", {})
    url = tcfg.get("url", DEFAULT_TOKEN_URL)
    client_auth = tcfg.get("client_auth")
    if not client_auth:
        raise AuthError("config [token] client_auth is not set")
    try:
        # A 1-byte body: some networks/clients drop "Content-Length: 0" on an empty POST and
        # BMW's server then answers 411 Length Required (seen on Muse's machine). It ignores the body.
        resp = requests.post(
            url,
            data=TOKEN_BODY,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": client_auth,
                "Origin": "https://www.bmwusa.com",
                "Referer": "https://www.bmwusa.com/certified-preowned-search/results",
            },
            timeout=30,
        )
    except requests.RequestException as e:
        raise AuthError(f"token request failed: {type(e).__name__}") from None
    if resp.status_code != 200:
        raise AuthError(f"token endpoint returned HTTP {resp.status_code}")
    try:
        jwt = str(resp.json()["access_token"]).strip()
    except Exception:
        raise AuthError("unexpected token response (no access_token)") from None
    exp = token_expiry(jwt)
    if exp is None or exp <= time.time():
        raise AuthError("token endpoint returned an invalid or already-expired token")
    return f"Bearer {jwt}"


def refresh(cfg: dict[str, Any]) -> str:
    """Fetch a new token and store it. Returns the stored value."""
    value = fetch(cfg)
    save(value, _auth_file(cfg))
    return value


def ensure(cfg: dict[str, Any], *, force: bool = False) -> tuple[str, str]:
    """Return (value, source) where source is 'env', 'file' or 'fetched'.

    Order: BMW_AUTH env var (used as-is), then data/auth.txt if it is still valid
    for more than the margin, then a fresh fetch (if [token] auto_refresh).
    """
    api = cfg.get("api", {})
    tcfg = cfg.get("token", {})
    env_value = os.environ.get(api.get("auth_env", "BMW_AUTH"))
    if env_value and not force:
        return env_value.strip(), "env"

    margin = tcfg.get("refresh_margin_seconds", DEFAULT_MARGIN_S)
    path = _auth_file(cfg)
    if not force and path.exists():
        value = path.read_text().strip()
        exp = token_expiry(value)
        if value and (exp is None or exp - time.time() > margin):
            # exp None = not a JWT (hand-pasted value); trust it and let the API decide.
            return value, "file"

    if not (force or tcfg.get("auto_refresh", True)):
        raise AuthError(
            f"no valid token in {path} and auto_refresh is off; "
            "run `python -m bmwcpo.auth` or scripts/save_auth.sh"
        )
    return refresh(cfg), "fetched"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="config.toml")
    ap.add_argument("--force", action="store_true", help="fetch a new token even if the current one is valid")
    args = ap.parse_args()
    with open(args.config, "rb") as f:
        cfg = tomllib.load(f)
    try:
        value, source = ensure(cfg, force=args.force)
    except AuthError as e:
        print(f"error: {e}")
        return 1
    exp = token_expiry(value)
    when = dt.datetime.fromtimestamp(exp).strftime("%Y-%m-%d %H:%M") if exp else "unknown"
    verb = {"fetched": "auth refreshed", "file": "auth still valid", "env": "using BMW_AUTH"}[source]
    print(f"{verb} (expires {when})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
