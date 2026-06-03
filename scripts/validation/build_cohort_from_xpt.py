"""Build a *powered* scored NHANES cohort from an earlier cycle (long mortality follow-up).

The 2017-2018 cycle has only ~1-2 years of follow-up to the 2019 mortality cutoff (few deaths,
underpowered). Earlier cycles (e.g. 2005-2006) have ~14 years of follow-up and thousands of deaths —
the right basis for calibrating the phenotype -> survival mapping.

This downloads (if missing) the cycle's NHANES survey XPT files from the current CDC path
(https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/<year>/DataFiles/<FILE>.xpt) plus the cycle's
Public-use Linked Mortality File, maps variables -> model inputs via the versioned mappers, scores
each adult, joins the mortality outcome, and writes a scored-cohort CSV for validate.py.

Usage:
  python scripts/validation/build_cohort_from_xpt.py --cycle 2005-2006
  python scripts/validation/validate.py --cohort data/processed/nhanes_cohort_2005-2006.csv \
      --out reports/validation_2005_2006

DUC: NHANES + Linked Mortality data are for statistical analysis only; no re-identification; cite
NCHS. See scripts/validation/FETCH_MORTALITY.md.
"""
from __future__ import annotations

import argparse
import os

import pandas as pd

from centenarian_phenotype import map_value, score
from parse_nhanes_lmf import parse_file as parse_lmf

# cycle -> (year_folder, file suffix). Survey XPT files share the suffix; CRP variable differs.
CYCLES = {
    "1999-2000": ("1999", ""), "2001-2002": ("2001", "_B"), "2003-2004": ("2003", "_C"),
    "2005-2006": ("2005", "_D"), "2007-2008": ("2007", "_E"), "2009-2010": ("2009", "_F"),
    "2011-2012": ("2011", "_G"), "2013-2014": ("2013", "_H"), "2015-2016": ("2015", "_I"),
    "2017-2018": ("2017", "_J"),
}
XPT_BASE = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/{year}/DataFiles/{name}.xpt"
LMF_BASE = ("https://ftp.cdc.gov/pub/Health_Statistics/NCHS/datalinkage/linked_mortality/"
            "NHANES_{a}_{b}_MORT_2019_PUBLIC.dat")


def _dl(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        return dest
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        f.write(r.read())
    return dest


def _xpt(d, year, base, suffix):
    """Download+read an NHANES XPT (base like 'HDL'); returns DataFrame indexed by SEQN or None."""
    name = f"{base}{suffix}"
    dest = os.path.join(d, f"{name}.xpt")
    try:
        _dl(XPT_BASE.format(year=year, name=name), dest)
        df = pd.read_sas(dest, format="xport")
    except Exception as e:  # noqa: BLE001 - cycle may lack a file; skip gracefully
        print(f"  (skip {name}: {e})")
        return None
    df = df.set_index(df["SEQN"].astype("int64"))
    return df


def build(cycle):
    if cycle not in CYCLES:
        raise SystemExit(f"unknown cycle {cycle}; choose from {sorted(CYCLES)}")
    year, suf = CYCLES[cycle]
    d = os.path.join("data", "raw", "datasets", "nhanes_cycles", cycle)
    os.makedirs(d, exist_ok=True)

    demo = _xpt(d, year, "DEMO", suf)
    if demo is None:
        raise SystemExit("could not load DEMO for this cycle")
    hdl = _xpt(d, year, "HDL", suf)          # older cycles: HDL may be in 'l13_*'; LBDHDD if present
    trig = _xpt(d, year, "TRIGLY", suf)      # LBXTR, LBDLDL
    crp_hs = _xpt(d, year, "HSCRP", suf)     # 2015+ hs-CRP (mg/L) LBXHSCRP
    crp_old = _xpt(d, year, "CRP", suf)      # older CRP (mg/dL) LBXCRP -> *10 = mg/L
    bmx = _xpt(d, year, "BMX", suf)          # BMXBMI
    smq = _xpt(d, year, "SMQ", suf)          # SMQ020, SMQ040
    diq = _xpt(d, year, "DIQ", suf)          # DIQ010

    # mortality
    a, b = cycle.split("-")
    lmf_path = os.path.join("data", "processed", f"nhanes_lmf_{a}_{b}.csv")
    raw_dat = os.path.join(d, f"NHANES_{a}_{b}_MORT_2019_PUBLIC.dat")
    _dl(LMF_BASE.format(a=a, b=b), raw_dat)
    lmf = {int(float(r["seqn"])): r for r in parse_lmf(raw_dat) if r["seqn"]}

    def val(df, seqn, col):
        if df is None or col not in df.columns or seqn not in df.index:
            return None
        v = df.at[seqn, col]
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        return None if pd.isna(v) else v

    rows = []
    for seqn in demo.index:
        age = val(demo, seqn, "RIDAGEYR")
        if age is None or age < 18:
            continue
        sex = "M" if val(demo, seqn, "RIAGENDR") == 1 else "F"

        clinical = {}

        def add(feature, mapper_feature, raw):
            if raw is None:
                return
            a_ = map_value(mapper_feature, raw, sex=sex)["alignment"]
            if a_ is not None:
                clinical[feature] = a_

        add("hdl_cholesterol", "hdl_cholesterol", val(hdl, seqn, "LBDHDD"))
        add("triglycerides", "triglycerides", val(trig, seqn, "LBXTR"))
        add("cholesterol", "ldl_cholesterol", val(trig, seqn, "LBDLDL"))
        add("body_mass_index", "body_mass_index", val(bmx, seqn, "BMXBMI"))
        # CRP: prefer hs-CRP (mg/L); else convert older CRP (mg/dL) to mg/L (x10)
        if val(crp_hs, seqn, "LBXHSCRP") is not None:
            add("c_reactive_protein", "c_reactive_protein", val(crp_hs, seqn, "LBXHSCRP"))
        elif val(crp_old, seqn, "LBXCRP") is not None:
            add("c_reactive_protein", "c_reactive_protein", val(crp_old, seqn, "LBXCRP") * 10.0)

        answers = {}
        smq020, smq040 = val(smq, seqn, "SMQ020"), val(smq, seqn, "SMQ040")
        if smq020 == 2:
            answers["q_smoking"] = 0
        elif smq020 == 1:
            answers["q_smoking"] = 1 if smq040 == 3 else (2 if smq040 in (1, 2) else 1)
        diq010 = val(diq, seqn, "DIQ010")
        if diq010 in (1, 2, 3):
            answers["q_diabetes"] = {2: 0, 3: 1, 1: 2}[diq010]

        if not answers and not clinical:
            continue
        layer = 3 if clinical else 2
        res = score(layer, answers, clinical=clinical or None, strict=False)
        m = lmf.get(int(seqn))
        deceased = permth = ""
        if m and m.get("eligstat") == "1" and m.get("mortstat") in ("0", "1"):
            deceased, permth = m["mortstat"], m.get("permth_exm", "")
        rows.append({"subject_id": int(seqn), "age": round(age, 1), "sex": sex,
                     "score_pct": res["score_pct"], "n_features": res["answered"],
                     "age_band": "18-49" if age < 50 else ("50-64" if age < 65 else
                                  ("65-74" if age < 75 else "75+")),
                     "deceased": deceased, "permth_exm": permth})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycle", required=True, help="e.g. 2005-2006")
    ap.add_argument("--out")
    args = ap.parse_args()
    rows = build(args.cycle)
    out = args.out or os.path.join("data", "processed", f"nhanes_cohort_{args.cycle}.csv")
    pd.DataFrame(rows).to_csv(out, index=False)
    linked = sum(1 for r in rows if r["deceased"] != "")
    deaths = sum(1 for r in rows if r["deceased"] == "1")
    print(f"wrote {out}: {len(rows)} scored, {linked} linked, {deaths} deaths "
          f"(cycle {args.cycle}, follow-up to 2019-12-31).")


if __name__ == "__main__":
    main()
