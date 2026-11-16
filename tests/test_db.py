from bmwcpo import db


def test_upsert_and_price_history(tmp_path):
    conn = db.connect(str(tmp_path / "t.sqlite"))
    l = {"vin": "V1", "price": 30000, "option_codes": ["337"], "option_names": []}
    assert db.upsert_listing(conn, l, True) is True
    assert db.upsert_listing(conn, l, True) is False
    l["price"] = 29000
    db.upsert_listing(conn, l, True)
    rows = conn.execute("SELECT price FROM price_history WHERE vin='V1' ORDER BY id").fetchall()
    assert [r["price"] for r in rows] == [30000, 29000]


def test_cache_roundtrip(tmp_path):
    conn = db.connect(str(tmp_path / "t.sqlite"))
    k = db.cache_key("http://x", {"a": 1})
    assert db.cache_get(conn, k, 60) is None
    db.cache_put(conn, k, "http://x", "{}")
    assert db.cache_get(conn, k, 60) == "{}"
