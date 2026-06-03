"""Strict-validation behaviour: unknown IDs, out-of-range, empty, partial, completeness split."""
import pytest

from centenarian_phenotype import score, load_model
from centenarian_phenotype.validation import ValidationError


def opt0(model):
    return {q["id"]: 0 for q in model["questions"]}


# ---------- strict mode rejects bad input ----------

def test_unknown_question_id_raises_in_strict_mode():
    with pytest.raises(ValidationError) as e:
        score(1, {"q_not_a_real_question": 0, "q_smoking": 0})
    assert "q_not_a_real_question" in e.value.report["unknown_inputs"]


def test_invalid_option_index_raises():
    with pytest.raises(ValidationError) as e:
        score(1, {"q_smoking": 99})
    assert e.value.report["out_of_range_values"]


def test_non_integer_option_index_is_invalid():
    with pytest.raises(ValidationError) as e:
        score(1, {"q_smoking": 1.5})
    assert e.value.report["invalid_inputs"]


def test_unknown_clinical_feature_raises_at_layer3():
    with pytest.raises(ValidationError) as e:
        score(3, {"q_smoking": 0}, clinical={"not_a_marker": 0.9})
    assert "not_a_marker" in e.value.report["unknown_inputs"]


def test_clinical_alignment_out_of_range_raises():
    with pytest.raises(ValidationError) as e:
        score(3, {"q_smoking": 0}, clinical={"hdl_cholesterol": 1.7})
    assert e.value.report["out_of_range_values"]


def test_empty_answers_does_not_produce_a_valid_score():
    with pytest.raises(ValidationError) as e:
        score(2, {})
    assert e.value.report["missing_required_inputs"]


# ---------- non-strict downgrades to warnings ----------

def test_non_strict_drops_bad_inputs_and_warns():
    r = score(1, {"q_smoking": 0, "q_bogus": 2}, strict=False)
    assert "q_bogus" in r["warnings"]["unknown_inputs"]
    assert "q_bogus" in r["warnings"]["ignored_inputs"]
    assert r["answered"] == 1  # only the valid one scored


# ---------- completeness split ----------

def test_model_depth_vs_response_completeness_are_distinct():
    t2 = load_model(2)
    full = score(2, opt0(t2))
    partial = score(2, {"q_smoking": 0, "q_diabetes": 0, "q_outlook": 0})
    # Tier depth is the same for both (both are Layer 2)...
    assert full["model_depth_pct"] == partial["model_depth_pct"] == 50
    # ...but response completeness and evidence confidence track what was actually answered.
    assert full["response_completeness_pct"] == 100.0
    assert partial["response_completeness_pct"] < full["response_completeness_pct"]
    assert partial["evidence_confidence_pct"] < full["evidence_confidence_pct"]


def test_usable_score_flag():
    t2 = load_model(2)
    assert score(2, opt0(t2))["usable_score"] is True
    assert score(2, {"q_smoking": 0, "q_diabetes": 0, "q_outlook": 0})["usable_score"] is False


def test_missing_high_value_inputs_ranked_and_actionable():
    partial = score(2, {"q_smoking": 0})
    mhv = partial["missing_high_value_inputs"]
    assert mhv and mhv[0]["weight"] >= mhv[-1]["weight"]  # ranked by weight desc
    assert partial["next_best_data_action"]  # a concrete suggestion is produced


def test_layer1_full_completeness_back_compat():
    # Back-compat: completeness_pct / confidence_pct still equal model depth (30/50/80).
    t1 = load_model(1)
    r = score(1, opt0(t1))
    assert r["completeness_pct"] == r["confidence_pct"] == r["model_depth_pct"] == 30
