"""Build an epigenetic-clock alignment cohort from the NHANES DNAm public file (dnmepi.sas7bdat,
1999-2002 subsample) linked to mortality, so the standard per-feature harness
(feature_association.py) can score the clocks the same way as every other Tier-3 measured feature.

For each subject the chronological age, sex, and mortality outcome are taken from an already-built
NHANES cohort CSV (build_cohort_from_xpt.py, which carries age/sex/deceased/permth_exm by SEQN).
Each clock is turned into an alignment in [0,1] via the package mappers:
  * age-type clocks (Horvath/Hannum/SkinBlood/PhenoAge/GrimAge/GrimAge2): age-acceleration =
    clock_age - chronological_age, lower favourable -> mapper "epigenetic_age_acceleration".
  * DunedinPoAm: pace of ageing (~1.0/yr), lower favourable -> mapper "dunedinpace_2022".
  * HorvathTelo: DNAm-predicted telomere length, longer favourable -> mapper "telomere_length".

DUC: NHANES DNAm + Linked Mortality data are for statistical analysis only; no re-identification;
cite NCHS (DNAm Epigenetic Biomarkers, 1999-2002, published 2024). Aggregate results only.

Usage:
  python scripts/validation/build_epi_cohort.py \
      --dnmepi data/raw/dnmepi.sas7bdat \
      --cohort data/processed/nhanes_cohort_feat_v2.csv \
      --out data/processed/nhanes_epi_cohort.csv
"""
from __future__ import annotations

import argparse

import pandas as pd

from centenarian_phenotype import map_value

# clock column -> (alignment feature id, mapper, kind)
AGE_CLOCKS = {
    "HorvathAge": "f_clock_horvath",
    "HannumAge": "f_clock_hannum",
    "SkinBloodAge": "f_clock_skinblood",
    "PhenoAge": "f_clock_phenoage",
    "GrimAgeMort": "f_clock_grimage",
    "GrimAge2Mort": "f_clock_grimage2",
}


def _align_accel(clock_age, chrono_age):
    if pd.isna(clock_age) or pd.isna(chrono_age):
        return None
    return map_value("epigenetic_age_acceleration", float(clock_age) - float(chrono_age))["alignment"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dnmepi", default="data/raw/dnmepi.sas7bdat")
    ap.add_argument("--cohort", default="data/processed/nhanes_cohort_feat_v2.csv")
    ap.add_argument("--out", default="data/processed/nhanes_epi_cohort.csv")
    args = ap.parse_args()

    epi = pd.read_sas(args.dnmepi)
    epi["SEQN"] = epi["SEQN"].astype("int64")
    coh = pd.read_csv(args.cohort, low_memory=False)
    coh = coh[["subject_id", "age", "sex", "deceased", "permth_exm"]].copy()
    coh["subject_id"] = pd.to_numeric(coh["subject_id"], errors="coerce")

    rows = []
    cmap = {int(r.subject_id): r for r in coh.itertuples() if pd.notna(r.subject_id)}
    for r in epi.itertuples():
        seqn = int(r.SEQN)
        base = cmap.get(seqn)
        if base is None:
            continue
        out = {"subject_id": seqn, "age": base.age, "sex": base.sex,
               "deceased": base.deceased, "permth_exm": base.permth_exm}
        for col, fid in AGE_CLOCKS.items():
            al = _align_accel(getattr(r, col, None), base.age)
            if al is not None:
                out[fid] = al
        pace = getattr(r, "DunedinPoAm", None)
        if pace is not None and pd.notna(pace):
            out["f_clock_dunedinpace"] = map_value("dunedinpace_2022", float(pace))["alignment"]
        telo = getattr(r, "HorvathTelo", None)
        if telo is not None and pd.notna(telo):
            out["f_clock_dnam_telomere"] = map_value("telomere_length", float(telo))["alignment"]
        rows.append(out)

    df = pd.DataFrame(rows)
    df.to_csv(args.out, index=False)
    linked = df["deceased"].isin([0, 1, "0", "1"]).sum()
    print(f"wrote {args.out}: {len(df)} subjects with clocks, {linked} mortality-linked.")
    for fid in [v for v in AGE_CLOCKS.values()] + ["f_clock_dunedinpace", "f_clock_dnam_telomere"]:
        if fid in df:
            print(f"  {fid}: {df[fid].notna().sum()}")


if __name__ == "__main__":
    main()
