"""Schema validity of the bundled model YAMLs (audit #11: model YAML schema validity)."""
import pytest

from centenarian_phenotype import load_model
from centenarian_phenotype.longevity import _load_calibration, _load


@pytest.mark.parametrize("layer", [1, 2])
def test_quiz_model_schema(layer):
    m = load_model(layer)
    for key in ("model", "layer", "version", "narrative_template", "scoring", "questions"):
        assert key in m, f"tier{layer} missing {key}"
    assert m["scoring"]["method"] == "evidence_weighted_alignment"
    assert isinstance(m["scoring"]["completeness_pct"], int)
    ids = set()
    for q in m["questions"]:
        for key in ("id", "domain", "weight", "text", "options"):
            assert key in q, f"{q.get('id')} missing {key}"
        assert q["id"] not in ids, f"duplicate question id {q['id']}"
        ids.add(q["id"])
        assert q["options"], f"{q['id']} has no options"
        for o in q["options"]:
            assert "label" in o and "basis" in o
            assert 0.0 <= o["alignment"] <= 1.0


def test_tier3_schema():
    t3 = load_model(3)
    assert t3["scoring"]["completeness_pct"] == 80
    assert "clinical_disease_flags" not in t3  # disease diagnoses are self-report at Layer 2
    for grp in ("clinical_biomarkers", "genomic_variants", "epigenetic_methylation"):
        assert t3[grp], f"{grp} empty"
        for f in t3[grp]:
            assert isinstance(f["weight"], (int, float))
            assert f.get("basis")
    feats = {f["feature"] for f in t3["clinical_biomarkers"]}
    assert {"glucose", "hba1c", "egfr"} <= feats  # widened panel present


def test_longevity_baselines_schema():
    doc = _load()
    assert doc["baselines"] and "source" in doc
    row = next(iter(doc["baselines"].values()))
    for k in ("country_name", "p_reach_100_from_65", "ex65"):
        assert k in row


def test_survival_calibration_schema_if_present():
    cal = _load_calibration()
    if cal is None:
        pytest.skip("survival_calibration.yaml not bundled")
    assert len(cal["standardized_weights"]) == len(cal["features"]) == len(cal["feature_stats"])
    assert cal["horizon_months"] == 120
    assert "heldout" in cal and cal["heldout"]["auc"] is not None
