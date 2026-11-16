import copy

import pytest

from bmwcpo import config

REAL = config.load("config.toml")


def test_repo_config_is_valid_and_clean():
    errors, warnings = config.validate(REAL)
    assert errors == [] and warnings == []
    names = [s["name"] for s in config.searches(REAL)]
    assert names == ["g20-msport-dap-pro"]  # the example search is disabled


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
