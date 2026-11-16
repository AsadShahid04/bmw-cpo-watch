import copy

import pytest

from bmwcpo import config

REAL = config.load("config.toml", local=False)


def test_repo_config_is_valid_and_clean():
    errors, warnings = config.validate(REAL)
    assert errors == [] and warnings == []
    names = [s["name"] for s in config.searches(REAL)]
    assert names == ["g20-msport-dap-pro", "dap-pro-hud"]  # the example search is disabled


def test_local_overrides_merge(tmp_path):
    base = tmp_path / "config.toml"
    base.write_text(open("config.toml").read())
    (tmp_path / "config.local.toml").write_text(
        '[alerts]\nmin_price_drop = 500\n'
        '[[searches]]\nname = "dap-pro-hud"\nenabled = false\n'
        '[[searches]]\nname = "g20-msport-dap-pro"\nradius = 600\n'
        '[[searches]]\nname = "mine"\nzip = "94704"\nradius = 50\nfilters = { Series = ["X3"] }\n'
    )
    cfg = config.load(str(base))
    assert cfg["_local_config"].endswith("config.local.toml")
    assert cfg["alerts"]["min_price_drop"] == 500
    assert cfg["health"] == REAL["health"]  # untouched sections kept
    assert [s["name"] for s in config.searches(cfg)] == ["g20-msport-dap-pro", "mine"]
    g20 = config.searches(cfg)[0]
    assert g20["radius"] == 600 and g20["match"]["required_codes"] == ["337", "5AU"]  # rest kept
    assert config.validate(cfg)[0] == []
    assert "_local_config" not in config.load(str(base), local=False)


def test_only_selects_disabled_search_by_name():
    [s] = config.searches(REAL, only="m340i-west")
    assert s["radius"] == 500 and s["match"] == {"max_price": 50000, "max_miles": 30000}
    with pytest.raises(config.ConfigError):
        config.searches(REAL, only="nope")


def test_build_body_matches_site_request_shape():
    s = config.searches(REAL)[0]
    body = config.build_body(REAL, s, offset=200, page_size=100)
    assert body["pageIndex"] == 200 and body["PageSize"] == 100
    assert body["postalCode"] == "95391" and body["radius"] == 3000
    assert {"name": "Option", "values": ["M Sport Package"]} in body["filters"]
    assert body["includeVehicles"] is True and body["includeFacets"] is False
    assert config.build_body(REAL, s, offset=0, page_size=1, include_facets=True)["includeFacets"] is True


def test_validate_reports_mistakes():
    cfg = copy.deepcopy(REAL)
    cfg["searches"] = [
        {"name": "a", "zip": "9539", "radius": 100, "filters": {"Colour": ["Blue"]}, "match": {"max_prise": 1}},
        {"name": "a", "zip": "95391", "radius": -5, "filters": {"Series": "3 Series"}},
    ]
    errors, warnings = config.validate(cfg)
    joined = " | ".join(errors)
    assert "zip must be a 5-digit string" in joined
    assert "unknown match rule 'max_prise'" in joined
    assert "duplicate name" in joined
    assert "radius must be a positive integer" in joined
    assert "filter Series must be a non-empty list" in joined
    assert any("'Colour' is not a known API facet" in w for w in warnings)


def test_validate_requires_searches():
    cfg = copy.deepcopy(REAL)
    cfg["searches"] = []
    assert config.validate(cfg)[0] == ["config has no [[searches]] entries"]
