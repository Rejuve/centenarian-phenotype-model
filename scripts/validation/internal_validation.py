"""Internal-validation rigor for the ELC score -> mortality model (TRIPOD-AI items).

Apparent performance is optimistic (evaluated on the same data it was fit on). This adds the two
pieces a prediction-model reviewer expects beyond a single AUC:

  1. Bootstrap OPTIMISM CORRECTION (Harrell/Efron .632-style enhanced bootstrap):
       optimism = mean over B bootstraps of [ AUC(model_b on boot_b) - AUC(model_b on original) ]
       corrected = apparent - optimism.  Also the optimism-corrected CALIBRATION SLOPE (a slope < 1
       signals overfitting / need for shrinkage).
  2. DECISION-CURVE ANALYSIS (net benefit vs treat-all / treat-none across risk thresholds): does using
       the model to flag elevated-mortality (low-ELC) individuals for intervention add clinical utility?

The fitted model is the deployed calibration model: P(death) ~ score + age + sex. Higher ELC score is
protective. All-cause mortality within follow-up is the external (non-circular) outcome.

Usage: python scripts/validation/internal_validation.py --cohort data/processed/nhanes_cohort_99_16_v2.csv
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
import pandas as pd
from scipy.stats import rankdata


def auc(scores, y):
    y = np.asarray(y)
    npos, nneg = int(y.sum()), int(len(y) - y.sum())
    if npos == 0 or nneg == 0:
        return float("nan")
    r = rankdata(np.asarray(scores, float))
    return (r[y == 1].sum() - npos * (npos + 1) / 2) / (npos * nneg)


def fit(X, y, iters=400, lr=0.3, l2=1e-4):
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    Xs = (X - mu) / sd
    w, b = np.zeros(Xs.shape[1]), 0.0
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-(Xs @ w + b)))
        e = p - y
        w -= lr * (Xs.T @ e / len(y) + l2 * w)
        b -= lr * e.mean()
    return w, b, mu, sd


def predict(model, X):
    w, b, mu, sd = model
    return 1.0 / (1.0 + np.exp(-(((X - mu) / sd) @ w + b)))


def cal_slope(p, y):
    """Calibration slope: logistic of y on the linear predictor (logit p). ~1 = well-calibrated."""
    lp = np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
    w, b, mu, sd = fit(lp.reshape(-1, 1), y, iters=400)
    return float(w[0] / sd[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", default="data/processed/nhanes_cohort_99_16_v2.csv")
    ap.add_argument("--score-col", default="score_full")
    ap.add_argument("--boots", type=int, default=200)
    ap.add_argument("--out", default="reports/internal_validation")
    args = ap.parse_args()

    df = pd.read_csv(args.cohort, low_memory=False)
    df["y"] = pd.to_numeric(df["deceased"], errors="coerce")
    df["s"] = pd.to_numeric(df[args.score_col], errors="coerce")
    df["age"] = pd.to_numeric(df["age"], errors="coerce")
    df = df[df["y"].isin([0, 1]) & df["s"].notna() & df["age"].notna() & df["sex"].isin(["M", "F"])]
    X = np.column_stack([df["s"].to_numpy(float), df["age"].to_numpy(float),
                         (df["sex"] == "M").astype(float).to_numpy()])
    y = df["y"].to_numpy(float)
    n = len(y)

    model = fit(X, y)
    p_app = predict(model, X)
    auc_app = auc(p_app, y)
    slope_app = cal_slope(p_app, y)

    rng = np.random.default_rng(7)
    opt_auc, opt_slope = [], []
    for _ in range(args.boots):
        idx = rng.integers(0, n, n)
        mb = fit(X[idx], y[idx])
        pb_boot = predict(mb, X[idx])
        pb_orig = predict(mb, X)
        opt_auc.append(auc(pb_boot, y[idx]) - auc(pb_orig, y))
        opt_slope.append(cal_slope(pb_boot, y[idx]) - cal_slope(pb_orig, y))
    auc_corr = auc_app - float(np.mean(opt_auc))
    slope_corr = slope_app - float(np.mean(opt_slope))

    # ---- decision-curve analysis ----
    event_rate = float(y.mean())
    dca = []
    for pt in np.arange(0.02, 0.51, 0.02):
        pred_pos = p_app >= pt
        tp = float(((pred_pos) & (y == 1)).sum()) / n
        fp = float(((pred_pos) & (y == 0)).sum()) / n
        nb_model = tp - fp * (pt / (1 - pt))
        nb_all = event_rate - (1 - event_rate) * (pt / (1 - pt))
        dca.append({"threshold": round(float(pt), 2), "nb_model": round(nb_model, 4),
                    "nb_treat_all": round(nb_all, 4), "nb_treat_none": 0.0,
                    "model_best": bool(nb_model >= max(nb_all, 0.0))})

    out = {"n": n, "events": int(y.sum()), "event_rate": round(event_rate, 4), "boots": args.boots,
           "discrimination": {"auc_apparent": round(auc_app, 4),
                              "optimism": round(float(np.mean(opt_auc)), 4),
                              "auc_optimism_corrected": round(auc_corr, 4)},
           "calibration_slope": {"apparent": round(slope_app, 4),
                                 "optimism_corrected": round(slope_corr, 4)},
           "decision_curve": dca}
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "internal_validation.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    print(f"# Internal validation — ELC score+age+sex -> P(death)  (n={n}, {int(y.sum())} deaths, "
          f"{args.boots} bootstraps)\n")
    d = out["discrimination"]
    print(f"Discrimination AUC: apparent {d['auc_apparent']} - optimism {d['optimism']} "
          f"= optimism-corrected {d['auc_optimism_corrected']}")
    c = out["calibration_slope"]
    print(f"Calibration slope: apparent {c['apparent']} -> optimism-corrected {c['optimism_corrected']} "
          f"(1.0 = no shrinkage needed)\n")
    print("Decision curve (net benefit; model_best = model >= treat-all and >= treat-none):")
    print(f"{'threshold':>9} {'nb_model':>9} {'nb_all':>8} {'best?':>6}")
    for r in dca:
        if round(r["threshold"] / 0.02) % 3 == 0:  # print every ~6%
            print(f"{r['threshold']:9} {r['nb_model']:9} {r['nb_treat_all']:8} "
                  f"{'yes' if r['model_best'] else 'no':>6}")
    span = [r["threshold"] for r in dca if r["model_best"]]
    if span:
        print(f"\nModel adds net benefit over treat-all/none across thresholds "
              f"{min(span):.2f}-{max(span):.2f}.")
    print("wrote", os.path.join(args.out, "internal_validation.json"))


if __name__ == "__main__":
    main()
