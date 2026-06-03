"""Tests for the validation metric engine (scripts/validation/metrics.py) on synthetic data."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "validation"))

import metrics  # noqa: E402
import validate  # noqa: E402


def test_auc_perfect_and_random():
    assert metrics.auc([1, 2, 3, 4], [0, 0, 1, 1]) == 1.0          # perfectly separable
    assert metrics.auc([1, 2, 3, 4], [1, 1, 0, 0]) == 0.0          # perfectly inverted
    assert metrics.auc([1, 1, 1, 1], [0, 1, 0, 1]) == 0.5          # all ties -> 0.5
    assert metrics.auc([1, 2], [1, 1]) is None                     # one class -> undefined


def test_brier_and_ece_bounds():
    probs = [0.1, 0.2, 0.8, 0.9]
    labels = [0, 0, 1, 1]
    assert 0.0 <= metrics.brier(probs, labels) <= 1.0
    assert 0.0 <= metrics.ece(probs, labels) <= 1.0


def test_logistic_recovers_protective_direction():
    # higher score -> lower event probability; fitted weight on score must be negative.
    import random
    rng = random.Random(1)
    X, y = [], []
    for _ in range(500):
        s = rng.uniform(0, 100)
        p = 1.0 / (1.0 + pow(2.718281828, -(2.0 - 0.05 * s)))
        X.append([s])
        y.append(1 if rng.random() < p else 0)
    model = metrics.logistic_fit(X, y, iters=1500)
    assert model["weights"][0] < 0
    probs = metrics.predict_proba(model, X)
    assert metrics.auc(probs, y) > 0.7


def test_reliability_table_partitions_all_rows():
    probs = [i / 100 for i in range(100)]
    labels = [0, 1] * 50
    table = metrics.reliability_table(probs, labels, bins=10)
    assert sum(r["n"] for r in table) == 100


def test_synthetic_run_is_directionally_correct():
    rows = validate.synthetic_cohort(1500, seed=3)
    rep = validate.run(rows, "score_pct", "deceased", "age", "sex", cal_iters=1500)
    # protective score -> AUC(score predicts survival) > 0.5
    assert rep["discrimination"]["auc_score_predicts_survival"] > 0.55
    # adding age/sex the calibration model should discriminate and be reasonably calibrated
    assert rep["calibration"]["auc_calibrated_predicts_deceased"] > 0.6
    assert rep["calibration"]["ece"] < 0.1
    # 'score' weight in the mortality model is negative (protective)
    assert rep["calibration_model"]["standardized_weights"][0] < 0


def test_score_distribution_splits_by_group():
    rows = [{"score": 10, "g": "a"}, {"score": 90, "g": "b"}, {"score": 20, "g": "a"}]
    d = metrics.score_distribution(rows, "score", by="g")
    assert "by_g" in d and set(d["by_g"]) == {"a", "b"}
