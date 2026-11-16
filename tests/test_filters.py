from bmwcpo.client import get_path, normalize
from bmwcpo.codes import normalize_code
from bmwcpo.filters import color_match, matches


def car(**kw):
    base = {
        "vin": "WBA00000000000001",
        "model": "3 Series 330i xDrive",
        "color_name": "Brooklyn Grey Metallic",
        "color_code": "C4P",
        "option_codes": ["S337A", "SA5AU"],
        "option_names": [],
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
    raw = {"vin": "V1", "modelSeries": "3 Series", "exterior": "Brooklyn Grey Metallic",
           "allCodes": "01PP|0337|05AU|0ZPP"}
    n = normalize(raw, {"vin": "vin", "series": "modelSeries", "color_name": "exterior", "option_codes": "allCodes"})
    assert n["option_codes"] == ["01PP", "0337", "05AU", "0ZPP"]
    assert matches(n)
    n["option_codes"].remove("05AU")
    assert not matches(n)


def test_match_by_codes():
    assert matches(car())


def test_match_portimao_by_code_and_name():
    assert matches(car(color_name="", color_code="C31"))
    assert matches(car(color_name="Portimao Blue Metallic", color_code=None))


def test_phytonic_is_not_portimao():
    assert color_match(car(color_name="Phytonic Blue", color_code="C1M")) is None


def test_missing_driving_assistant_fails():
    assert not matches(car(option_codes=["S337A"]))


def test_name_fallback_when_codes_absent():
    l = car(option_codes=[], option_names=["M Sport Package", "Driving Assistant Professional Package"])
    assert matches(l)


def test_wrong_series_fails():
    assert not matches(car(model="X3 xDrive30i"))


def test_get_path_and_normalize():
    raw = {"vin": "V1", "price": 30000, "options": [{"code": "S337A", "name": "M Sport"}, {"code": "S5AU", "name": "DAP"}]}
    assert get_path(raw, "options[].code") == ["S337A", "S5AU"]
    n = normalize(raw, {"vin": "vin", "price": "price", "option_codes": "options[].code", "option_names": "options[].name"})
    assert n["option_codes"] == ["S337A", "S5AU"] and n["price"] == 30000
