from bmwcpo.client import get_path, normalize
from bmwcpo.codes import normalize_code
from bmwcpo.filters import color_match, failed_rules, matches

RULES = {"required_codes": ["337", "5AU"], "colors": ["Brooklyn Grey", "Portimao Blue"]}


def car(**kw):
    base = {
        "vin": "WBA00000000000001",
        "model": "330i xDrive",
        "year": 2024,
        "color_name": "Brooklyn Grey Metallic",
        "option_codes": ["0337", "05AU"],
        "option_names": [],
        "price": 38000,
        "mileage": 20000,
        "dealer_distance": 350.0,
    }
    base.update(kw)
    return base


def test_normalize_code():
    assert normalize_code("S337A") == "337"
    assert normalize_code("SA5AU") == "5AU"
    assert normalize_code("S5AU") == "5AU"
    assert normalize_code("337") == "337"
    assert normalize_code("c4p") == "C4P"
    # padded codes from the live BMW inventory API
    assert normalize_code("0337") == "337"
    assert normalize_code("05AU") == "5AU"
    assert normalize_code("0ZDY") == "ZDY"


def test_pipe_delimited_codes_from_live_api_shape():
    raw = {"vin": "V1", "exterior": "Brooklyn Grey Metallic", "allCodes": "01PP|0337|05AU|0ZPP"}
    n = normalize(raw, {"vin": "vin", "color_name": "exterior", "option_codes": "allCodes"})
    assert n["option_codes"] == ["01PP", "0337", "05AU", "0ZPP"]
    assert matches(n, RULES)
    n["option_codes"].remove("05AU")
    assert failed_rules(n, RULES) == ["required_codes:5AU"]


def test_match_by_codes_and_colors():
    assert matches(car(), RULES)
    assert matches(car(color_name="Portimao Blue Metallic"), RULES)


def test_color_folding_accents_and_gray():
    assert color_match(car(color_name="Portimão Blue Metallic"), ["Portimao Blue"]) == "Portimao Blue"
    assert color_match(car(color_name="Brooklyn Gray"), ["Brooklyn Grey"]) == "Brooklyn Grey"


def test_phytonic_is_not_portimao():
    assert color_match(car(color_name="Phytonic Blue Metallic"), ["Portimao Blue"]) is None
    assert "colors" in failed_rules(car(color_name="Phytonic Blue Metallic"), RULES)


def test_name_fallback_when_codes_absent():
    l = car(option_codes=[], option_names=["M Sport Package", "Driving Assistance Professional Package"])
    assert matches(l, RULES)


def test_numeric_limits():
    rules = {"max_price": 40000, "max_miles": 25000, "max_distance": 500, "min_year": 2023, "max_year": 2024}
    assert matches(car(), rules)
    assert failed_rules(car(price=45000, mileage=30000), rules) == ["max_price", "max_miles"]
    assert failed_rules(car(dealer_distance=900, year=2022), rules) == ["max_distance", "min_year"]
    assert failed_rules(car(year=2025), rules) == ["max_year"]


def test_unknown_values_pass_limits():
    assert matches(car(price=None, mileage=None, dealer_distance=None), {"max_price": 1, "max_miles": 1, "max_distance": 1})


def test_any_codes_for_hud():
    hud = {"required_codes": ["5AU"], "any_codes": ["6U3", "610"]}
    assert matches(car(option_codes=["05AU", "06U3"]), hud)        # curved display with HUD
    assert matches(car(option_codes=["05AU", "0610"]), hud)        # standalone HUD
    assert failed_rules(car(option_codes=["05AU"]), hud) == ["any_codes"]
    assert failed_rules(car(option_codes=["06U3"]), hud) == ["required_codes:5AU"]


def test_models_rule():
    assert matches(car(model="330e"), {"models": ["330e", "M340i"]})
    assert not matches(car(model="330i xDrive"), {"models": ["330e"]})


def test_empty_rules_match_everything():
    assert matches(car(option_codes=[], color_name="White"), {})


def test_get_path_and_normalize():
    raw = {"vin": "V1", "price": 30000, "options": [{"code": "S337A", "name": "M Sport"}, {"code": "S5AU", "name": "DAP"}]}
    assert get_path(raw, "options[].code") == ["S337A", "S5AU"]
    n = normalize(raw, {"vin": "vin", "price": "price", "option_codes": "options[].code", "option_names": "options[].name"})
    assert n["option_codes"] == ["S337A", "S5AU"] and n["price"] == 30000


def test_field_fallback_when_model_is_null():
    fields = {"vin": "vin", "model": ["model", "trimDescription"]}
    assert normalize({"vin": "V1", "model": None, "trimDescription": "330i"}, fields)["model"] == "330i"
    assert normalize({"vin": "V1", "model": "330e", "trimDescription": "x"}, fields)["model"] == "330e"
    assert normalize({"vin": "V1"}, fields)["model"] is None
