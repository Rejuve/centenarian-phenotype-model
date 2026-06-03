"""Benchmark the phenotype panel against PhenoAge (Levine 2018), the clinical-biomarker biological-age
gold standard, on NHANES all-cause mortality — and test the incremental value of the cheap
behavioral/psychosocial block on top of PhenoAge.

PhenoAge is computed from its published 9-biomarker + age formula (Levine et al., 2018, Aging
10:573), trained/validated on NHANES mortality:
  albumin (g/L), creatinine (umol/L), glucose (mmol/L), ln C-reactive protein (mg/dL),
  lymphocyte %, mean cell volume (fL), red cell distribution width (%), alkaline phosphatase (U/L),
  white blood cell count (1000/uL), chronological age (years).

Three comparisons (mortality discrimination, out-of-sample where modelled):
  1. PhenoAge vs the phenotype score — AUC for all-cause mortality on the shared subjects.
  2. Age/sex-adjusted standardized association of PhenoAgeAccel vs the phenotype score.
  3. Incremental value: does the behavioral/psychosocial block add discrimination on top of a model
     that already contains PhenoAgeAccel + age + sex?

Inputs: NHANES BIOPRO (albumin/creatinine/alk phos), CBC (WBC/lymph%/MCV/RDW), GLU (glucose),
CRP/HSCRP, DEMO (age/sex), merged on SEQN with the feature matrix from build_cohort_from_xpt.py.
Restricted to cycles with the modern lab-file naming (2005-2016). All-cause mortality is a survival
proxy; single national cohort. Aggregate results only.

Usage:
  python scripts/validation/phenoage_benchmark.py --cohort data/processed/nhanes_cohort_feat.csv \
      --cycles 2005-2006,2007-2008,2009-2010 --out reports/phenoage_benchmark
"""
from __future__ import annotations

import argparse
import json
import math
import os

import numpy as np
import pandas as pd

import metrics
from build_cohort_from_xpt import YEAR, _xpt

GAMMA = 0.0076927

# behavioral/psychosocial features (exclude clinical labs that overlap PhenoAge) for the incremental test
BEHAVIORAL = ["f_q_depression", "f_q_self_rated_health", "f_q_functional_mobility",
              "f_q_pa_frequency", "f_q_diet", "f_q_sleep", "f_q_alcohol", "f_q_smoking",
              "f_q_family_partner"]


def phenoage(alb_gL, creat_umol, gluc_mmol, crp_mgdl, lymph_pct, mcv, rdw, alp, wbc, age):
    if None in (alb_gL, creat_umol, gluc_mmol, crp_mgdl, lymph_pct, mcv, rdw, alp, wbc, age):
        return None
    if crp_mgdl <= 0:
        crp_mgdl = 0.01
    xb = (-19.907 - 0.0336 * alb_gL + 0.0095 * creat_umol + 0.1953 * gluc_mmol
          + 0.0954 * math.log(crp_mgdl) - 0.0120 * lymph_pct + 0.0268 * mcv + 0.3306 * rdw
          + 0.00188 * alp + 0.0554 * wbc + 0.0804 * age)
    m = 1 - math.exp(-math.exp(xb) * (math.exp(120 * GAMMA) - 1) / GAMMA)
    m = min(max(m, 1e-7), 1 - 1e-7)
    return 141.50225 + math.log(-0.00553 * math.log(1 - m)) / 0.090165


def compute_phenoage_by_seqn(cycles):
    rows = {}
    for cyc in cycles:
        yr = YEAR[cyc]
        s = cyc.split("-")[0]
        suf = {"2005": "_D", "2007": "_E", "2009": "_F", "2011": "_G", "2013": "_H", "2015": "_I"}[s]
        d = os.path.join("data", "raw", "datasets", "nhanes_cycles", cyc)
        os.makedirs(d, exist_ok=True)
        demo, bio, cbc, glu = (_xpt(d, yr, f"DEMO{suf}"), _xpt(d, yr, f"BIOPRO{suf}"),
                               _xpt(d, yr, f"CBC{suf}"), _xpt(d, yr, f"GLU{suf}"))
        crp = _xpt(d, yr, f"CRP{suf}") if int(s) <= 2010 else _xpt(d, yr, f"HSCRP{suf}")
        crp_var, crp_to_mgdl = ("LBXCRP", 1.0) if int(s) <= 2010 else ("LBXHSCRP", 0.1)
        if demo is None:
            continue

        def g(df, seqn, col):
            if df is None or col not in df.columns or seqn not in df.index:
                return None
            v = df.at[seqn, col]
            try:
                v = float(v)
            except (TypeError, ValueError):
                return None
            return None if pd.isna(v) else v

        for seqn in demo.index:
            age = g(demo, seqn, "RIDAGEYR")
            crp_raw = g(crp, seqn, crp_var)
            pa = phenoage(
                alb_gL=(g(bio, seqn, "LBXSAL") or 0) * 10 if g(bio, seqn, "LBXSAL") else None,
                creat_umol=(g(bio, seqn, "LBXSCR") or 0) * 88.42 if g(bio, seqn, "LBXSCR") else None,
                gluc_mmol=(g(glu, seqn, "LBXGLU") or 0) * 0.0555 if g(glu, seqn, "LBXGLU") else None,
                crp_mgdl=crp_raw * crp_to_mgdl if crp_raw is not None else None,
                lymph_pct=g(cbc, seqn, "LBXLYPCT"), mcv=g(cbc, seqn, "LBXMCVSI"),
                rdw=g(cbc, seqn, "LBXRDW"), alp=g(bio, seqn, "LBXSAPSI"),
                wbc=g(cbc, seqn, "LBXWBCSI"), age=age)
            if pa is not None and age is not None:
                rows[int(seqn)] = {"phenoage": pa, "phenoage_accel": pa - age}
    return rows


def _fit(X, y, iters=600, lr=0.5, l2=1e-4):
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    w, b = np.zeros(Z.shape[1]), 0.0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(Z @ w + b)))
        gd = p - y
        w -= lr * (Z.T @ gd / len(y) + l2 * w)
        b -= lr * gd.mean()
    return mu, sd, w, b


def _auc_oos(df, cols, seed=13):
    d = df.dropna(subset=cols + ["deceased"]).copy()
    if d["deceased"].nunique() < 2 or len(d) < 200:
        return None, len(d), None
    X = d[cols].astype(float).to_numpy()
    y = d["deceased"].astype(float).to_numpy()
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(y))
    tr, te = idx[:int(0.7 * len(y))], idx[int(0.7 * len(y)):]
    mu, sd, w, b = _fit(X[tr], y[tr])
    p = 1 / (1 + np.exp(-(((X[te] - mu) / sd) @ w + b)))
    return metrics.auc(list(p), [int(v) for v in y[te]]), len(d), (w, list(cols))


def _std_beta(df, y, x, covars):
    """Standardized OLS coefficient on x in y ~ x + covars (age/sex-adjusted association)."""
    d = df.dropna(subset=[y, x] + covars)
    if len(d) < 200:
        return None, len(d)
    cols = [x] + covars
    X = d[cols].astype(float).to_numpy()
    yv = d[y].astype(float).to_numpy()
    Xs = (X - X.mean(0)) / (X.std(0) + 1e-9)
    ys = (yv - yv.mean()) / (yv.std() + 1e-9)
    A = np.column_stack([np.ones(len(Xs)), Xs])
    beta, *_ = np.linalg.lstsq(A, ys, rcond=None)
    return round(float(beta[1]), 4), len(d)


def concurrent_validity(df, fcols, behavioral):
    """Does the phenotype track PhenoAge itself? Lower PhenoAge accel = biologically younger;
    higher phenotype alignment is favourable, so favourable signal should give NEGATIVE coefficients."""
    d = df.dropna(subset=["phenoage_accel", "score_full"])
    pearson = round(float(d["score_full"].corr(d["phenoage_accel"])), 4) if len(d) > 200 else None
    spearman = (round(float(d["score_full"].corr(d["phenoage_accel"], method="spearman")), 4)
                if len(d) > 200 else None)
    adj_beta, n = _std_beta(df, "phenoage_accel", "score_full", ["age", "male"])
    per_feat = {}
    for c in fcols:
        b, nn = _std_beta(df, "phenoage_accel", c, ["age", "male"])
        if b is not None and nn >= 300:
            per_feat[c[2:]] = b
    return {
        "score_vs_phenoage_accel_pearson": pearson,
        "score_vs_phenoage_accel_spearman": spearman,
        "score_adjusted_std_beta": adj_beta,  # negative = higher score -> younger PhenoAge
        "per_feature_std_beta_vs_phenoage_accel": dict(sorted(per_feat.items(), key=lambda kv: kv[1])),
        "behavioral_only": {k[2:]: per_feat.get(k[2:]) for k in behavioral if k[2:] in per_feat},
        "interpretation": "negative = favourable phenotype associates with decelerated (younger) PhenoAge",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--cycles", default="2005-2006,2007-2008,2009-2010")
    ap.add_argument("--out", default="reports/phenoage_benchmark")
    args = ap.parse_args()
    cycles = [c.strip() for c in args.cycles.split(",")]

    pa = compute_phenoage_by_seqn(cycles)
    df = pd.read_csv(args.cohort)
    df = df[pd.to_numeric(df["deceased"], errors="coerce").isin([0, 1])].copy()
    df["deceased"] = df["deceased"].astype(int)
    df["phenoage"] = df["subject_id"].map(lambda s: pa.get(int(s), {}).get("phenoage"))
    df["phenoage_accel"] = df["subject_id"].map(lambda s: pa.get(int(s), {}).get("phenoage_accel"))
    df["male"] = (df["sex"] == "M").astype(float)
    df = df.dropna(subset=["phenoage", "age"])
    df["risk_score"] = -df["score_full"].astype(float)  # higher = worse, to align with mortality

    have_beh = [c for c in BEHAVIORAL if c in df.columns]

    # 1. raw mortality discrimination
    auc_pa = metrics.auc(list(df["phenoage"]), list(df["deceased"]))
    sub = df.dropna(subset=["risk_score"])
    auc_score = metrics.auc(list(sub["risk_score"]), list(sub["deceased"]))

    # 2 & 3. out-of-sample models
    base = ["age", "male"]
    auc_base, n_base, _ = _auc_oos(df, base)
    auc_pa_adj, _, _ = _auc_oos(df, base + ["phenoage_accel"])
    auc_score_adj, _, _ = _auc_oos(df, base + ["risk_score"])
    auc_pa_beh, n_inc, _ = _auc_oos(df.assign(**{c: df[c].fillna(0.5) for c in have_beh}),
                                    base + ["phenoage_accel"] + have_beh)

    out = {
        "n_with_phenoage": int(df["phenoage"].notna().sum()),
        "deaths": int(df["deceased"].sum()),
        "cycles": cycles,
        "raw_mortality_auc": {"phenoage": round(auc_pa, 4) if auc_pa else None,
                              "phenotype_score": round(auc_score, 4) if auc_score else None},
        "oos_auc": {"age_sex": round(auc_base, 4) if auc_base else None,
                    "age_sex_phenoageAccel": round(auc_pa_adj, 4) if auc_pa_adj else None,
                    "age_sex_phenotypeScore": round(auc_score_adj, 4) if auc_score_adj else None,
                    "age_sex_phenoageAccel_plus_behavioral": round(auc_pa_beh, 4) if auc_pa_beh else None},
        "incremental_behavioral_over_phenoage": (round(auc_pa_beh - auc_pa_adj, 4)
                                                 if auc_pa_beh and auc_pa_adj else None),
        "behavioral_features_used": have_beh,
        "concurrent_validity_vs_phenoage": concurrent_validity(
            df, [c for c in df.columns if c.startswith("f_")], BEHAVIORAL),
        "note": "All-cause mortality (survival proxy), single US cohort. PhenoAge per Levine 2018.",
    }
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "phenoage_benchmark.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
