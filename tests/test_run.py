"""End-to-end runner tests with a fake API client (no network)."""

import json

from bmwcpo import config, db, run
from bmwcpo.client import FatalError

CFG = config.load("config.toml")
SEARCH = {"name": "s", "description": "", "zip": "95391", "radius": 3000,
          "filters": {"Series": ["3 Series"]},
          "match": {"required_codes": ["337", "5AU"], "colors": ["Portimao Blue"]}}


def v(vin, price, match=True, miles=10000):
    return {"vin": vin, "year": 2023, "model": "330i", "internetPrice": price, "odometer": miles,
            "exterior": "Portimao Blue Metallic" if match else "Alpine White",
            "allCodes": "0337|05AU", "dealerCode": "D1", "distance": 100.0, "vdpUrl": f"https://x/{vin}"}


class FakeClient:
    def __init__(self, batches):
        self.batches = batches  # list of vehicle lists, or an exception to raise
        self.requests = 0

    def fetch_search(self, search):
        self.requests += 1
        b = self.batches.pop(0)
        if isinstance(b, Exception):
            raise b
        return b, {"total_records": len(b), "fetched": len(b), "requests": 1}


def types(report):
    return [a["type"] for a in report["alerts"]]


def test_alert_lifecycle(tmp_path):
    conn = db.connect(str(tmp_path / "t.sqlite"))
    client = FakeClient([
        [v("A", 40000), v("B", 30000, match=False), v("C", 35000)],
        [v("A", 39000), v("B", 30000, match=False), v("D", 41000)],
    ])
    # Run 1: first time this search runs -> baseline, not "new".
    r1 = run.run_searches(CFG, conn, [SEARCH], client, now=1000)
    assert r1["status"] == "ok" and types(r1) == ["search_started"]
    assert {c["vin"] for c in r1["alerts"][0]["matches"]} == {"A", "C"}
    # Run 2: A drops $1,000, C disappears, D is new.
    r2 = run.run_searches(CFG, conn, [SEARCH], client, now=2000)
    assert r2["status"] == "ok"
    assert sorted(types(r2)) == ["match_gone", "new_match", "price_drop"]
    drop = next(a for a in r2["alerts"] if a["type"] == "price_drop")
    assert (drop["vin"], drop["old_price"], drop["new_price"], drop["drop"]) == ("A", 40000, 39000, 1000)
    assert next(a for a in r2["alerts"] if a["type"] == "match_gone")["vin"] == "C"
    assert next(a for a in r2["alerts"] if a["type"] == "new_match")["vin"] == "D"
    assert r2["searches"][0]["matches"] == 2
    assert "PRICE DROP" in run.format_text(r2) and "NEW MATCH" in run.format_text(r2)


def test_zero_results_warns_and_does_not_mark_gone(tmp_path):
    conn = db.connect(str(tmp_path / "t.sqlite"))
    client = FakeClient([[v("A", 40000), v("C", 35000)], []])
    run.run_searches(CFG, conn, [SEARCH], client, now=1000)
    r = run.run_searches(CFG, conn, [SEARCH], client, now=2000)
    assert r["status"] == "warning"
    assert types(r) == ["health"] and "0 cars returned" in r["alerts"][0]["message"]
    assert r["searches"][0]["matches"] == 2  # nothing falsely marked as sold


def test_sharp_drop_warns_once(tmp_path):
    conn = db.connect(str(tmp_path / "t.sqlite"))
    many = [v(f"N{i}", 30000, match=False) for i in range(10)]
    client = FakeClient([many, many[:3], many[:3]])
    run.run_searches(CFG, conn, [SEARCH], client, now=1000)
    r2 = run.run_searches(CFG, conn, [SEARCH], client, now=2000)
    assert r2["status"] == "warning" and "sharp drop" in r2["alerts"][0]["message"]
    r3 = run.run_searches(CFG, conn, [SEARCH], client, now=3000)
    assert r3["status"] == "ok"


def test_token_failure_is_an_error_and_skips_other_searches(tmp_path):
    conn = db.connect(str(tmp_path / "t.sqlite"))
    other = {**SEARCH, "name": "t"}
    client = FakeClient([FatalError("token endpoint returned HTTP 401")])
    r = run.run_searches(CFG, conn, [SEARCH, other], client, now=1000)
    assert r["status"] == "error"
    msgs = [a["message"] for a in r["alerts"]]
    assert msgs[0] == "token endpoint returned HTTP 401" and "skipped" in msgs[1]
    assert run.EXIT_CODES[r["status"]] == 2


def test_multiple_searches_share_listings(tmp_path):
    conn = db.connect(str(tmp_path / "t.sqlite"))
    cheap = {**SEARCH, "name": "cheap", "match": {"max_price": 36000}}
    client = FakeClient([[v("A", 40000), v("C", 35000)], [v("A", 40000), v("C", 35000)]])
    r = run.run_searches(CFG, conn, [SEARCH, cheap], client, now=1000)
    by = {e["name"]: e for e in r["searches"]}
    assert by["s"]["matches"] == 2 and by["cheap"]["matches"] == 1
    assert conn.execute("select count(*) from listings").fetchone()[0] == 2


def test_dry_run_makes_no_db_or_network(tmp_path, capsys):
    db_path = tmp_path / "t.sqlite"
    assert run.main(["--dry-run", "--db", str(db_path)]) == 0
    assert "DRY RUN" in capsys.readouterr().out and not db_path.exists()


def test_main_writes_report_and_exit_code(tmp_path, monkeypatch):
    monkeypatch.setattr(run.Client, "fetch_search", lambda self, s: ([v("A", 40000)], {"total_records": 1, "requests": 0}))
    report = tmp_path / "last_run.json"
    code = run.main(["--db", str(tmp_path / "t.sqlite"), "--report", str(report), "--json"])
    data = json.loads(report.read_text())
    assert code == 0 and data["status"] == "ok" and data["alerts"][0]["type"] == "search_started"


def test_bad_config_exits_2(tmp_path):
    bad = tmp_path / "c.toml"
    bad.write_text("[[searches]]\nname='x'\nzip='1'\n[api]\n[fields]\n")
    assert run.main(["--config", str(bad), "--dry-run"]) == 2
