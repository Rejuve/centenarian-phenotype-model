"""Raw-value -> alignment mapper behaviour and metadata completeness."""
import pytest

from centenarian_phenotype.mappers import MAPPERS, describe_mappers, map_panel, map_value


def test_every_mapper_self_describes():
    for d in describe_mappers():
        for field in ("units", "accepted_range", "direction", "provenance", "evidence_grade",
                      "version", "missingness"):
            assert d[field] not in (None, ""), f"{d['feature']} missing {field}"
        assert d["evidence_grade"] in ("A", "B", "C")


def test_mappers_produce_alignment_in_unit_interval():
    for feat, m in MAPPERS.items():
        lo, hi = m.accepted_range
        for v in (lo, (lo + hi) / 2, hi):
            a = m(v, sex="M", age=70)["alignment"]
            assert 0.0 <= a <= 1.0, f"{feat} produced {a} for {v}"


def test_direction_is_respected_higher_favorable():
    # HDL is higher-favourable: a high value should out-align a low value.
    assert map_value("hdl_cholesterol", 70, sex="M")["alignment"] > \
           map_value("hdl_cholesterol", 30, sex="M")["alignment"]


def test_direction_is_respected_lower_favorable():
    assert map_value("ldl_cholesterol", 80)["alignment"] > map_value("ldl_cholesterol", 190)["alignment"]


def test_bmi_is_u_shaped():
    mid = map_value("body_mass_index", 22)["alignment"]
    assert mid > map_value("body_mass_index", 16)["alignment"]   # underweight penalised
    assert mid > map_value("body_mass_index", 35)["alignment"]   # obese penalised


def test_sex_adjustment_changes_result():
    # HDL low cut-off differs by sex (50 F vs 40 M): the same value scores differently.
    assert map_value("hdl_cholesterol", 45, sex="F")["alignment"] != \
           map_value("hdl_cholesterol", 45, sex="M")["alignment"]


def test_missing_value_returns_none_not_a_midpoint():
    out = map_value("hdl_cholesterol", None)
    assert out["alignment"] is None
    assert "missing" in out["warnings"]


def test_out_of_range_value_is_clamped_and_warned():
    out = map_value("hdl_cholesterol", 5000, sex="M")  # e.g. wrong units
    assert out["warnings"]
    assert 0.0 <= out["alignment"] <= 1.0


def test_unknown_feature_raises():
    with pytest.raises(KeyError):
        map_value("not_a_marker", 1.0)


def test_map_panel_round_trips_into_scoring():
    from centenarian_phenotype import score
    panel = map_panel({"hdl_cholesterol": 65, "triglycerides": 90, "unknown_x": 1}, sex="M")
    assert "unknown_x" in panel["unmapped"]
    r = score(3, {"q_smoking": 0}, clinical=panel["clinical"])
    assert r["score_pct"] >= 0
