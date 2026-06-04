"""Cause-specific discrete-time survival (trajectory) model on NHANES.

Estimates the phenotype's association with **aging-related** survival, controlling for non-aging
mortality: deaths coded as unintentional injuries/accidents (UCOD_LEADING = 004) are treated as
censored rather than events, so the model targets aging-related death rather than being penalized for
accidents. A discrete-time (pooled-logistic) hazard model over yearly follow-up intervals handles
right-censoring and supports a per-person trajectory (predicted aging-related survival to a horizon).

Restricted to NHANES cycles with the full leading-cause recode and meaningful follow-up (1999-2014;
2015-2018 code only heart/cancer, so accidents cannot be separated and are excluded here). Cause of
death and follow-up months come from the Public-use Linked Mortality File; features come from the
matrix built by build_cohort_from_xpt.py. All-cause results are reported alongside for comparison.
Out-of-sample (subject-level 70/30 split); aggregate results only (NCHS-cited).

Usage:
  python scripts/validation/trajectory_model.py --cohort data/processed/nhanes_cohort_feat.csv \
      --out reports/trajectory_model
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os

import numpy as np
import pandas as pd

import metrics
from parse_nhanes_lmf import parse_file

ACCIDENT_UCOD = 4          # UCOD_LEADING leading-cause code for unintentional injuries (verified)
MAX_YEARS = 18             # cap follow-up horizon for the discrete-time grid


def ucod_by_seqn():
    out = {}
    for p in glob.glob(os.path.join("data", "raw", "datasets", "nhanes_cycles", "*",
                                    "NHANES_*MORT*.dat")):
        for r in parse_file(p):
            if r["seqn"]:
                out[int(float(r["seqn"]))] = r["ucod_leading"]
    return out


def _fit(X, y, iters=500, lr=0.5, l2=1e-4):
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    w, b = np.zeros(Z.shape[1]), 0.0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(Z @ w + b)))
        g = p - y
        w -= lr * (Z.T @ g / len(y) + l2 * w)
        b -= lr * g.mean()
    return mu, sd, w, b


def _expand(sub):
    """Person-period rows: one per subject-year up to event/censor; outcome=1 only at the event year."""
    rows, idx = [], []
    for i, r in enumerate(sub):
        k = max(1, min(MAX_YEARS, int(math.ceil(r["t_years"]))))
        for t in range(1, k + 1):
            rows.append((t, t * t, r["age"], r["male"], r["score"]))
            idx.append((i, 1 if (t == k and r["event"]) else 0))
    return np.array(rows, float), np.array([j for _, j in idx], float), [i for i, _ in idx]


def _risk_to_horizon(model, sub, H):
    """1 - prod_t(1-hazard_t) over t=1..H for each subject (discrete-time cumulative incidence)."""
    mu, sd, w, b = model
    out = np.zeros(len(sub))
    for i, r in enumerate(sub):
        surv = 1.0
        for t in range(1, H + 1):
            x = np.array([t, t * t, r["age"], r["male"], r["score"]])
            z = b + (((x - mu) / sd) @ w)
            surv *= 1 - 1 / (1 + math.exp(-z))
        out[i] = 1 - surv
    return out


def _td_auc(model, sub, H):
    """Time-dependent AUC at horizon H: event by H vs risk(H), among subjects observed through H."""
    elig = [r for r in sub if (r["t_years"] >= H) or (r["event"] and r["t_years"] <= H)]
    if len({r["event"] and r["t_years"] <= H for r in elig}) < 2:
        return None, len(elig)
    risk = _risk_to_horizon(model, elig, H)
    y = [1 if (r["event"] and r["t_years"] <= H) else 0 for r in elig]
    return metrics.auc(list(risk), y), len(elig)


def run(sub, label, seed=11):
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(sub))
    tr = [sub[i] for i in order[:int(0.7 * len(sub))]]
    te = [sub[i] for i in order[int(0.7 * len(sub)):]]
    X, y, _ = _expand(tr)
    model = _fit(X, y)
    score_coef = float(model[2][-1])  # standardized hazard coefficient on the phenotype score
    res = {"label": label, "n": len(sub), "events": sum(r["event"] for r in sub),
           "score_hazard_coef": round(score_coef, 4)}
    for H in (5, 10, 15):
        auc, n_elig = _td_auc(model, te, H)
        res[f"auc_{H}yr"] = round(auc, 4) if auc is not None else None
        res[f"n_eligible_{H}yr"] = n_elig
    # bootstrap CI on 10-yr test AUC
    elig = [r for r in te if (r["t_years"] >= 10) or (r["event"] and r["t_years"] <= 10)]
    risk = _risk_to_horizon(model, elig, 10)
    yv = np.array([1 if (r["event"] and r["t_years"] <= 10) else 0 for r in elig])
    boots = []
    for _ in range(300):
        b = rng.integers(0, len(elig), len(elig))
        a = metrics.auc(list(risk[b]), list(yv[b]))
        if a is not None:
            boots.append(a)
    if boots:
        res["auc_10yr_ci95"] = [round(np.percentile(boots, 2.5), 4), round(np.percentile(boots, 97.5), 4)]
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--out", default="reports/trajectory_model")
    args = ap.parse_args()

    ucod = ucod_by_seqn()
    df = pd.read_csv(args.cohort)
    df = df[pd.to_numeric(df["deceased"], errors="coerce").isin([0, 1])].copy()
    df["year"] = df["cycle"].str[:4].astype(int)
    df = df[df["year"] <= 2013]                      # full leading-cause recode + follow-up
    df = df[df["sex"].isin(["M", "F"])]
    df = df.dropna(subset=["age", "score_full", "permth_exm"])
    df["deceased"] = df["deceased"].astype(int)
    df["permth_exm"] = pd.to_numeric(df["permth_exm"], errors="coerce")
    df = df.dropna(subset=["permth_exm"])

    def ucod_int(seqn):
        v = ucod.get(int(seqn), "")
        try:
            return int(v)
        except ValueError:
            return None

    df["ucod"] = df["subject_id"].map(ucod_int)
    rows_all, rows_aging = [], []
    for _, r in df.iterrows():
        base = {"age": float(r["age"]), "male": 1.0 if r["sex"] == "M" else 0.0,
                "score": float(r["score_full"]), "t_years": max(0.1, float(r["permth_exm"]) / 12.0)}
        rows_all.append({**base, "event": int(r["deceased"] == 1)})
        # aging-related: accidents (UCOD 4) censored (event=0); other deaths are events
        aging = int(r["deceased"] == 1 and r["ucod"] != ACCIDENT_UCOD)
        rows_aging.append({**base, "event": aging})

    out = {
        "n": len(df), "cycles_year_max": 2013,
        "n_accident_deaths_censored": int(((df["deceased"] == 1) & (df["ucod"] == ACCIDENT_UCOD)).sum()),
        "all_cause": run(rows_all, "all_cause"),
        "aging_related": run(rows_aging, "aging_related_accidents_censored"),
        "note": "Discrete-time pooled-logistic hazard; phenotype score + age + sex + time. NHANES "
                "1999-2014 linked mortality; accidents (UCOD 004) censored for the aging-related "
                "endpoint. Out-of-sample 70/30. Aggregate results only.",
    }
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "trajectory_model.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
