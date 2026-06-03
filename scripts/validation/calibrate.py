"""Part A — fit a held-out, versioned calibration of phenotype score -> survival, and bundle it.

Turns the *untrained* phenotype score into a calibrated probability via a small logistic model on a
**fixed 10-year mortality horizon** (so the differing follow-up lengths across NHANES cycles do not
confound the estimate):

    outcome y = 1 if deceased within 120 months of exam
              = 0 if known alive at >= 120 months
              (censored-alive-before-120mo are excluded — 10-yr status unknown)

    P(y=1) = sigmoid(b0 + w_score·z(score) + w_age·z(age) + w_sex·sex_male)

Honesty guardrail: metrics are reported on a held-out test split (the score was NOT trained on
mortality, and the *calibration* is evaluated out-of-sample). The bundled coefficients are then refit
on the full cohort for deployment, with the held-out metrics recorded in the artifact.

Output: centenarian_phenotype/models/survival_calibration.yaml (bundled; aggregate coefficients only,
no individual data). All-cause US mortality — NOT centenarian attainment.

Usage:
  python scripts/validation/calibrate.py --cohort data/processed/nhanes_cohort_99_16_v2.csv \
      --score-col score_full
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import random

import yaml

import metrics

HORIZON_MONTHS = 120
OUT = os.path.join("centenarian_phenotype", "models", "survival_calibration.yaml")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load(cohort, score_col):
    rows = []
    with open(cohort, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            s = _num(r.get(score_col))
            age = _num(r.get("age"))
            permth = _num(r.get("permth_exm"))
            dec = r.get("deceased")
            sex = r.get("sex")
            if s is None or age is None or permth is None or dec not in ("0", "1") or sex not in ("M", "F"):
                continue
            dec = int(dec)
            if dec == 1 and permth <= HORIZON_MONTHS:
                y = 1
            elif permth >= HORIZON_MONTHS:
                y = 0
            else:
                continue  # censored alive before horizon -> 10-yr status unknown
            rows.append({"x": [s, age, 1.0 if sex == "M" else 0.0], "y": y})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--score-col", default="score_full")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--iters", type=int, default=3000)
    args = ap.parse_args()

    rows = load(args.cohort, args.score_col)
    rng = random.Random(args.seed)
    rng.shuffle(rows)
    cut = int(0.7 * len(rows))
    train, test = rows[:cut], rows[cut:]

    Xtr = [r["x"] for r in train]
    ytr = [r["y"] for r in train]
    model = metrics.logistic_fit(Xtr, ytr, iters=args.iters)
    Xte = [r["x"] for r in test]
    yte = [r["y"] for r in test]
    p_te = metrics.predict_proba(model, Xte)
    heldout = {
        "n_test": len(test),
        "auc": round(metrics.auc(p_te, yte), 4),
        "ece": metrics.ece(p_te, yte),
        "brier": metrics.brier(p_te, yte),
    }

    # refit on full cohort for the deployed coefficients
    full = metrics.logistic_fit([r["x"] for r in rows], [r["y"] for r in rows], iters=args.iters)

    artifact = {
        "model": "phenotype_score_to_10yr_mortality_logistic",
        "version": "1.0",
        "date": dt.date.today().isoformat(),
        "horizon_months": HORIZON_MONTHS,
        "features": ["score", "age", "sex_male"],
        "standardized_weights": [round(w, 6) for w in full["weights"]],
        "bias": round(full["bias"], 6),
        "feature_stats": [[round(m, 6), round(sd, 6)] for m, sd in full["feature_stats"]],
        "n_total": len(rows),
        "event_rate_10yr": round(sum(r["y"] for r in rows) / len(rows), 4),
        "heldout": heldout,
        "cohort": "NHANES 1999-2016 Public-use Linked Mortality File (follow-up to 2019-12-31)",
        "citation": "NCHS Continuous NHANES Public-use Linked Mortality Files, 2019 "
                    "(doi:10.15620/cdc:117142).",
        "interpretation": "negative 'score' weight => higher phenotype score lowers modelled 10-year "
                          "all-cause mortality.",
        "caveats": "ALL-CAUSE US mortality at a 10-year horizon; NOT centenarian attainment. Single "
                   "national cohort; not externally replicated. score column = " + args.score_col,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        yaml.safe_dump(artifact, f, sort_keys=False, allow_unicode=True)
    print(f"wrote {OUT}")
    print(f"held-out (n={heldout['n_test']}): AUC={heldout['auc']} ECE={heldout['ece']} "
          f"Brier={heldout['brier']}; 10-yr event rate={artifact['event_rate_10yr']}; "
          f"score weight={artifact['standardized_weights'][0]}")


if __name__ == "__main__":
    main()
