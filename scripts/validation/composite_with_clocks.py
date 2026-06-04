"""Validate the lift from folding DNA-methylation clocks into the composite Tier-3 score.

The cross-sectional cohort composite (build_cohort_from_xpt.py) does not carry the clocks — they exist
only for the NHANES 1999-2002 DNAm subsample (build_epi_cohort.py). Here we merge the clock alignments
into the main cohort for the overlapping subjects and compare, on that subsample, the Tier-3 composite
WITHOUT vs WITH the clocks: AUC(score -> survival) and the age/sex-adjusted standardized coefficient
(negative = higher score lowers modelled mortality), 24-month landmark in parentheses.

Reuses the access-partitioned weighting from tier_ablation_by_access.py. Clocks are weighted at the
epigenetic feature weight (0.66); the scale-mismatched DNAm-telomere feature is excluded.

Usage:
  python scripts/validation/composite_with_clocks.py
"""
from __future__ import annotations

import argparse
import json
import os

import pandas as pd

from tier_ablation_by_access import feature_weights, tier_score, evaluate

CLOCK_COLS = ["f_clock_horvath", "f_clock_hannum", "f_clock_skinblood", "f_clock_phenoage",
              "f_clock_grimage", "f_clock_grimage2", "f_clock_dunedinpace"]  # exclude dnam_telomere (scale)
CLOCK_WEIGHT = 0.66


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", default="data/processed/nhanes_cohort_feat_v2.csv")
    ap.add_argument("--epi", default="data/processed/nhanes_epi_cohort.csv")
    ap.add_argument("--out", default="reports/composite_with_clocks")
    args = ap.parse_args()

    df = pd.read_csv(args.cohort, low_memory=False)
    epi = pd.read_csv(args.epi, low_memory=False)
    clk = [c for c in CLOCK_COLS if c in epi.columns]
    df = df.merge(epi[["subject_id"] + clk], on="subject_id", how="left")
    # restrict to the DNAm subsample (subjects with clocks) for a fair within-subject comparison
    df = df[df[clk].notna().any(axis=1)].copy()
    df["deceased"] = pd.to_numeric(df["deceased"], errors="coerce")

    fw = feature_weights()
    base = [(c, w) for c, (a, w) in fw.items() if a in ("self_report", "anthropometric", "lab")]
    clocks = [(c, CLOCK_WEIGHT) for c in clk]

    df["score_tier3_no_clocks"], _ = tier_score(df, base)
    df["score_tier3_with_clocks"], _ = tier_score(df, base + clocks)

    out = {
        "dnam_subsample_n": int(len(df)),
        "deaths": int((df["deceased"] == 1).sum()),
        "clocks_included": clk,
        "tier3_without_clocks": evaluate(df, "score_tier3_no_clocks"),
        "tier3_with_clocks": evaluate(df, "score_tier3_with_clocks"),
    }
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "composite_with_clocks.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"DNAm subsample n={out['dnam_subsample_n']} deaths={out['deaths']}")
    for k in ("tier3_without_clocks", "tier3_with_clocks"):
        v = out[k]
        print(f"  {k}: AUC {v['auc_score_to_survival']}  adj.coef {v['adj_coef']} "
              f"(landmark {v['adj_coef_landmark']})  n={v['n']}")


if __name__ == "__main__":
    main()
