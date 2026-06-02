"""Biological-age clock interface: panel construction, alignment, and scoreable-only feed."""
import pytest

from centenarian_phenotype import score
from centenarian_phenotype.clocks import (CLOCKS, compute_clock, compute_panel, describe_clocks,
                                          to_clinical_alignments)


def test_every_clock_self_describes():
    for d in describe_clocks():
        for f in ("kind", "output_type", "tissue", "platform", "availability", "evidence_grade",
                  "limitations"):
            assert d[f] not in (None, ""), f"{d['name']} missing {f}"
        assert d["availability"] in ("free_open", "requires_coefficients", "restricted")
        assert d["output_type"] in ("biological_age", "age_acceleration", "pace", "length",
                                    "index", "risk_score", "biological_age")


def test_biological_age_clock_computes_delta_and_alignment():
    # Biological age younger than chronological -> negative delta -> high alignment.
    young = compute_clock("horvath_2013", value=60, chronological_age=70)
    old = compute_clock("horvath_2013", value=80, chronological_age=70)
    assert young["age_adjusted_delta"] == -10.0
    assert old["age_adjusted_delta"] == 10.0
    assert young["alignment"] > old["alignment"]


def test_biological_age_clock_requires_chronological_age():
    e = compute_clock("horvath_2013", value=60)
    assert e["alignment"] is None and any("chronological_age" in w for w in e["warnings"])


def test_pace_clock_uses_native_value():
    fast = compute_clock("dunedinpace_2022", value=1.3)
    slow = compute_clock("dunedinpace_2022", value=0.8)
    assert slow["alignment"] > fast["alignment"]


def test_frailty_index_lower_is_better():
    assert compute_clock("frailty_index", value=0.1)["alignment"] > \
           compute_clock("frailty_index", value=0.6)["alignment"]


def test_pending_clock_is_inert():
    e = compute_clock("proteomic_aging_clock", value=55, chronological_age=70)
    assert e["alignment"] is None and e["scoreable"] is False
    assert any("pending" in w for w in e["warnings"])


def test_panel_feeds_only_scoreable_clocks_by_default():
    panel = compute_panel(
        {"grimage_2019": {"value": 65, "chronological_age": 72},     # scoreable
         "skinblood_2018": {"value": 65, "chronological_age": 72}},  # not scoreable
        sex="M")
    clin = to_clinical_alignments(panel)
    assert "grimage_2019" in clin
    assert "skinblood_2018" not in clin  # not wired into a tier model
    # override lets research include it
    assert "skinblood_2018" not in to_clinical_alignments(panel)  # no score_feature -> still excluded


def test_panel_round_trips_into_layer3_scoring():
    panel = compute_panel({"grimage_2019": {"value": 60, "chronological_age": 72},
                           "telomere_length": 1.6}, sex="F")
    clin = to_clinical_alignments(panel)
    r = score(3, {"q_smoking": 0}, clinical=clin)
    assert r["score_pct"] >= 0
    assert "epigenetic_youthfulness_slow_pace_context" in r["domain_scores"]


def test_unknown_clock_raises():
    with pytest.raises(KeyError):
        compute_clock("not_a_clock", value=1)
