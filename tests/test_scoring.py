"""Invariant tests for the Centenarian Phenotype scoring package."""
import math

import pytest

from centenarian_phenotype import score, load_model, MODEL_VERSIONS
from centenarian_phenotype.scoring import _MODEL_FILES


def opt0(model):
    return {q["id"]: 0 for q in model["questions"]}


def worst(model):
    return {q["id"]: len(q["options"]) - 1 for q in model["questions"]}


def truemax(model):
    return {q["id"]: max(range(len(q["options"])), key=lambda j: q["options"][j]["alignment"])
            for q in model["questions"]}


# ---------- structure / schema ----------

def test_models_load_and_have_expected_question_counts():
    assert len(load_model(1)["questions"]) == 12
    assert len(load_model(2)["questions"]) == 31
    assert "questions" not in load_model(3)  # tier 3 is a spec, not a quiz


@pytest.mark.parametrize("layer", [1, 2])
def test_every_option_has_alignment_and_basis(layer):
    for q in load_model(layer)["questions"]:
        assert "weight" in q and isinstance(q["weight"], (int, float))
        assert q["options"], f"{q['id']} has no options"
        for o in q["options"]:
            assert 0.0 <= o["alignment"] <= 1.0, f"{q['id']} alignment out of range"
            assert o.get("basis"), f"{q['id']} option missing basis"


def test_tier3_features_have_weight_and_basis():
    t3 = load_model(3)
    for grp in ("clinical_biomarkers", "clinical_disease_flags", "genomic_variants", "epigenetic_methylation"):
        for f in t3[grp]:
            assert "weight" in f
            assert f.get("basis"), f"{grp} entry missing basis"


# ---------- score ranges ----------

def test_layer1_range():
    t1 = load_model(1)
    assert score(1, truemax(t1))["score_pct"] == 97.5
    assert score(1, worst(t1))["score_pct"] == 25.9


def test_layer2_range_within_bounds():
    t2 = load_model(2)
    hi = score(2, truemax(t2))["score_pct"]
    lo = score(2, worst(t2))["score_pct"]
    assert 95.0 < hi <= 100.0
    assert 25.0 < lo < hi


def test_scores_bounded_0_100():
    t1 = load_model(1)
    r = score(1, opt0(t1))
    assert 0 <= r["ci_lower_pct"] <= r["score_pct"] <= r["ci_upper_pct"] <= 100


# ---------- completeness ladder ----------

def test_completeness_ladder():
    t1, t2, t3 = load_model(1), load_model(2), load_model(3)
    clin = {c["clock"]: 0.9 for c in t3["epigenetic_methylation"]}
    assert score(1, opt0(t1))["completeness_pct"] == 30
    assert score(2, opt0(t2))["completeness_pct"] == 50
    assert score(3, opt0(t2), clinical=clin)["completeness_pct"] == 80


# ---------- gwas invariant ----------

def test_gwas_invariant():
    t1, t2, t3 = load_model(1), load_model(2), load_model(3)
    clin = {**{c["clock"]: 0.9 for c in t3["epigenetic_methylation"]},
            **{v["variant"]: 1.0 for v in t3["genomic_variants"]}}
    assert score(1, opt0(t1))["gwas_corroborated_weight_share_pct"] == 0.0
    assert score(2, opt0(t2))["gwas_corroborated_weight_share_pct"] == 0.0
    assert score(3, opt0(t2), clinical=clin)["gwas_corroborated_weight_share_pct"] > 0.0


# ---------- L3 evolves from L2 (carries all L2 questions) + construct dedup ----------

def test_layer3_includes_all_layer2_questions():
    t2 = load_model(2)
    a = opt0(t2)
    r = score(3, a, clinical={"grimage_2019": 0.9})  # epigenetic clock — no construct dedup
    assert r["answered"] == len(t2["questions"]) + 1  # all 31 L2 questions + 1 lab
    assert r["layers_included"] == [2, 3]


def test_layer3_is_higher_confidence_than_layer2():
    # same similarity construct, rising confidence: completeness L2 < L3
    t2 = load_model(2)
    a = opt0(t2)
    assert score(2, a)["confidence_pct"] < score(3, a, clinical={"grimage_2019": 0.9})["confidence_pct"]


def test_deepest_layer_wins_dedup():
    t2 = load_model(2)
    # supplying measured diabetes should supersede the L2 self-report q_diabetes
    r = score(3, opt0(t2), clinical={"diabetes": 1.0})
    assert "q_diabetes" in r["superseded_by_l3"]


# ---------- provenance + versioning ----------

def test_evidence_basis_pct_sums_to_about_100():
    t1 = load_model(1)
    total = sum(score(1, opt0(t1))["evidence_basis_pct"].values())
    assert math.isclose(total, 100.0, abs_tol=0.5)


def test_model_version_stamped():
    t1 = load_model(1)
    assert "model_version" in score(1, opt0(t1))
    assert set(_MODEL_FILES) == {1, 2, 3}
    assert MODEL_VERSIONS[1] and MODEL_VERSIONS[2] and MODEL_VERSIONS[3]


# ---------- phenotype decomposition (secondary domains; primary endpoint unchanged) ----------

def test_primary_endpoint_unchanged_by_decomposition():
    # Adding domain_scores must not move the headline similarity number.
    t1 = load_model(1)
    assert score(1, truemax(t1))["score_pct"] == 97.5


def test_domain_scores_present_and_bounded():
    t2 = load_model(2)
    ds = score(2, opt0(t2))["domain_scores"]
    assert ds  # at least one interpretive domain emitted
    for d in ds.values():
        assert 0.0 <= d["score_pct"] <= 100.0
        assert d["n_features"] >= 1


def test_layer3_emits_genetic_and_epigenetic_context():
    t2, t3 = load_model(2), load_model(3)
    clin = {"grimage_2019": 0.9, "rs2802295": 1.0}
    ds = score(3, opt0(t2), clinical=clin)["domain_scores"]
    assert "genetic_longevity_context" in ds
    assert "epigenetic_youthfulness_slow_pace_context" in ds


def test_product_output_fields_present():
    t2 = load_model(2)
    r = score(2, opt0(t2))
    for f in ("total_similarity_score", "class_posteriors", "domain_scores", "top_positive_drivers",
              "top_negative_drivers", "modifiable_drivers", "non_modifiable_context",
              "missing_high_value_inputs", "evidence_confidence_pct", "next_best_data_action",
              "pro_unlock_opportunities", "response_completeness_pct", "usable_score", "warnings"):
        assert f in r, f"missing product field {f}"
