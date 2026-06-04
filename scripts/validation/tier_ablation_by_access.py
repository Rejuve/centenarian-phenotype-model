"""Tiered mortality-discrimination ablation under the `access`-based tier definition.

Tier 2 = self-report quiz + `access: anthropometric` measured features (grip, BMI, ...).
Tier 3 = Tier 2 + `access: lab` biomarkers (blood draw + assay). (genomic/epigenetic are not in the
cross-sectional NHANES cohort.)

Each tier's score for a subject is the evidence-weighted mean of the available per-feature alignments
(`f_<feature>` columns from build_cohort_from_xpt.py) whose `access` class belongs to that tier, using
the model feature weights. We then report AUC(score -> survival) and the age/sex-adjusted standardized
logistic coefficient (negative = higher score lowers modelled mortality), with a 24-month landmark.

Usage:
  python scripts/validation/tier_ablation_by_access.py --cohort data/processed/nhanes_cohort_feat_v2.csv
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
import pandas as pd

from centenarian_phenotype import load_model

import metrics


def feature_weights():
    """Return {f_column: (access_class, weight)} from the tier-2 + tier-3 models."""
    fw = {}
    for q in load_model(2)["questions"]:
        fw[f"f_{q['id']}"] = ("self_report", float(q.get("weight", 1.0)))
    for b in load_model(3).get("clinical_biomarkers", []):
        fw[f"f_{b['feature']}"] = (b.get("access", "lab"), float(b.get("weight", 0.66)))
    return fw


def tier_score(df, cols_weights):
    """Evidence-weighted mean alignment over available features (per row)."""
    cols = [c for c, _ in cols_weights if c in df.columns]
    w = np.array([wt for c, wt in cols_weights if c in df.columns], dtype=float)
    A = df[cols].to_numpy(dtype=float)              # rows x feats (NaN where missing)
    mask = ~np.isnan(A)
    wsum = (mask * w).sum(axis=1)
    num = np.nansum(np.where(mask, A, 0.0) * w, axis=1)
    score = np.where(wsum > 0, num / wsum, np.nan)
    return score, wsum


def _logit_coef(X, y, iters=600, lr=0.5, l2=1e-4):
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    w, b = np.zeros(Z.shape[1]), 0.0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(Z @ w + b)))
        g = p - y
        w -= lr * (Z.T @ g / len(y) + l2 * w)
        b -= lr * g.mean()
    return w


def evaluate(df, score_col):
    d = df[[score_col, "age", "sex", "deceased", "permth_exm"]].dropna(subset=[score_col, "age", "deceased"])
    d = d[d["sex"].isin(["M", "F"]) & d["deceased"].isin([0, 1])]
    y = d["deceased"].astype(float).to_numpy()
    surv = [1 - int(v) for v in d["deceased"]]
    auc = metrics.auc(list(d[score_col].astype(float)), surv)
    X = np.column_stack([d[score_col].astype(float), d["age"].astype(float), (d["sex"] == "M").astype(float)])
    coef = float(_logit_coef(X, y)[0])
    lm = d[~((d["deceased"] == 1) & (pd.to_numeric(d["permth_exm"], errors="coerce") < 24))]
    Xl = np.column_stack([lm[score_col].astype(float), lm["age"].astype(float), (lm["sex"] == "M").astype(float)])
    coef_lm = float(_logit_coef(Xl, lm["deceased"].astype(float).to_numpy())[0])
    return {"n": int(len(d)), "deaths": int(y.sum()), "auc_score_to_survival": round(auc, 4),
            "adj_coef": round(coef, 4), "adj_coef_landmark": round(coef_lm, 4)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", default="data/processed/nhanes_cohort_feat_v2.csv")
    ap.add_argument("--out", default="reports/tier_ablation_by_access")
    args = ap.parse_args()

    df = pd.read_csv(args.cohort, low_memory=False)
    df["deceased"] = pd.to_numeric(df["deceased"], errors="coerce")
    fw = feature_weights()
    self_report = [(c, w) for c, (a, w) in fw.items() if a == "self_report"]
    anthro = [(c, w) for c, (a, w) in fw.items() if a == "anthropometric"]
    lab = [(c, w) for c, (a, w) in fw.items() if a == "lab"]

    df["score_tier2"], _ = tier_score(df, self_report + anthro)         # self-report + anthropometric
    df["score_tier3"], _ = tier_score(df, self_report + anthro + lab)   # + lab biomarkers
    df["score_selfreport_only"], _ = tier_score(df, self_report)        # quiz only (reference)
    df["score_lab_only"], _ = tier_score(df, lab)                       # lab only (reference)

    out = {
        "tier2_self_report_plus_anthropometric": evaluate(df, "score_tier2"),
        "tier3_plus_lab_biomarkers": evaluate(df, "score_tier3"),
        "reference_self_report_only": evaluate(df, "score_selfreport_only"),
        "reference_lab_only": evaluate(df, "score_lab_only"),
        "anthropometric_features": [c for c, _ in anthro],
        "lab_features": [c for c, _ in lab],
    }
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "tier_ablation_by_access.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    for k, v in out.items():
        if isinstance(v, dict):
            print(f"{k}: AUC {v['auc_score_to_survival']}  adj.coef {v['adj_coef']} "
                  f"(landmark {v['adj_coef_landmark']})  n={v['n']} deaths={v['deaths']}")
    print("anthropometric:", out["anthropometric_features"])


if __name__ == "__main__":
    main()
