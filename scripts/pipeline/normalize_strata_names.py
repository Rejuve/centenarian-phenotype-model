"""
Normalization pass on biomarker_name + contrast_type in
biomarker_pooled_strata.csv. Writes biomarker_pooled_strata_normalized.csv
(original is NOT overwritten).

Approach: transparent, ordered canonical dictionary. For each raw name we strip
method/statistical phrases and match the core anatomical/clinical term against a
priority-ordered list (specific terms before general). Output keeps every
original column. The input strata name is written as `biomarker_name_raw` and the
canonical term as `biomarker_name` (the standard cross-file join key); also adds:
    contrast_type_normalized    snake_case (controlled vocab)
    name_changed                core term differs from the original (not just
                                whitespace/case) -> needs your eyes
    review_priority             high | low | none
    normalization_note          what was done / why flagged
"""
import re
import pandas as pd

SRC = "data/processed/biomarker_pooled_strata.csv"
OUT = "data/processed/biomarker_pooled_strata_normalized.csv"

# RAW biomarker names to drop entirely from the feature set (user decisions
# 2026-06-01). Keyed on the original name, NOT the canonical, because some of
# these canonicalize to legitimate terms (e.g. "weighting but not diabetes" ->
# diabetes, "both parents top survival" -> survival) and must not delete those.
# (1) extraction garbage + negation; (2) the two ambiguous depression rows.
DROP_RAW = {
    "each component was scored", "each scored", "hr ci",
    "both parents top survival", "response had survival benefit",
    "weighting but not diabetes",
    "stroke hr ci depression", "pd hr ci depression",
}

# method / statistical / filler tokens to strip when forming the fallback term
STRIP_PHRASES = [
    "multivariate analysis", "confidence interval", "all-cause", "hr ci",
    "ci ", " ci", " hr", "hr ", " ivw", "ivw ", " pd", "pd ", " adj",
    "mmse adj", "nhanes",
]
STRIP_WORDS = {
    "multivariate", "analysis", "specifically", "without", "develop",
    "developing", "predicted", "predictor", "pooled", "almost", "fold",
    "quartiles", "raised", "reducing", "lowest", "usual", "early",
    "strongest", "including", "components", "component", "category", "ivw",
    "hr", "ci", "or", "confidence", "interval", "pd", "adj", "mmse", "scored",
    "each", "was", "showed", "had", "response", "selection", "status", "stage",
    "strata", "seldom", "loneliness", "youthful", "brain", "top", "both",
    "parents", "corresponding", "requirement", "daily", "grs", "sup", "the",
    "and", "but", "not", "con", "por", "de", "showed",
}

# (trigger substrings, canonical snake_case). ORDER MATTERS: most specific first.
CANON = [
    (["all-cause mortality", "all cause mortality"], "all_cause_mortality"),
    (["cardiovascular mortality", "cvd mortality", "morir por causas cardiovascular",
      "causas cardiovasculares"], "cardiovascular_mortality"),
    (["coronary heart disease"], "coronary_heart_disease"),
    (["hdl cholesterol"], "hdl_cholesterol"),
    (["breast cancer"], "breast_cancer"),
    (["prostate cancer"], "prostate_cancer"),
    (["skin cancer"], "skin_cancer"),
    (["myocardial infarction"], "myocardial_infarction"),
    (["estimated glomerular filtration"], "estimated_glomerular_filtration_rate"),
    (["c-reactive protein", "creactive protein"], "c_reactive_protein"),
    (["interleukin-6", "interleukin 6", "il-6"], "interleukin_6"),
    # IGF-1 must precede the generic "insulin" trigger so it is not swallowed.
    (["insulin-like growth factor", "igf-1", "igf 1", "igfbp"], "igf_1"),
    (["thyroid stimulating hormone"], "thyroid_stimulating_hormone"),
    (["subclinical hypothyroidism"], "subclinical_hypothyroidism"),
    (["subclinical hyperthyroidism"], "subclinical_hyperthyroidism"),
    (["overt hyperthyroidism", "hyperthyroidism"], "hyperthyroidism"),
    (["hypothyroidism"], "hypothyroidism"),
    (["euthyroid"], "euthyroid"),
    (["diabetes mellitus", "type diabetes", "diabetes t2d", "t2d", "diabetes"],
     "diabetes"),
    (["hypertriglyceridemia"], "hypertriglyceridemia"),
    (["triglycerid"], "triglycerides"),
    (["body mass index", "bmi"], "body_mass_index"),
    (["waist circumference"], "waist_circumference"),
    (["calf circumference"], "calf_circumference"),
    (["handgrip strength", "grip strength", "grip"], "grip_strength"),
    (["limb muscle strength", "muscle strength"], "muscle_strength"),
    (["muscle mass"], "muscle_mass"),
    (["physical frailty", "developing frailty", "frailty"], "frailty"),
    (["pre-frailty", "prefrailty", "pre frailty"], "pre_frailty"),
    (["sarcopenia"], "sarcopenia"),
    (["hip oa", "hip osteoarthritis"], "hip_osteoarthritis"),
    (["osteoporosis"], "osteoporosis"),
    (["multimorbidity"], "multimorbidity"),
    (["comorbidity"], "comorbidity"),
    (["mets prevalence", "metabolic syndrome"], "metabolic_syndrome"),
    (["lv diastolic dysfunction", "diastolic dysfunction"],
     "left_ventricular_diastolic_dysfunction"),
    (["incident cvd", "cardiovascular disease", "cardiovascular causes",
      "cardiovascular symptoms", "cardiovascular benefits", "cardiovascular",
      "cardiovasculares", "cardiovascular benef"], "cardiovascular_disease"),
    (["alzheimer"], "alzheimer_disease"),
    (["dementia"], "dementia"),
    (["depression"], "depression"),
    (["stroke"], "stroke"),
    (["telomere length"], "telomere_length"),
    (["telomerase"], "telomerase"),
    (["epigenetic age"], "epigenetic_age"),
    # SBP / DBP are distinct biomarkers; keep them out of generic blood_pressure.
    (["systolic blood pressure"], "systolic_blood_pressure"),
    (["diastolic blood pressure"], "diastolic_blood_pressure"),
    (["blood pressure"], "blood_pressure"),
    (["hypertension"], "hypertension"),
    (["cholesterol"], "cholesterol"),
    (["cortisol"], "cortisol"),
    (["testosterone"], "testosterone"),
    (["albumin"], "albumin"),
    (["serum urea", "urea"], "serum_urea"),
    (["white blood cell"], "white_blood_cell"),
    (["dheas", "dhea"], "dheas"),
    (["tnf"], "tnf_alpha"),
    (["inflammation"], "inflammation"),
    (["vitamin"], "vitamin"),
    (["weight loss"], "weight_loss"),
    (["underweight"], "underweight"),
    (["insulin"], "insulin"),
    (["adl", "activities of daily"], "activities_of_daily_living"),
    (["lifespan"], "lifespan"),
    (["longevity"], "longevity"),
    (["morbidity"], "all_cause_morbidity"),
    (["survival"], "survival"),
    (["mortality"], "mortality"),
    (["cancer"], "cancer"),
    (["diet"], "diet"),
]

# raw names that are extraction garbage (no real clinical term) -> hard review
GARBAGE = {"each component was scored", "each scored", "hr ci",
           "both parents top survival", "response had survival benefit",
           "weighting but not diabetes"}

# raw names where the mapping is genuinely ambiguous -> flag even though mapped
AMBIGUOUS = {"stroke hr ci depression", "pd hr ci depression",
             "weighting but not diabetes", "mortality including glucose"}

NON_ENGLISH = ["asociaron", "associados", "benef cios", "morir", "riscos",
               "desfechos", "causas cardiovasculares"]


def simple_snake(s):
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


def strip_terms(s):
    s = s.lower()
    for ph in STRIP_PHRASES:
        s = s.replace(ph, " ")
    toks = [t for t in re.split(r"[^a-z0-9]+", s) if t and t not in STRIP_WORDS]
    return "_".join(toks)


def canonicalize(raw):
    low = raw.lower()
    for triggers, canon in CANON:
        for t in triggers:
            if t in low:
                return canon, "matched:" + t
    # no canonical match -> best-effort stripped fallback
    fb = strip_terms(raw)
    return (fb or simple_snake(raw)), "fallback_stripped"


def main():
    df = pd.read_csv(SRC)
    norm, note, changed, prio = [], [], [], []

    for raw in df["biomarker_name"].astype(str):
        canon, how = canonicalize(raw)
        sm = simple_snake(raw)
        is_changed = canon != sm
        notes = []
        priority = "none"

        if is_changed:
            notes.append(how)
            priority = "low"
        if raw in GARBAGE:
            notes.append("EXTRACTION_GARBAGE: no clear clinical term")
            priority = "high"
        if raw in AMBIGUOUS:
            notes.append("AMBIGUOUS: multiple candidate terms / negation")
            priority = "high"
        if any(k in raw.lower() for k in NON_ENGLISH):
            notes.append("NON_ENGLISH: mapped from es/pt phrasing")
            priority = "high"
        if how == "fallback_stripped" and is_changed:
            notes.append("NO_CANONICAL_MATCH: kept stripped term, verify")
            priority = "high"

        norm.append(canon)
        changed.append(is_changed)
        prio.append(priority)
        note.append("; ".join(notes) if notes else "formatting_only")

    df["biomarker_name_normalized"] = norm
    df["contrast_type_normalized"] = df["contrast_type"].map(simple_snake)
    df["name_changed"] = changed
    df["review_priority"] = prio
    df["normalization_note"] = note

    # apply the agreed drops (keyed on raw name) before writing the file
    n_before = len(df)
    df = df[~df["biomarker_name"].isin(DROP_RAW)].copy()
    print(f"dropped {n_before - len(df)} rows in DROP_RAW")

    # standardized name schema: biomarker_name_raw (input strata name) +
    # biomarker_name (snake_case canonical join key).
    df = df.rename(columns={"biomarker_name": "biomarker_name_raw",
                            "biomarker_name_normalized": "biomarker_name"})
    cols = list(df.columns)
    front = ["biomarker_name_raw", "biomarker_name", "contrast_type",
             "contrast_type_normalized", "name_changed", "review_priority",
             "normalization_note"]
    rest = [c for c in cols if c not in front]
    df = df[front + rest]
    df.to_csv(OUT, index=False)

    # ---- report ----
    n = len(df)
    print(f"strata rows: {n}")
    print(f"core term changed: {int(df['name_changed'].sum())} "
          f"(formatting-only: {n - int(df['name_changed'].sum())})")
    print(f"distinct canonical names: {df['biomarker_name'].nunique()} "
          f"(was {df['biomarker_name_raw'].nunique()})")
    print("review_priority:", dict(df["review_priority"].value_counts()))
    print(f"contrast_type_normalized unchanged: "
          f"{(df['contrast_type_normalized']==df['contrast_type']).all()}")

    print("\n=== HIGH-priority review rows ===")
    hi = df[df["review_priority"] == "high"][
        ["biomarker_name_raw", "biomarker_name", "normalization_note"]]
    for _, r in hi.iterrows():
        print(f"  {r['biomarker_name_raw'][:38]:39} -> {r['biomarker_name']:30} | {r['normalization_note']}")

    print("\n=== merges (canonical names now covering >1 raw name) ===")
    g = (df.groupby("biomarker_name")["biomarker_name_raw"]
         .nunique().sort_values(ascending=False))
    for nm, cnt in g[g > 1].items():
        raws = sorted(df[df["biomarker_name"] == nm]["biomarker_name_raw"].unique())
        print(f"  {nm} ({cnt}): {raws}")


if __name__ == "__main__":
    main()
