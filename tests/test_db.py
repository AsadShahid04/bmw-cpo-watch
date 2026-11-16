from bmwcpo import db


def test_upsert_returns_previous_price_and_history(tmp_path):
    conn = db.connect(str(tmp_path / "t.sqlite"))
    l = {"vin": "V1", "price": 30000, "option_codes": ["337"], "option_names": []}
    assert db.upsert_listing(conn, l, True, now=1) == (True, None)
    assert db.upsert_listing(conn, l, True, now=2) == (False, 30000)
    l["price"] = 29000
    assert db.upsert_listing(conn, l, True, now=3) == (False, 30000)
    rows = conn.execute("SELECT price FROM price_history WHERE vin='V1' ORDER BY id").fetchall()
    assert [r["price"] for r in rows] == [30000, 29000]


def test_cache_roundtrip(tmp_path):
    conn = db.connect(str(tmp_path / "t.sqlite"))
    k = db.cache_key("http://x", {"a": 1})
    assert db.cache_get(conn, k, 60) is None
    db.cache_put(conn, k, "http://x", "{}")
    assert db.cache_get(conn, k, 60) == "{}"


def test_hit_transitions_and_gone(tmp_path):
    conn = db.connect(str(tmp_path / "t.sqlite"))
    assert not db.has_hits(conn, "s")
    assert db.record_hit(conn, "s", "A", True, 10.0, now=100) is True     # new match
    assert db.record_hit(conn, "s", "B", False, 20.0, now=100) is False   # seen, not a match
    assert db.record_hit(conn, "s", "A", True, 10.0, now=200) is False    # still a match
    assert db.record_hit(conn, "s", "B", True, 20.0, now=200) is True     # became a match
    assert db.mark_gone(conn, "s", 200) == []
    db.record_hit(conn, "s", "B", True, 20.0, now=300)                    # A missing this run
    assert db.mark_gone(conn, "s", 300) == ["A"]
    assert db.record_hit(conn, "s", "A", True, 10.0, now=400) is True     # relisted -> new again


def test_stats_reset_when_signature_changes(tmp_path):
    conn = db.connect(str(tmp_path / "t.sqlite"))
    db.set_stats(conn, "s", "sig1", 80, now=1)
    assert db.last_total(conn, "s", "sig1") == 80
    assert db.last_total(conn, "s", "sig2") is None
