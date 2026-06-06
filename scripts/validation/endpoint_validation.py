"""Validate the model against the WHOLE ELC endpoint (not just mortality).

The ELC endpoint = exceptional age + good health, where good health = functional independence
(ADL/IADL) + self-rated health, with clinical depression controlled (Keyes' dual continua: low
self-report driven by depression is separated from decline).

NHANES lets us test two faces of it:
  1. SURVIVAL (prospective): higher score -> survives follow-up. (Run via validate.py.)
  2. HEALTHY-AGER composite (cross-sectional): among older adults, does the score identify those who
     are functionally independent + self-rated good health + not depressed?

Circularity guard: self-rated health, functional mobility and depression are INPUTS to score_full, and
they also build the endpoint -> so we score the composite with the OBJECTIVE Tier-3 lab score
(`score_labs`, no self-report) as the honest, non-circular test, and report score_full alongside for
contrast. Full ADL/IADL (PFQ061) is not a model input, so it is independent of the score either way.

Composite (among age>=AGE):  functional in {full, minimal}  AND  SRH good (HUQ010<=3)  AND  PHQ-9 < 10.
Reads cached cycle files (2007-2014) + the scored endocrine cohort.
Usage: python scripts/validation/endpoint_validation.py
"""
from __future__ import annotations

import glob
import json
import os

import pandas as pd

import metrics

CYCLES = ["2007-2008", "2009-2010", "2011-2012", "2013-2014"]
ADL = ["PFQ061H", "PFQ061I", "PFQ061J", "PFQ061K", "PFQ061T"]
IADL = ["PFQ061A", "PFQ061F", "PFQ061G"]
ITEMS = ADL + IADL


def _xpt(cyc, prefix):
    f = glob.glob(os.path.join("data", "raw", "datasets", "nhanes_cycles", cyc, f"{prefix}*.xpt"))
    if not f:
        return None
    df = pd.read_sas(f[0], format="xport")
    return df.set_index(df["SEQN"].astype("int64"))


def func_level(row):
    vals = [row[i] for i in ITEMS if i in row.index and row[i] in (1, 2, 3, 4)]
    if not vals:
        return None
    mx = max(vals)
    return "full" if mx == 1 else ("minimal" if mx == 2 else "dependent")


def phq9(row):
    items = [row[f"DPQ0{i}0"] for i in range(1, 10) if f"DPQ0{i}0" in row.index]
    vals = [v for v in items if v in (0, 1, 2, 3)]
    return sum(vals) if len(vals) >= 7 else None


def build_health():
    frames = []
    for cyc in CYCLES:
        demo, pfq, huq, dpq = _xpt(cyc, "DEMO"), _xpt(cyc, "PFQ"), _xpt(cyc, "HUQ"), _xpt(cyc, "DPQ")
        if demo is None or pfq is None or huq is None:
            continue
        d = pd.DataFrame(index=demo.index)
        d["age"] = demo["RIDAGEYR"]
        for it in ITEMS:
            d[it] = pfq[it] if it in pfq.columns else pd.NA
        d["func"] = d.apply(func_level, axis=1)
        d["srh"] = pd.to_numeric(huq["HUQ010"], errors="coerce") if "HUQ010" in huq.columns else pd.NA
        if dpq is not None:
            d["phq9"] = dpq.apply(phq9, axis=1)
        else:
            d["phq9"] = pd.NA
        frames.append(d.reset_index().rename(columns={"index": "subject_id", "SEQN": "subject_id"}))
    return pd.concat(frames, ignore_index=True)


def main():
    health = build_health()
    scored = pd.read_csv("data/processed/nhanes_cohort_endocrine.csv", low_memory=False)
    df = scored.merge(health[["subject_id", "func", "srh", "phq9"]], on="subject_id", how="inner")
    df["srh"] = pd.to_numeric(df["srh"], errors="coerce")
    df["phq9"] = pd.to_numeric(df["phq9"], errors="coerce")

    # ELC healthy-ager composite (primary): functional independence (graded) + good self-rated health.
    # Depression is a SEPARATE control/sensitivity, not a gate: PHQ-9 is a NHANES half-sample (too sparse
    # to gate without collapsing n), and per Keyes' dual-continua a low self-report driven by depression
    # is distinguished from decline rather than folded into the wellbeing score.
    df["func_ok"] = df["func"].isin(["full", "minimal"])
    df["srh_ok"] = df["srh"].isin([1, 2, 3])
    df["healthy_ager"] = (df["func_ok"] & df["srh_ok"]).astype(int)

    out = {}
    for age_min in (65, 75):
        sub = df[(df["age"] >= age_min) & df["func"].notna() & df["srh"].notna()].copy()
        y = sub["healthy_ager"].tolist()
        rec = {"n": len(sub), "healthy_ager_rate": round(sum(y) / len(y), 3) if y else None,
               "component_rates": {"func_independent": round(sub["func_ok"].mean(), 3),
                                   "srh_good": round(sub["srh_ok"].mean(), 3)}}
        for col in ("score_labs", "score_full"):
            s = pd.to_numeric(sub[col], errors="coerce")
            ok = s.notna()
            if ok.sum() > 50 and len(set(pd.Series(y)[ok.values])) == 2:
                rec[f"auc_{col}_to_healthy_ager"] = round(
                    metrics.auc(s[ok].tolist(), pd.Series(y)[ok.values].tolist()), 4)
        # depression-controlled sensitivity (small PHQ-9 subsample)
        sd = sub[sub["phq9"].notna()].copy()
        if len(sd) > 50:
            sd_y = (sd["func_ok"] & sd["srh_ok"] & (sd["phq9"] < 10)).astype(int)
            sl = pd.to_numeric(sd["score_labs"], errors="coerce")
            okd = sl.notna()
            if okd.sum() > 50 and sd_y.nunique() == 2:
                rec["depression_controlled_sensitivity"] = {
                    "n": int(len(sd)), "healthy_ager_rate": round(float(sd_y.mean()), 3),
                    "auc_score_labs": round(metrics.auc(sl[okd].tolist(), sd_y[okd.values].tolist()), 4)}
        out[f"age_{age_min}plus"] = rec

    os.makedirs("reports/endpoint_validation", exist_ok=True)
    with open("reports/endpoint_validation/endpoint.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    print("# ELC whole-endpoint validation (NHANES 2007-2014): healthy-ager composite\n")
    print("healthy_ager = functional independence (full/minimal) + self-rated health good "
          "(depression = separate sensitivity)")
    print("AUC reports discrimination of the OBJECTIVE lab score (non-circular) and full score.\n")
    for k, r in out.items():
        print(f"== {k}: n={r['n']}, healthy-ager rate={r['healthy_ager_rate']} ==")
        print(f"   components: {r['component_rates']}")
        print(f"   AUC score_labs -> healthy-ager: {r.get('auc_score_labs_to_healthy_ager')}  "
              f"(non-circular: objective biomarkers)")
        print(f"   AUC score_full -> healthy-ager: {r.get('auc_score_full_to_healthy_ager')}  "
              f"(includes self-report inputs -> partly circular)")
        sd = r.get("depression_controlled_sensitivity")
        if sd:
            print(f"   [depression-controlled sensitivity] n={sd['n']} rate={sd['healthy_ager_rate']} "
                  f"AUC score_labs={sd['auc_score_labs']}")
        print()
    print("wrote reports/endpoint_validation/endpoint.json")


if __name__ == "__main__":
    main()
