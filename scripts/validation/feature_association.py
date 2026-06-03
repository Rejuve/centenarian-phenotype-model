"""Per-feature association with all-cause mortality (the 'what is most associated with longer life'
table) — with a reverse-causation (landmark/lag) sensitivity.

For each scored feature's alignment (the f_<feature> columns emitted by build_cohort_from_xpt.py):
  * AUC(alignment -> survival)            — higher alignment = more centenarian-like; >0.5 = protective
  * age/sex-adjusted logistic coefficient — standardized weight on the feature in a model of P(death);
                                            NEGATIVE = protective independent of age/sex
  * the same coefficient on a LANDMARK sample that EXCLUDES early deaths (< --lag-months), so the
    association is not just baseline-sick-people-die-soon (a partial guard against reverse causation)

This does NOT establish causation (cross-sectional exposure); persistence after age/sex adjustment +
landmarking is supportive, not proof. See README/VALIDATION_PLAN for the causal-inference plan (MR etc.).

Usage:
  python scripts/validation/feature_association.py --cohort data/processed/nhanes_cohort_99_16_v2.csv \
      --out reports/feature_association
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
import pandas as pd

import metrics


def _logit_coef(X, y, iters=300, lr=0.5, l2=1e-4):
    """Vectorized standardized logistic regression (numpy); returns standardized weights."""
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd == 0] = 1.0
    Xs = (X - mu) / sd
    n, k = Xs.shape
    w = np.zeros(k)
    b = 0.0
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-(Xs @ w + b)))
        err = p - y
        w -= lr * (Xs.T @ err / n + l2 * w)
        b -= lr * err.mean()
    return w


def _fit_coef(df, fcol, iters):
    """Standardized age/sex-adjusted logistic coefficient on the feature (neg = protective)."""
    d = df[[fcol, "age", "sex", "deceased"]].dropna()
    d = d[d["sex"].isin(["M", "F"])]
    if d["deceased"].nunique() < 2 or len(d) < 50:
        return None, len(d)
    X = np.column_stack([d[fcol].astype(float).to_numpy(),
                         d["age"].astype(float).to_numpy(),
                         (d["sex"] == "M").astype(float).to_numpy()])
    y = d["deceased"].astype(float).to_numpy()
    w = _logit_coef(X, y, iters=iters)
    return round(float(w[0]), 4), len(d)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--out", default="reports/feature_association")
    ap.add_argument("--lag-months", type=float, default=24)
    ap.add_argument("--min-n", type=int, default=300)
    ap.add_argument("--iters", type=int, default=600)
    ap.add_argument("--min-age", type=float, default=None, help="restrict to age >= this (e.g. 75)")
    ap.add_argument("--max-age", type=float, default=None)
    args = ap.parse_args()

    df = pd.read_csv(args.cohort)
    if args.min_age is not None:
        df = df[pd.to_numeric(df["age"], errors="coerce") >= args.min_age]
    if args.max_age is not None:
        df = df[pd.to_numeric(df["age"], errors="coerce") <= args.max_age]
    df = df[pd.to_numeric(df["deceased"], errors="coerce").isin([0, 1])].copy()
    df["deceased"] = df["deceased"].astype(int)
    df["permth_exm"] = pd.to_numeric(df.get("permth_exm"), errors="coerce")
    fcols = sorted(c for c in df.columns if c.startswith("f_"))

    # landmark sample: drop deaths occurring before the lag (keep survivors + later deaths)
    lm = df[~((df["deceased"] == 1) & (df["permth_exm"] < args.lag_months))].copy()

    rows = []
    for c in fcols:
        sub = df[[c, "deceased"]].dropna()
        if len(sub) < args.min_n or sub["deceased"].nunique() < 2:
            continue
        aligns = [float(v) for v in sub[c]]
        survived = [1 - int(v) for v in sub["deceased"]]
        auc = metrics.auc(aligns, survived)
        coef, n = _fit_coef(df, c, args.iters)
        coef_lm, n_lm = _fit_coef(lm, c, args.iters)
        rows.append({
            "feature": c[2:], "n": n, "deaths": int(sub["deceased"].sum()),
            "auc_align_to_survival": round(auc, 4) if auc is not None else None,
            "adj_coef": coef, "adj_coef_landmark": coef_lm, "n_landmark": n_lm,
        })

    # rank by adjusted coefficient (most negative = most protective independent of age/sex)
    rows.sort(key=lambda r: (r["adj_coef"] if r["adj_coef"] is not None else 0))
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "feature_association.json"), "w", encoding="utf-8") as f:
        json.dump({"lag_months": args.lag_months, "features": rows}, f, indent=2)

    md = ["# Per-feature mortality association (NHANES, all-cause)", "",
          f"Ranked by age/sex-adjusted coefficient (negative = protective). Landmark excludes deaths "
          f"< {args.lag_months:.0f} months (reverse-causation guard). Survival proxy, single cohort.",
          "", "| feature | n | deaths | AUC->survival | adj.coef | adj.coef (landmark) |",
          "|---|---:|---:|---:|---:|---:|"]
    for r in rows:
        md.append(f"| {r['feature']} | {r['n']} | {r['deaths']} | {r['auc_align_to_survival']} | "
                  f"{r['adj_coef']} | {r['adj_coef_landmark']} |")
    with open(os.path.join(args.out, "feature_association.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
