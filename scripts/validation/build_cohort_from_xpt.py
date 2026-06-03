"""Build a *powered* scored NHANES cohort from one or more cycles (long mortality follow-up).

The 2017-2018 cycle has only ~1-2 years of follow-up to the 2019 mortality cutoff (few deaths,
underpowered). Earlier cycles (1999-2010) have 10-20 years of follow-up and thousands of deaths.
This downloads each cycle's NHANES survey files + its Public-use Linked Mortality File, maps
variables -> model inputs via the versioned mappers, scores each adult (self-report / labs / full
for ablation), and joins the mortality outcome.

Self-report Layer-2 coverage (~15 of 31 questions, coverage varies by cycle): smoking (SMQ),
alcohol (ALQ), diet self-rating (DBQ700), sleep hours (SLQ), physical activity (PAQ rec-days),
**depression PHQ-9 (DPQ) — mental wellbeing**, self-rated health (HUQ/HSQ), partnership (DMDMARTL),
BMI/waist bands (BMX), diabetes (DIQ), hypertension/cholesterol (BPQ), CVD/cancer (MCQ), functional
mobility (PFQ), osteoporosis (OSQ). The remaining ~16 are constructs NHANES never measured (social
ties, purpose/meaning, cognitive hobbies, faith, family-history-of-longevity) — left unmapped rather
than fabricated. Labs (Layer 3): HDL, LDL, triglycerides, glucose, HbA1c, eGFR, CRP, BMI.

A per-cycle MANIFEST handles NHANES file-naming heterogeneity (verified against CDC):
  * 2005+:    HDL_x / TRIGLY_x / GLU_x / GHB_x / BIOPRO_x / CRP_x|HSCRP_x  (HDL var LBDHDD)
  * 1999-2000: LAB13 / LAB13AM / LAB10AM / LAB10 / LAB11 / LAB18           (HDL var LBDHDL)
  * 2001-2004: l13_x / l13am_x / l10am_x / l10_x / l11_x / l40_x           (HDL var LBDHDL)
CRP is mg/L hs-CRP (2015+, LBXHSCRP) or mg/dL CRP (<=2010, LBXCRP -> x10 to mg/L); absent 2011-2014.
eGFR is computed from serum creatinine (LBXSCR) via CKD-EPI 2021 (race-free).

Usage:
  python scripts/validation/build_cohort_from_xpt.py --cycles 1999-2000,2001-2002,2003-2004,\
2005-2006,2007-2008,2009-2010,2011-2012,2013-2014,2015-2016
  python scripts/validation/validate.py --cohort data/processed/nhanes_cohort_pooled_*.csv \
      --ablate-cols score_selfreport,score_labs,score_full --out reports/validation_pooled

DUC: NHANES + Linked Mortality data are for statistical analysis only; no re-identification; cite
NCHS. See scripts/validation/FETCH_MORTALITY.md.
"""
from __future__ import annotations

import argparse
import os

import pandas as pd

from centenarian_phenotype import map_value, score
from parse_nhanes_lmf import parse_file as parse_lmf

SUF = {"1999-2000": "", "2001-2002": "_B", "2003-2004": "_C", "2005-2006": "_D",
       "2007-2008": "_E", "2009-2010": "_F", "2011-2012": "_G", "2013-2014": "_H",
       "2015-2016": "_I", "2017-2018": "_J"}
YEAR = {c: c.split("-")[0] for c in SUF}
XPT_BASE = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/{year}/DataFiles/{name}.xpt"
LMF_BASE = ("https://ftp.cdc.gov/pub/Health_Statistics/NCHS/datalinkage/linked_mortality/"
            "NHANES_{a}_{b}_MORT_2019_PUBLIC.dat")


def qfile(base, cycle):
    """NHANES questionnaire filename for a cycle: NAME (1999-2000), name_x lowercase (2001-2004),
    NAME_X (2005+). Component mnemonics (BPQ/MCQ/PAQ/...) are stable across cycles."""
    s = SUF[cycle]
    yr = int(YEAR[cycle])
    if yr == 1999:
        return base
    if yr <= 2003:
        return f"{base.lower()}{s.lower()}"
    return f"{base}{s}"


def manifest(cycle):
    """Return {logical: xpt_filename} for a cycle. Variable names handled in build()."""
    s = SUF[cycle]
    yr = int(YEAR[cycle])
    m = {"demo": f"DEMO{s}", "bmx": f"BMX{s}", "smq": f"SMQ{s}", "diq": f"DIQ{s}"}
    # labs
    if yr >= 2005:
        m.update(hdl=f"HDL{s}", lipid=f"TRIGLY{s}", glu=f"GLU{s}", ghb=f"GHB{s}", bio=f"BIOPRO{s}")
        if yr <= 2010:
            m["crp"] = f"CRP{s}"          # LBXCRP mg/dL
        elif yr >= 2015:
            m["crp"] = f"HSCRP{s}"        # LBXHSCRP mg/L
        # 2011-2014: no CRP
    elif yr == 1999:
        m.update(hdl="LAB13", lipid="LAB13AM", glu="LAB10AM", ghb="LAB10", crp="LAB11", bio="LAB18")
    else:  # 2001-2002, 2003-2004 lowercase 'l..' lab files
        low = s.lower()
        m.update(hdl=f"l13{low}", lipid=f"l13am{low}", glu=f"l10am{low}", ghb=f"l10{low}",
                 crp=f"l11{low}", bio=f"l40{low}")
    # questionnaires (behavioral + self-report health). Loader skips any 404 (coverage varies).
    for base in ("BPQ", "MCQ", "PFQ", "ALQ", "PAQ", "DBQ", "HUQ", "HSQ", "DPQ", "SLQ", "OSQ"):
        m[base.lower()] = qfile(base, cycle)
    return m


def _dl(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        return dest
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
        f.write(r.read())
    return dest


def _xpt(d, year, name):
    dest = os.path.join(d, f"{name}.xpt")
    try:
        _dl(XPT_BASE.format(year=year, name=name), dest)
        df = pd.read_sas(dest, format="xport")
    except Exception as e:  # noqa: BLE001
        print(f"  (skip {name}: {e})")
        return None
    return df.set_index(df["SEQN"].astype("int64"))


def egfr_ckdepi(scr, age, sex):
    """CKD-EPI 2021 race-free eGFR (mL/min/1.73m^2) from serum creatinine (mg/dL)."""
    if scr is None or scr <= 0 or age is None:
        return None
    k = 0.7 if sex == "F" else 0.9
    a = -0.241 if sex == "F" else -0.302
    egfr = 142 * min(scr / k, 1) ** a * max(scr / k, 1) ** -1.200 * 0.9938 ** age
    if sex == "F":
        egfr *= 1.012
    return egfr


def build(cycle):
    if cycle not in SUF:
        raise SystemExit(f"unknown cycle {cycle}; choose from {sorted(SUF)}")
    year = YEAR[cycle]
    man = manifest(cycle)
    d = os.path.join("data", "raw", "datasets", "nhanes_cycles", cycle)
    os.makedirs(d, exist_ok=True)
    dfs = {k: _xpt(d, year, name) for k, name in man.items()}
    demo = dfs["demo"]
    if demo is None:
        raise SystemExit(f"could not load DEMO for {cycle}")

    a, b = cycle.split("-")
    raw_dat = os.path.join(d, f"NHANES_{a}_{b}_MORT_2019_PUBLIC.dat")
    _dl(LMF_BASE.format(a=a, b=b), raw_dat)
    lmf = {int(float(r["seqn"])): r for r in parse_lmf(raw_dat) if r["seqn"]}

    hdl_var = "LBDHDD" if int(year) >= 2005 else "LBDHDL"
    crp_var = "LBXHSCRP" if int(year) >= 2015 else "LBXCRP"
    crp_to_mgL = 1.0 if int(year) >= 2015 else 10.0  # older CRP is mg/dL

    def val(key, seqn, *cols):
        """First present/non-NaN value across candidate columns (handles cross-cycle renames)."""
        df = dfs.get(key)
        if df is None or seqn not in df.index:
            return None
        for col in cols:
            if col not in df.columns:
                continue
            v = df.at[seqn, col]
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
            if not pd.isna(v):
                return v
        return None

    def phq9(seqn):
        df = dfs.get("dpq")
        if df is None or seqn not in df.index:
            return None
        total, answered = 0.0, 0
        for i in range(1, 10):
            v = val("dpq", seqn, f"DPQ0{i}0")
            if v is not None and v <= 3:   # 0-3 valid; 7/9 = refused/don't know
                total += v
                answered += 1
        return total if answered >= 7 else None

    rows = []
    for seqn in demo.index:
        age = val("demo", seqn, "RIDAGEYR")
        if age is None or age < 18:
            continue
        sex = "M" if val("demo", seqn, "RIAGENDR") == 1 else "F"

        clinical = {}

        def add(feature, mapper_feature, raw):
            if raw is None:
                return
            al = map_value(mapper_feature, raw, sex=sex, age=age)["alignment"]
            if al is not None:
                clinical[feature] = al

        add("hdl_cholesterol", "hdl_cholesterol", val("hdl", seqn, hdl_var))
        add("triglycerides", "triglycerides", val("lipid", seqn, "LBXTR"))
        add("cholesterol", "ldl_cholesterol", val("lipid", seqn, "LBDLDL"))
        add("body_mass_index", "body_mass_index", val("bmx", seqn, "BMXBMI"))
        add("glucose", "glucose", val("glu", seqn, "LBXGLU"))
        add("hba1c", "hba1c", val("ghb", seqn, "LBXGH"))
        add("egfr", "egfr", egfr_ckdepi(val("bio", seqn, "LBXSCR"), age, sex))
        crp_raw = val("crp", seqn, crp_var)
        if crp_raw is not None:
            add("c_reactive_protein", "c_reactive_protein", crp_raw * crp_to_mgL)

        # ---- self-report Layer-2 answers mapped from NHANES (coverage varies by cycle) ----
        answers = {}

        def put(qid, idx):
            if idx is not None:
                answers[qid] = idx

        # substance use
        smq020, smq040 = val("smq", seqn, "SMQ020"), val("smq", seqn, "SMQ040")
        if smq020 == 2:
            put("q_smoking", 0)
        elif smq020 == 1:
            put("q_smoking", 1 if smq040 == 3 else (2 if smq040 in (1, 2) else 1))
        alq = val("alq", seqn, "ALQ130")                      # avg drinks/day on drinking days
        if val("alq", seqn, "ALQ101", "ALQ111") == 2:         # never drinks
            put("q_alcohol", 0)
        elif alq is not None:
            put("q_alcohol", 1 if alq <= 2 else (2 if alq <= 4 else 3))

        # diet (self-rated DBQ700 1=excellent..5=poor) -> plant/balanced/processed
        dbq = val("dbq", seqn, "DBQ700")
        if dbq in (1, 2, 3, 4, 5):
            put("q_diet", {1: 0, 2: 0, 3: 1, 4: 2, 5: 2}[dbq])

        # sleep hours (SLD010H 2005-2014; SLD012 2015+); restfulness not captured -> conservative
        slp = val("slq", seqn, "SLD012", "SLD010H")
        if slp is not None:
            put("q_sleep", 1 if 7 <= slp <= 9 else 2)

        # physical activity: moderate/vigorous recreational days/week (2007+ PAQ schema)
        pa_days = None
        for c in ("PAQ655", "PAQ670"):                        # vigorous-rec days, moderate-rec days
            dv = val("paq", seqn, c)
            if dv is not None:
                pa_days = max(pa_days or 0, dv)
        if pa_days is not None:
            put("q_pa_frequency", 0 if pa_days >= 5 else (1 if pa_days >= 3 else (2 if pa_days >= 1 else 3)))

        # mental wellbeing: PHQ-9 -> depression (current symptom severity)
        score9 = phq9(seqn)
        if score9 is not None:
            put("q_depression", 0 if score9 < 5 else (1 if score9 < 10 else 2))

        # self-rated health (HUQ010 / HSD010, 1=excellent..5=poor) -> gold-standard mortality item
        srh = val("huq", seqn, "HUQ010") or val("hsq", seqn, "HSD010")
        if srh in (1, 2, 3, 4, 5):
            put("q_self_rated_health", {1: 0, 2: 1, 3: 1, 4: 2, 5: 3}[srh])

        # family / partnership (marital status from demographics)
        mar = val("demo", seqn, "DMDMARTL")
        if mar in (1, 2, 3, 4, 5, 6):
            put("q_family_partner", {1: 0, 6: 1, 2: 2, 3: 3, 4: 3, 5: 3}[mar])

        # body composition self-report bands (deepest-layer L3 BMI supersedes in the full score)
        bmi = val("bmx", seqn, "BMXBMI")
        if bmi is not None:
            bi = 0 if 18.5 <= bmi < 25 else (3 if bmi < 18.5 else (2 if bmi < 30 else 3))
            put("q_body_mass_index", bi)
        waist = val("bmx", seqn, "BMXWAIST")
        if waist is not None:
            hi, mid = (88, 80) if sex == "F" else (102, 94)
            put("q_waist_circumference", 0 if waist < mid else (1 if waist < hi else 2))

        # disease escape / functional self-report
        diq010 = val("diq", seqn, "DIQ010")
        if diq010 in (1, 2, 3):
            put("q_diabetes", {2: 0, 3: 1, 1: 2}[diq010])
        bpq020, bpq040 = val("bpq", seqn, "BPQ020"), val("bpq", seqn, "BPQ040A")
        if bpq020 == 2:
            put("q_hypertension", 0)
        elif bpq020 == 1:
            put("q_hypertension", 2 if bpq040 == 1 else 3)
        bpq080 = val("bpq", seqn, "BPQ080")
        if bpq080 == 2:
            put("q_cholesterol", 0)
        elif bpq080 == 1:
            put("q_cholesterol", 2)
        if val("mcq", seqn, "MCQ160E") == 1 or val("mcq", seqn, "MCQ160F") == 1:
            put("q_cardiovascular_event", 2)
        elif val("mcq", seqn, "MCQ160E") == 2 or val("mcq", seqn, "MCQ160F") == 2:
            put("q_cardiovascular_event", 0)
        mcq220 = val("mcq", seqn, "MCQ220")
        if mcq220 == 1:
            put("q_cancer_history", 1)
        elif mcq220 == 2:
            put("q_cancer_history", 0)
        pf = val("pfq", seqn, "PFQ061B")                      # walking quarter mile: 1 none..4 unable
        if pf in (1, 2, 3, 4):
            put("q_functional_mobility", {1: 0, 2: 1, 3: 2, 4: 2}[pf])
        osq = val("osq", seqn, "OSQ060")
        if osq == 1:
            put("q_bone_health", 2)
        elif osq == 2:
            put("q_bone_health", 0)

        if not answers and not clinical:
            continue

        def sc(layer, ans, clin):
            try:
                return score(layer, ans, clinical=clin or None, strict=False)["score_pct"]
            except Exception:  # noqa: BLE001
                return ""

        s_self = sc(2, answers, None) if answers else ""
        s_labs = sc(3, {}, clinical) if clinical else ""
        s_full = sc(3, answers, clinical) if clinical else s_self
        m = lmf.get(int(seqn))
        deceased = permth = ""
        if m and m.get("eligstat") == "1" and m.get("mortstat") in ("0", "1"):
            deceased, permth = m["mortstat"], m.get("permth_exm", "")
        rows.append({"subject_id": int(seqn), "cycle": cycle, "age": round(age, 1), "sex": sex,
                     "score_pct": s_full, "score_full": s_full,
                     "score_selfreport": s_self, "score_labs": s_labs,
                     "n_clinical": len(clinical), "n_answers": len(answers),
                     "age_band": "18-49" if age < 50 else ("50-64" if age < 65 else
                                  ("65-74" if age < 75 else "75+")),
                     "deceased": deceased, "permth_exm": permth})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycle", help="single cycle, e.g. 2005-2006")
    ap.add_argument("--cycles", help="comma list to POOL")
    ap.add_argument("--out")
    args = ap.parse_args()
    if not args.cycle and not args.cycles:
        ap.error("pass --cycle or --cycles")
    cycles = [c.strip() for c in (args.cycles.split(",") if args.cycles else [args.cycle])]
    rows = []
    for c in cycles:
        print(f"[{c}] building...")
        rows += build(c)
    tag = ("pooled_" + "_".join(YEAR[c] for c in cycles)) if len(cycles) > 1 else cycles[0]
    out = args.out or os.path.join("data", "processed", f"nhanes_cohort_{tag}.csv")
    pd.DataFrame(rows).to_csv(out, index=False)
    linked = sum(1 for r in rows if r["deceased"] != "")
    deaths = sum(1 for r in rows if r["deceased"] == "1")
    avg_clin = (sum(r["n_clinical"] for r in rows) / len(rows)) if rows else 0
    print(f"wrote {out}: {len(rows)} scored, {linked} linked, {deaths} deaths, "
          f"avg {avg_clin:.1f} labs/subject (cycles {cycles}).")


if __name__ == "__main__":
    main()
