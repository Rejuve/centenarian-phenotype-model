"""Exposome <-> molecular coupling: how much do MODIFIABLE lifestyle drivers move the molecular markers?

This is the analysis that distinguishes the Exceptional Longevity Concordance (ELC) construct from a
static biological-age/biomarker composite. A clock or PhenoAge reports a molecular STATE; ELC asks how
much of that molecular state is *movable* by the modifiable exposome — i.e. how coupled the lifestyle
and molecular domains are, and through which exposures. That coupling is the actionable core (you can
only move the modifiable part) and underpins the genetics-vs-lifestyle decomposition.

For each molecular marker's alignment, we fit:
  base  = age + sex
  full  = age + sex + modifiable exposome (smoking, alcohol, diet, sleep, physical activity, depression)
and report dR2 = R2_full - R2_base = the share of that marker's variance attributable to the modifiable
exposome BEYOND age/sex, plus the standardized exposome coefficients (which lifestyle moves which marker).

Caveat: features are model ALIGNMENTS (monotone transforms of raw values), so dR2 is variance-in-alignment
explained, a within-construct coupling measure, not raw clinical variance. Cross-sectional NHANES; the
genomic domain is not in NHANES (no genotype), so this pass quantifies the LIFESTYLE<->molecular coupling.

Usage: python scripts/validation/exposome_molecular_coupling.py --cohort data/processed/nhanes_cohort_endocrine.csv
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
import pandas as pd

EXPOSOME = ["f_q_smoking", "f_q_alcohol", "f_q_diet", "f_q_sleep", "f_q_pa_frequency", "f_q_depression"]
MOLECULAR = ["f_c_reactive_protein", "f_glucose", "f_hba1c", "f_triglycerides", "f_hdl_cholesterol",
             "f_white_blood_cell", "f_egfr", "f_cholesterol", "f_thyroid_tsh", "f_testosterone"]


def _r2(X, y):
    """OLS R^2 with an intercept (X already standardized columns)."""
    Xi = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(Xi, y, rcond=None)
    pred = Xi @ beta
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return (1 - ss_res / ss_tot) if ss_tot else 0.0, beta[1:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", default="data/processed/nhanes_cohort_endocrine.csv")
    ap.add_argument("--out", default="reports/exposome_molecular_coupling")
    args = ap.parse_args()
    df = pd.read_csv(args.cohort, low_memory=False)
    df["sex_m"] = (df["sex"] == "M").astype(float)
    df["age"] = pd.to_numeric(df["age"], errors="coerce")
    expo = [c for c in EXPOSOME if c in df.columns]

    rows = []
    for m in MOLECULAR:
        if m not in df.columns:
            continue
        cols = [m, "age", "sex_m"] + expo
        d = df[cols].dropna()
        if len(d) < 300:
            continue
        y = d[m].to_numpy(float)

        def std(frame, names):
            A = frame[names].to_numpy(float)
            mu, sd = A.mean(0), A.std(0)
            sd[sd == 0] = 1.0
            return (A - mu) / sd

        r2_base, _ = _r2(std(d, ["age", "sex_m"]), y)
        r2_full, beta = _r2(std(d, ["age", "sex_m"] + expo), y)
        coefs = dict(zip(["age", "sex_m"] + expo, [round(float(b), 4) for b in beta]))
        expo_coefs = {k.replace("f_q_", ""): coefs[k] for k in expo}
        top = sorted(expo_coefs.items(), key=lambda kv: -abs(kv[1]))[:3]
        rows.append({"marker": m.replace("f_", ""), "n": int(len(d)),
                     "r2_age_sex": round(r2_base, 4), "r2_plus_exposome": round(r2_full, 4),
                     "exposome_dR2": round(r2_full - r2_base, 4),
                     "top_exposures": [f"{k} ({v:+.2f})" for k, v in top]})

    rows.sort(key=lambda r: -r["exposome_dR2"])
    mean_dr2 = round(float(np.mean([r["exposome_dR2"] for r in rows])), 4) if rows else 0.0
    os.makedirs(args.out, exist_ok=True)
    payload = {"exposome_features": [e.replace("f_q_", "") for e in expo],
               "n_markers": len(rows), "mean_exposome_dR2": mean_dr2, "markers": rows}
    with open(os.path.join(args.out, "coupling.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print("# Exposome -> molecular coupling (NHANES 2007-2014)\n")
    print("dR2 = variance in each molecular marker's alignment explained by modifiable lifestyle, "
          "beyond age/sex.\n")
    print(f"{'molecular marker':22} {'n':>6} {'R2 age+sex':>11} {'+exposome':>10} {'dR2':>7}  top movers")
    for r in rows:
        print(f"{r['marker']:22} {r['n']:6} {r['r2_age_sex']:11} {r['r2_plus_exposome']:10} "
              f"{r['exposome_dR2']:7}  {', '.join(r['top_exposures'])}")
    print(f"\nMean modifiable-exposome-attributable variance across {len(rows)} molecular markers: "
          f"{mean_dr2*100:.1f}%")
    print("wrote", os.path.join(args.out, "coupling.json"))


if __name__ == "__main__":
    main()
