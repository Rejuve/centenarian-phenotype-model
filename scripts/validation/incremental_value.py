"""Incremental-value / high-yield-input analysis.

ETHOS (not feature pruning): the model should give a *meaningful* read from a few accessible inputs
(the low-barrier teaser), and get *more confident* as a profile is filled in — it never discards
features. This quantifies how much out-of-sample survival discrimination a **sparse** profile already
carries, and the order in which inputs add the most value (so we can ask the highest-yield questions
first). The deployed model always uses **all** available features; this is about accessibility, not
minimization.

Method: greedy forward ordering by held-out mortality-AUC gain, on top of age + sex (always-in). The
curve shows diminishing returns; the full ("all features") model is reported for reference. Missing
per-subject features are neutral-imputed (0.5), matching how the scorer treats an absent input.
All-cause mortality is a survival proxy, single US cohort (see VALIDATION_PLAN; roadmap §"Predictive
Trajectory Modeling"). Aggregate results only.

Usage:
  python scripts/validation/incremental_value.py --cohort data/processed/nhanes_cohort_feat.csv \
      --out reports/incremental_value [--min-age 75]
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
import pandas as pd

import metrics


def _fit(X, y, iters=400, lr=0.5, l2=1e-4):
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    w = np.zeros(Z.shape[1])
    b = 0.0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(Z @ w + b)))
        g = p - y
        w -= lr * (Z.T @ g / len(y) + l2 * w)
        b -= lr * g.mean()
    return mu, sd, w, b


def _auc(mu, sd, w, b, X, y):
    p = 1 / (1 + np.exp(-(((X - mu) / sd) @ w + b)))
    return metrics.auc(list(p), [int(v) for v in y])  # mortality discrimination (higher = better)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--out", default="reports/incremental_value")
    ap.add_argument("--min-age", type=float, default=None)
    ap.add_argument("--max-features", type=int, default=12)
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()

    df = pd.read_csv(args.cohort)
    df = df[pd.to_numeric(df["deceased"], errors="coerce").isin([0, 1])].copy()
    if args.min_age is not None:
        df = df[pd.to_numeric(df["age"], errors="coerce") >= args.min_age]
    df = df[df["sex"].isin(["M", "F"])]
    fcols = sorted(c for c in df.columns if c.startswith("f_"))

    y = df["deceased"].astype(float).to_numpy()
    age = df["age"].astype(float).to_numpy()
    male = (df["sex"] == "M").astype(float).to_numpy()
    feats = {c: df[c].astype(float).fillna(0.5).to_numpy() for c in fcols}

    rng = np.random.default_rng(args.seed)
    idx = rng.permutation(len(y))
    tr, te = idx[:int(0.7 * len(y))], idx[int(0.7 * len(y)):]

    def design(cols):
        return np.column_stack([age, male] + [feats[c] for c in cols])

    mu, sd, w, b = _fit(design([])[tr], y[tr])
    base = _auc(mu, sd, w, b, design([])[te], y[te])
    traj = [{"step": 0, "added": "age+sex (base)", "test_auc": round(base, 4)}]

    selected, remaining, cur = [], list(fcols), base
    while remaining and len(selected) < args.max_features:
        best, best_auc = None, cur
        for c in remaining:
            X = design(selected + [c])
            mu, sd, w, b = _fit(X[tr], y[tr])
            a = _auc(mu, sd, w, b, X[te], y[te])
            if a is not None and a > best_auc:
                best, best_auc = c, a
        if best is None:
            break
        selected.append(best)
        remaining.remove(best)
        traj.append({"step": len(selected), "added": best[2:], "test_auc": round(best_auc, 4),
                     "gain": round(best_auc - cur, 4)})
        cur = best_auc

    mu, sd, w, b = _fit(design(fcols)[tr], y[tr])
    full = _auc(mu, sd, w, b, design(fcols)[te], y[te])
    out = {"n": int(len(y)), "deaths": int(y.sum()), "min_age": args.min_age,
           "base_age_sex_auc": round(base, 4), "full_all_features_auc": round(full, 4) if full else None,
           "high_yield_order": [t["added"] for t in traj[1:]], "value_curve": traj}
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "incremental_value.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    tag = f" (age {int(args.min_age)}+)" if args.min_age else ""
    lines = [f"# Incremental value of inputs — survival discrimination, out-of-sample{tag}", "",
             f"N={out['n']}, deaths={out['deaths']}. Age+sex alone AUC={out['base_age_sex_auc']}; "
             f"all {len(fcols)} features AUC={out['full_all_features_auc']}. "
             "Ethos: meaningful from few inputs, richer with more — all features retained.", "",
             "| inputs added | test AUC (mortality) | gain |", "|---|---:|---:|"]
    for t in traj:
        lines.append(f"| +{t['added']} | {t['test_auc']} | {t.get('gain', '')} |")
    body = "\n".join(lines) + "\n"
    with open(os.path.join(args.out, "incremental_value.md"), "w", encoding="utf-8") as f:
        f.write(body)
    print(body)


if __name__ == "__main__":
    main()
