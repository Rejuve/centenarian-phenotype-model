"""Validation metric engine (pure-Python, stdlib only) for the Centenarian Phenotype Model.

Dataset-agnostic: it operates on a "scored cohort" — a list of dicts, each with at least a phenotype
score, an observed binary outcome, and optional grouping fields (sex, age band, country). It powers
`validate.py` and is exercised by `tests/test_validation_harness.py` on a synthetic fixture.

Metrics implemented (no numpy/sklearn so it runs in CI and in the dependency-light spirit of the repo):
  * `auc`               — discrimination (Mann-Whitney, tie-corrected)
  * `reliability_table` — calibration bins (predicted vs observed)
  * `ece`, `brier`      — calibration error / score
  * `logistic_fit` / `predict_proba` — fit a small calibration model (score [+ age/sex] -> P(outcome))
  * `score_distribution`/`group_summary` — distributions by class/group
These map directly to the metrics in VALIDATION_PLAN.md §2.
"""
from __future__ import annotations

import math
from statistics import mean, pstdev


# ---------- discrimination ----------

def auc(scores, labels):
    """Area under ROC for `scores` predicting binary `labels` (1=event). Tie-corrected via ranks."""
    pairs = list(zip(scores, labels))
    n_pos = sum(1 for _, y in pairs if y == 1)
    n_neg = len(pairs) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    order = sorted(range(len(pairs)), key=lambda i: pairs[i][0])
    ranks = [0.0] * len(pairs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and pairs[order[j + 1]][0] == pairs[order[i]][0]:
            j += 1
        avg = (i + j) / 2 + 1  # 1-based average rank for the tie group
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    sum_pos = sum(ranks[i] for i in range(len(pairs)) if pairs[i][1] == 1)
    return (sum_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


# ---------- calibration ----------

def reliability_table(probs, labels, bins=10):
    """Group (prob, label) into equal-width bins; return per-bin predicted vs observed."""
    table = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        sel = [(p, y) for p, y in zip(probs, labels) if (lo <= p < hi) or (b == bins - 1 and p == 1.0)]
        if not sel:
            continue
        table.append({
            "bin": f"[{lo:.1f},{hi:.1f})", "n": len(sel),
            "mean_predicted": round(mean(p for p, _ in sel), 4),
            "observed_freq": round(mean(y for _, y in sel), 4),
        })
    return table


def ece(probs, labels, bins=10):
    """Expected calibration error: weighted |observed - predicted| across bins."""
    n = len(probs)
    if not n:
        return None
    tot = 0.0
    for row in reliability_table(probs, labels, bins):
        tot += row["n"] / n * abs(row["observed_freq"] - row["mean_predicted"])
    return round(tot, 4)


def brier(probs, labels):
    return round(mean((p - y) ** 2 for p, y in zip(probs, labels)), 4) if probs else None


# ---------- a small calibration model: logistic regression (GD on standardized features) ----------

def _standardize(cols):
    stats = []
    for c in cols:
        mu = mean(c)
        sd = pstdev(c) or 1.0
        stats.append((mu, sd))
    return stats


def logistic_fit(X, y, iters=4000, lr=0.1, l2=1e-4):
    """Fit P(y=1) = sigmoid(b0 + B·x). X = list of feature-rows. Returns a model dict.

    Standardizes features internally so a single learning rate works across scales (score 0–100,
    age in years, sex 0/1). Pure-Python; intended for small calibration cohorts.
    """
    if not X:
        raise ValueError("empty design matrix")
    k = len(X[0])
    cols = [[row[j] for row in X] for j in range(k)]
    stats = _standardize(cols)
    Xs = [[(row[j] - stats[j][0]) / stats[j][1] for j in range(k)] for row in X]
    w = [0.0] * k
    b = 0.0
    n = len(Xs)
    for _ in range(iters):
        gw = [0.0] * k
        gb = 0.0
        for xi, yi in zip(Xs, y):
            z = b + sum(w[j] * xi[j] for j in range(k))
            p = 1.0 / (1.0 + math.exp(-z))
            err = p - yi
            for j in range(k):
                gw[j] += err * xi[j]
            gb += err
        for j in range(k):
            w[j] = w[j] - lr * (gw[j] / n + l2 * w[j])
        b -= lr * gb / n
    return {"weights": w, "bias": b, "feature_stats": stats}


def predict_proba(model, X):
    w, b, stats = model["weights"], model["bias"], model["feature_stats"]
    out = []
    for row in X:
        xs = [(row[j] - stats[j][0]) / stats[j][1] for j in range(len(row))]
        z = b + sum(w[j] * xs[j] for j in range(len(w)))
        out.append(1.0 / (1.0 + math.exp(-z)))
    return out


# ---------- distributions / subgroups ----------

def _quantiles(vals):
    s = sorted(vals)
    if not s:
        return {}

    def q(p):
        idx = min(len(s) - 1, max(0, int(round(p * (len(s) - 1)))))
        return round(s[idx], 2)

    return {"n": len(s), "min": round(s[0], 2), "p25": q(0.25), "median": q(0.5),
            "p75": q(0.75), "max": round(s[-1], 2), "mean": round(mean(s), 2)}


def score_distribution(rows, score_key, by=None):
    """Distribution of `score_key`, overall and split by the categorical field `by` if given."""
    out = {"overall": _quantiles([r[score_key] for r in rows if r.get(score_key) is not None])}
    if by:
        groups = {}
        for r in rows:
            if r.get(score_key) is None:
                continue
            groups.setdefault(str(r.get(by)), []).append(r[score_key])
        out["by_" + by] = {g: _quantiles(v) for g, v in sorted(groups.items())}
    return out


def group_summary(rows, score_key, outcome_key, by):
    """AUC + event rate within each level of `by` (subgroup discrimination, VALIDATION_PLAN §2)."""
    groups = {}
    for r in rows:
        if r.get(score_key) is None or r.get(outcome_key) is None:
            continue
        groups.setdefault(str(r.get(by)), []).append((r[score_key], r[outcome_key]))
    out = {}
    for g, pairs in sorted(groups.items()):
        s = [p for p, _ in pairs]
        y = [int(v) for _, v in pairs]
        out[g] = {"n": len(pairs), "event_rate": round(mean(y), 4) if y else None,
                  "auc": round(auc(s, y), 4) if auc(s, y) is not None else None}
    return out
