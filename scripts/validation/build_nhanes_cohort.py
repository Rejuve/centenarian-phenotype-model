"""Build a scored NHANES cohort for validation: map NHANES variables -> model inputs, score each
participant, and (if the parsed Linked Mortality File is present) join the survival outcome.

This is an **initial adapter** covering the cleanly-available NHANES variables; it is meant to be
extended (more behavioral modules: PAQ/ALQ/SLQ). Mappings use the versioned `mappers.py` so no
cut-offs are reinvented.

Inputs (all under data/raw/datasets/, already in this repo's data tree):
  nhanes_demographics.csv  (SEQN, RIAGENDR sex, RIDAGEYR age)
  nhanes_cholesterol_hdl.csv (LBDHDD), nhanes_triglycerides.csv (LBXTR, LBDLDL),
  nhanes_crp.csv (LBXHSCRP), nhanes_body_measures.csv (BMXBMI),
  nhanes_smoking.csv (SMQ020/SMQ040), nhanes_diabetes.csv (DIQ010)
Optional outcome:
  --lmf data/processed/nhanes_lmf_2017_2018.csv  (from parse_nhanes_lmf.py)

Output: data/processed/nhanes_scored_cohort.csv  (subject_id, age, sex, score_pct, n_features,
        deceased, permth_exm, age_band) — feed to validate.py.

Usage:
  python scripts/validation/build_nhanes_cohort.py --lmf data/processed/nhanes_lmf_2017_2018.csv
"""
from __future__ import annotations

import argparse
import csv
import os

from centenarian_phenotype import map_value, score

RAW = os.path.join("data", "raw", "datasets")
OUT = os.path.join("data", "processed", "nhanes_scored_cohort.csv")


def _load(name):
    path = os.path.join(RAW, name)
    if not os.path.exists(path):
        return {}
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        return {r["SEQN"]: r for r in csv.DictReader(f) if r.get("SEQN")}


def _num(r, col):
    if not r:
        return None
    v = (r.get(col) or "").strip()
    try:
        return float(v)
    except ValueError:
        return None


def _align(feature, value, sex):
    if value is None:
        return None
    try:
        return map_value(feature, value, sex=sex)["alignment"]
    except KeyError:
        return None


def build(lmf_path=None):
    demo = _load("nhanes_demographics.csv")
    hdl = _load("nhanes_cholesterol_hdl.csv")
    trig = _load("nhanes_triglycerides.csv")
    crp = _load("nhanes_crp.csv")
    body = _load("nhanes_body_measures.csv")
    smoke = _load("nhanes_smoking.csv")
    diab = _load("nhanes_diabetes.csv")
    lmf = {}
    if lmf_path and os.path.exists(lmf_path):
        with open(lmf_path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                lmf[str(int(float(r["seqn"])))] = r  # normalise key

    rows = []
    for seqn, d in demo.items():
        age = _num(d, "RIDAGEYR")
        if age is None or age < 18:
            continue
        sex = "M" if (d.get("RIAGENDR") or "").strip() in ("1", "1.0") else "F"

        # --- tier-3 clinical alignments (only features that exist in the tier-3 model) ---
        clinical = {}
        for feature, src, col in [
            ("hdl_cholesterol", hdl.get(seqn), "LBDHDD"),
            ("triglycerides", trig.get(seqn), "LBXTR"),
            ("cholesterol", trig.get(seqn), "LBDLDL"),     # tier-3 'cholesterol' is LDL-directional
            ("c_reactive_protein", crp.get(seqn), "LBXHSCRP"),
            ("body_mass_index", body.get(seqn), "BMXBMI"),
        ]:
            # 'cholesterol' uses the LDL mapper; map_value keys on feature, so map LDL explicitly
            if feature == "cholesterol":
                a = _align("ldl_cholesterol", _num(src, col), sex)
            else:
                a = _align(feature, _num(src, col), sex)
            if a is not None:
                clinical[feature] = a

        # --- behavioral/self-report tier-2 answers ---
        answers = {}
        s = smoke.get(seqn)
        if s:
            smq020 = (s.get("SMQ020") or "").strip()
            smq040 = (s.get("SMQ040") or "").strip()
            if smq020 == "2":
                answers["q_smoking"] = 0                      # never
            elif smq020 == "1":
                answers["q_smoking"] = 1 if smq040 == "3" else (2 if smq040 in ("1", "2") else 1)
        dq = diab.get(seqn)
        if dq:
            diq010 = (dq.get("DIQ010") or "").strip()
            answers["q_diabetes"] = {"2": 0, "3": 1, "1": 2}.get(diq010, None)
            if answers["q_diabetes"] is None:
                answers.pop("q_diabetes")

        if not answers and not clinical:
            continue
        layer = 3 if clinical else 2
        res = score(layer, answers, clinical=clinical or None, strict=False)

        row = {"subject_id": seqn, "age": round(age, 1), "sex": sex,
               "score_pct": res["score_pct"], "n_features": res["answered"],
               "age_band": "18-49" if age < 50 else ("50-64" if age < 65 else
                            ("65-74" if age < 75 else "75+")),
               "deceased": "", "permth_exm": ""}
        m = lmf.get(str(int(float(seqn))))
        if m and m.get("eligstat") == "1" and m.get("mortstat") in ("0", "1"):
            row["deceased"] = m["mortstat"]
            row["permth_exm"] = m.get("permth_exm", "")
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lmf", help="parsed NHANES LMF csv (from parse_nhanes_lmf.py); "
                                  "omit to emit scores without the mortality outcome")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    if not os.path.exists(os.path.join(RAW, "nhanes_demographics.csv")):
        raise SystemExit(f"NHANES demographics not found under {RAW}/ — see "
                         "scripts/validation/FETCH_MORTALITY.md")
    rows = build(args.lmf)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    linked = sum(1 for r in rows if r["deceased"] != "")
    print(f"wrote {args.out}: {len(rows)} scored participants "
          f"({linked} linked to mortality outcome).")
    if not linked:
        print("No mortality outcome joined. Fetch + parse the NHANES LMF, then pass --lmf. "
              "See scripts/validation/FETCH_MORTALITY.md")


if __name__ == "__main__":
    main()
