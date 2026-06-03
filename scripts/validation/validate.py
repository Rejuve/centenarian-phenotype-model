"""Validation / calibration harness CLI.

Runs the metric engine over a "scored cohort" and writes a JSON + Markdown report covering the
VALIDATION_PLAN.md §2 metrics: score distributions, discrimination (AUC), a fitted calibration model
(score [+age/sex] -> P(outcome)) with reliability/ECE/Brier, and subgroup performance.

Two modes:

  # 1) Self-test on a synthetic cohort (runs now, no data needed) — proves the harness end-to-end:
  python scripts/validation/validate.py --synthetic 4000 --out reports/validation_synthetic

  # 2) Real cohort built by build_nhanes_cohort.py (once the NHANES Linked Mortality File is fetched):
  python scripts/validation/validate.py --cohort data/processed/nhanes_scored_cohort.csv \
      --score-col score_pct --outcome-col deceased --age-col age --sex-col sex \
      --out reports/validation_nhanes

The phenotype score is *protective* (higher = more centenarian-like), so discrimination is reported
as "score predicts survival." Calibration is fitted because the raw similarity score is NOT itself a
probability — fitting score->P(outcome) is exactly the phenotype->survival calibration the model needs
(see MODEL_CARD.md §4, §10).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random

import metrics


def synthetic_cohort(n, seed=7):
    """Cohort where higher phenotype health lowers mortality over follow-up (for harness self-test)."""
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        age = rng.uniform(50, 85)
        sex = rng.choice(["M", "F"])
        health = rng.betavariate(2, 2)               # latent phenotype health 0..1
        score = max(0.0, min(100.0, 100 * health + rng.gauss(0, 6)))
        # mortality risk rises with age, falls with health; women lower.
        z = -2.0 + 0.06 * (age - 65) - 2.4 * (health - 0.5) + (0.3 if sex == "M" else 0.0)
        p_death = 1.0 / (1.0 + math.exp(-z))
        deceased = 1 if rng.random() < p_death else 0
        rows.append({"subject_id": i, "age": round(age, 1), "sex": sex,
                     "score_pct": round(score, 1), "deceased": deceased,
                     "age_band": "50-64" if age < 65 else ("65-74" if age < 75 else "75-85")})
    return rows


def load_cohort(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def run(rows, score_col, outcome_col, age_col=None, sex_col=None, cal_iters=4000):
    # coerce
    clean = []
    for r in rows:
        s = _num(r.get(score_col))
        y = _num(r.get(outcome_col))
        if s is None or y is None:
            continue
        rr = {"score": s, "outcome": int(y)}
        rr["age"] = _num(r.get(age_col)) if age_col else None
        rr["sex"] = r.get(sex_col) if sex_col else None
        rr["age_band"] = r.get("age_band")
        clean.append(rr)

    scores = [r["score"] for r in clean]
    deceased = [r["outcome"] for r in clean]
    survived = [1 - y for y in deceased]

    report = {
        "n": len(clean),
        "event_rate_deceased": round(sum(deceased) / len(deceased), 4) if clean else None,
        "discrimination": {
            "auc_score_predicts_survival": _r(metrics.auc(scores, survived)),
            "note": "AUC>0.5 means a higher phenotype score is associated with lower mortality.",
        },
        "score_distribution_by_outcome": metrics.score_distribution(
            [{"score": r["score"], "deceased": "deceased" if r["outcome"] else "survived"} for r in clean],
            "score", by="deceased"),
    }

    # --- fitted calibration model: score [+ age, sex] -> P(deceased) ---
    feats, names = [], ["score"]
    use_age = age_col and all(r["age"] is not None for r in clean)
    use_sex = sex_col and all(r["sex"] in ("M", "F") for r in clean)
    if use_age:
        names.append("age")
    if use_sex:
        names.append("sex_male")
    for r in clean:
        row = [r["score"]]
        if use_age:
            row.append(r["age"])
        if use_sex:
            row.append(1.0 if r["sex"] == "M" else 0.0)
        feats.append(row)
    model = metrics.logistic_fit(feats, deceased, iters=cal_iters)
    probs = metrics.predict_proba(model, feats)
    report["calibration_model"] = {
        "features": names,
        "standardized_weights": [round(w, 4) for w in model["weights"]],
        "bias": round(model["bias"], 4),
        "interpretation": "negative weight on 'score' => higher phenotype score lowers modelled "
                          "mortality risk (the phenotype->survival signal).",
    }
    report["calibration"] = {
        "auc_calibrated_predicts_deceased": _r(metrics.auc(probs, deceased)),
        "ece": metrics.ece(probs, deceased),
        "brier": metrics.brier(probs, deceased),
        "reliability_table": metrics.reliability_table(probs, deceased),
    }

    # --- subgroup discrimination ---
    sub = {}
    if use_sex:
        sub["sex"] = metrics.group_summary(
            [{"s": r["score"], "y": r["outcome"], "g": r["sex"]} for r in clean], "s", "y", "g")
    if any(r.get("age_band") for r in clean):
        sub["age_band"] = metrics.group_summary(
            [{"s": r["score"], "y": r["outcome"], "g": r.get("age_band")} for r in clean], "s", "y", "g")
    report["subgroup_performance"] = sub
    report["disclaimer"] = ("All-cause mortality within follow-up is a survival proxy, not "
                            "centenarian attainment. Calibrates the phenotype->survival mapping; "
                            "does not by itself validate reaching 100. See VALIDATION_PLAN.md.")
    return report


def ablation(rows, cols, outcome_col, age_col=None, sex_col=None, cal_iters=2500):
    """Per-feature-class contribution: AUC(col -> survival) + age/sex-adjusted weight on each col."""
    out = {}
    for col in cols:
        clean = []
        for r in rows:
            s, y = _num(r.get(col)), _num(r.get(outcome_col))
            if s is None or y is None:
                continue
            age = _num(r.get(age_col)) if age_col else None
            sex = r.get(sex_col) if sex_col else None
            clean.append((s, int(y), age, sex))
        if len(clean) < 50:
            out[col] = {"n": len(clean), "note": "too few to assess"}
            continue
        s = [c[0] for c in clean]
        y = [c[1] for c in clean]
        entry = {"n": len(clean), "deaths": sum(y),
                 "auc_score_predicts_survival": _r(metrics.auc(s, [1 - v for v in y]))}
        use_age = age_col and all(c[2] is not None for c in clean)
        use_sex = sex_col and all(c[3] in ("M", "F") for c in clean)
        X = []
        for sc_, _, age, sex in clean:
            row = [sc_]
            if use_age:
                row.append(age)
            if use_sex:
                row.append(1.0 if sex == "M" else 0.0)
            X.append(row)
        model = metrics.logistic_fit(X, y, iters=cal_iters)
        entry["adjusted_score_weight"] = round(model["weights"][0], 4)
        entry["adjusted_features"] = ["score"] + (["age"] if use_age else []) + \
                                     (["sex_male"] if use_sex else [])
        out[col] = entry
    return out


def _r(x):
    return round(x, 4) if x is not None else None


def write_report(report, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    lines = ["# Validation report", "", f"- N = {report['n']}",
             f"- event rate (deceased) = {report['event_rate_deceased']}",
             f"- **AUC (score predicts survival)** = "
             f"{report['discrimination']['auc_score_predicts_survival']}",
             f"- calibrated ECE = {report['calibration']['ece']} · Brier = "
             f"{report['calibration']['brier']}", "",
             "## Calibration model (score [+age/sex] -> P(deceased))",
             f"- features: {report['calibration_model']['features']}",
             f"- standardized weights: {report['calibration_model']['standardized_weights']}",
             f"- {report['calibration_model']['interpretation']}", "",
             "## Reliability", "", "| bin | n | predicted | observed |", "|---|---:|---:|---:|"]
    for row in report["calibration"]["reliability_table"]:
        lines.append(f"| {row['bin']} | {row['n']} | {row['mean_predicted']} | {row['observed_freq']} |")
    lines += ["", "## Subgroup AUC (score predicts deceased)", ""]
    for dim, gs in report.get("subgroup_performance", {}).items():
        lines.append(f"**{dim}**")
        for g, v in gs.items():
            lines.append(f"- {g}: n={v['n']} event_rate={v['event_rate']} auc={v['auc']}")
    lines += ["", f"> {report['disclaimer']}"]
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Centenarian Phenotype Model validation harness")
    ap.add_argument("--synthetic", type=int, help="generate and validate a synthetic cohort of size N")
    ap.add_argument("--cohort", help="path to a scored-cohort CSV")
    ap.add_argument("--score-col", default="score_pct")
    ap.add_argument("--outcome-col", default="deceased")
    ap.add_argument("--age-col", default="age")
    ap.add_argument("--sex-col", default="sex")
    ap.add_argument("--ablate-cols", help="comma list of score columns to ablate, e.g. "
                                          "score_selfreport,score_labs,score_full")
    ap.add_argument("--out", default="reports/validation")
    args = ap.parse_args()

    if args.synthetic:
        rows = synthetic_cohort(args.synthetic)
        rep = run(rows, "score_pct", "deceased", "age", "sex")
    elif args.cohort:
        rows = load_cohort(args.cohort)
        rep = run(rows, args.score_col, args.outcome_col, args.age_col, args.sex_col)
        if args.ablate_cols:
            rep["ablation_by_feature_class"] = ablation(
                rows, [c.strip() for c in args.ablate_cols.split(",")],
                args.outcome_col, args.age_col, args.sex_col)
    else:
        ap.error("pass --synthetic N or --cohort PATH")
    write_report(rep, args.out)
    print(json.dumps({k: rep[k] for k in ("n", "discrimination", "calibration")}, indent=2)[:800])
    print(f"\nwrote {args.out}/report.json and report.md")


if __name__ == "__main__":
    main()
