"""Prove the four-class Naive Bayes posterior layer is actually used and is responsive."""
import pytest

from centenarian_phenotype import score, load_model
from centenarian_phenotype.naive_bayes import CLASSES, class_posteriors, DEFAULT_PRIORS, MU


def truemax(model):
    return {q["id"]: max(range(len(q["options"])), key=lambda j: q["options"][j]["alignment"])
            for q in model["questions"]}


def worst(model):
    return {q["id"]: len(q["options"]) - 1 for q in model["questions"]}


def test_score_exposes_class_posteriors_summing_to_one():
    r = score(1, truemax(load_model(1)))
    post = r["class_posteriors"]
    assert set(post) == set(CLASSES)
    assert abs(sum(post.values()) - 1.0) < 1e-6
    assert "centenarian_posterior" in r and "supercentenarian_posterior" in r
    assert r["calibration"] == "heuristic_pending"


def test_high_alignment_shifts_mass_to_longevity_classes():
    hi = score(1, truemax(load_model(1)))
    lo = score(1, worst(load_model(1)))
    # A centenarian-like profile must carry more centenarian+super mass than a poor profile.
    assert (hi["centenarian_posterior"] + hi["supercentenarian_posterior"]
            > lo["centenarian_posterior"] + lo["supercentenarian_posterior"])
    assert lo["class_posteriors"]["general_population"] > hi["class_posteriors"]["general_population"]


def test_posterior_changes_when_feature_evidence_changes():
    items_lo = [{"alignment": 0.3, "eff_weight": 1.0}]
    items_hi = [{"alignment": 0.9, "eff_weight": 1.0}]
    assert (class_posteriors(items_hi)["centenarian_100_109"]
            > class_posteriors(items_lo)["centenarian_100_109"])


def test_posterior_changes_when_priors_change():
    items = [{"alignment": 0.7, "eff_weight": 1.0}]
    base = class_posteriors(items)
    cent_heavy = class_posteriors(items, priors={**DEFAULT_PRIORS,
                                                 "centenarian_100_109": 0.5, "general_population": 0.28})
    assert cent_heavy["centenarian_100_109"] > base["centenarian_100_109"]


def test_posterior_changes_when_likelihood_centroids_change():
    items = [{"alignment": 0.7, "eff_weight": 1.0}]
    base = class_posteriors(items)
    # Move the centenarian centroid onto the observed alignment -> its likelihood rises.
    shifted = class_posteriors(items, mu={**MU, "centenarian_100_109": 0.70})
    assert shifted["centenarian_100_109"] > base["centenarian_100_109"]


def test_no_items_returns_priors():
    assert class_posteriors([]) == pytest.approx(DEFAULT_PRIORS)


def test_higher_weight_features_count_more():
    # Two conflicting features; the heavier one (high alignment) should dominate the posterior.
    items = [{"alignment": 0.9, "eff_weight": 5.0}, {"alignment": 0.3, "eff_weight": 0.5}]
    post = class_posteriors(items)
    assert post["centenarian_100_109"] + post["supercentenarian_110_plus"] > 0.5
