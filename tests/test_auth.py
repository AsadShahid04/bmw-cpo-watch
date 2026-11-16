import base64
import json
import stat
import time

import pytest

from bmwcpo import auth, client, db


def fake_jwt(exp: int) -> str:
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{enc({'alg': 'HS256'})}.{enc({'exp': exp, 'iat': exp - 86400})}.sig"


class FakeResp:
    def __init__(self, status=200, data=None, text=""):
        self.status_code = status
        self._data = data
        self.text = text

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def cfg_for(tmp_path, **token):
    return {
        "api": {"auth_env": "BMW_AUTH_TEST", "auth_file": str(tmp_path / "auth.txt")},
        "token": {"client_auth": "Basic x", **token},
    }


@pytest.fixture(autouse=True)
def no_env(monkeypatch):
    monkeypatch.delenv("BMW_AUTH_TEST", raising=False)


def test_token_expiry_bearer_and_bare():
    exp = int(time.time()) + 3600
    assert auth.token_expiry(f"Bearer {fake_jwt(exp)}") == exp
    assert auth.token_expiry(fake_jwt(exp)) == exp
    assert auth.token_expiry("not a jwt") is None


def test_ensure_uses_valid_file_without_network(tmp_path, monkeypatch):
    cfg = cfg_for(tmp_path)
    value = f"Bearer {fake_jwt(int(time.time()) + 3600)}"
    auth.save(value, tmp_path / "auth.txt")
    monkeypatch.setattr(auth.requests, "post", lambda *a, **k: pytest.fail("should not fetch"))
    assert auth.ensure(cfg) == (value, "file")


def test_ensure_refreshes_expiring_token(tmp_path, monkeypatch):
    cfg = cfg_for(tmp_path)
    auth.save(f"Bearer {fake_jwt(int(time.time()) + 60)}", tmp_path / "auth.txt")  # < margin
    new_jwt = fake_jwt(int(time.time()) + 86400)
    monkeypatch.setattr(auth.requests, "post", lambda *a, **k: FakeResp(200, {"access_token": new_jwt}))
    value, source = auth.ensure(cfg)
    assert (value, source) == (f"Bearer {new_jwt}", "fetched")
    path = tmp_path / "auth.txt"
    assert path.read_text().strip() == f"Bearer {new_jwt}"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_env_var_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("BMW_AUTH_TEST", "Bearer from-env")
    assert auth.ensure(cfg_for(tmp_path)) == ("Bearer from-env", "env")


def test_fetch_errors_do_not_leak(tmp_path, monkeypatch):
    monkeypatch.setattr(auth.requests, "post", lambda *a, **k: FakeResp(401, {}))
    with pytest.raises(auth.AuthError, match="HTTP 401"):
        auth.ensure(cfg_for(tmp_path))


def test_no_refresh_when_disabled(tmp_path):
    with pytest.raises(auth.AuthError, match="auto_refresh is off"):
        auth.ensure(cfg_for(tmp_path, auto_refresh=False))


def test_client_refreshes_once_on_401(tmp_path, monkeypatch):
    cfg = cfg_for(tmp_path)
    cfg["api"].update(url="https://example.test/vehicle", method="POST", page_size=2,
                      max_pages=1, results_path="vehicles")
    cfg.update(cache_ttl_seconds=0, delay_range_seconds=[0, 0])
    search = {"name": "s", "zip": "95391", "radius": 100, "filters": {}, "match": {}}
    auth.save(f"Bearer {fake_jwt(int(time.time()) + 3600)}", tmp_path / "auth.txt")
    new_jwt = fake_jwt(int(time.time()) + 86400)
    monkeypatch.setattr(auth.requests, "post", lambda *a, **k: FakeResp(200, {"access_token": new_jwt}))

    sent = []

    def fake_request(self, method, url, **kw):
        sent.append(self.headers["Authorization"])
        if len(sent) == 1:
            return FakeResp(401)
        return FakeResp(200, text=json.dumps({"vehicles": [{"vin": "V1"}]}))

    monkeypatch.setattr(client.requests.Session, "request", fake_request)
    conn = db.connect(str(tmp_path / "t.sqlite"))
    c = client.Client(cfg, conn)
    vehicles, meta = c.fetch_search(search)
    assert [v["vin"] for v in vehicles] == ["V1"]
    assert len(sent) == 2 and sent[1] == f"Bearer {new_jwt}"
    assert meta["requests"] == 2 and c.requests == 2


def test_client_stops_when_token_rejected_twice(tmp_path, monkeypatch):
    cfg = cfg_for(tmp_path)
    cfg["api"].update(url="https://example.test/vehicle", method="POST", page_size=2,
                      max_pages=1, results_path="vehicles")
    cfg.update(cache_ttl_seconds=0, delay_range_seconds=[0, 0])
    auth.save(f"Bearer {fake_jwt(int(time.time()) + 3600)}", tmp_path / "auth.txt")
    monkeypatch.setattr(auth.requests, "post", lambda *a, **k: FakeResp(200, {"access_token": fake_jwt(int(time.time()) + 86400)}))
    monkeypatch.setattr(client.requests.Session, "request", lambda self, *a, **k: FakeResp(403))
    c = client.Client(cfg, db.connect(str(tmp_path / "t.sqlite")))
    with pytest.raises(client.FatalError, match="HTTP 403"):
        c.fetch_search({"name": "s", "zip": "95391", "radius": 100, "filters": {}, "match": {}})
