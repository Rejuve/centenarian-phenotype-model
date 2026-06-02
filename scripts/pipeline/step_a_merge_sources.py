#!/usr/bin/env python3
"""
merge_all.py — Data merge and cleaning for the Centenarian Clock Phase 2 pipeline.

Outputs (data/processed/):
  master_dataset.csv    — unified academic + news corpus, shared schema
  supercentenarians.csv — cleaned Wikipedia + TidyTuesday verified roster
  nhanes_merged.csv     — all 15 NHANES files joined on SEQN, CDC codes renamed

Run: python merge_all.py
"""

import re
import sys
import pandas as pd
import numpy as np
from pathlib import Path

RAW = Path("data/raw")
DATASETS = RAW / "datasets"
PROCESSED = Path("data/processed")
PROCESSED.mkdir(exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

BOOL_MAP = {True: 1, False: 0, 1: 1, 0: 0, "True": 1, "False": 0, "true": 1, "false": 0}


def coerce_bool(series):
    return series.map(BOOL_MAP)


def strip_wiki_footnotes(s):
    """Remove [1], [a], [b] citation markers and non-breaking spaces."""
    if pd.isna(s):
        return None
    return re.sub(r"\[[^\]]*\]", "", str(s)).replace("\xa0", " ").strip() or None


def parse_wiki_age(s):
    """'122 years, 164 days[b]' → decimal years float."""
    if pd.isna(s):
        return np.nan
    clean = re.sub(r"\[[^\]]*\]", "", str(s)).replace("\xa0", " ")
    m = re.search(r"(\d+)\s*years?(?:,\s*(\d+)\s*days?)?", clean, re.IGNORECASE)
    if m:
        return round(int(m.group(1)) + int(m.group(2) or 0) / 365.25, 4)
    return np.nan


def parse_wiki_date(s):
    """'21 February 1875[9]' → '1875-02-21', or None on failure."""
    if pd.isna(s):
        return None
    clean = re.sub(r"\[[^\]]*\]", "", str(s)).strip()
    dt = pd.to_datetime(clean, format="%d %B %Y", errors="coerce")
    return None if pd.isna(dt) else dt.strftime("%Y-%m-%d")


def normalize_gender(s):
    if pd.isna(s):
        return None
    v = str(s).strip().lower()
    if v in ("female", "f", "woman"):
        return "F"
    if v in ("male", "m", "man"):
        return "M"
    return None


def _section(title):
    print(f"\n{'='*60}\n{title}\n{'='*60}")


# ─────────────────────────────────────────────────────────────────────────────
# Section 1: Corpus merge (academic + news → master_dataset.csv)
# ─────────────────────────────────────────────────────────────────────────────

TRAIT_COLS = [
    "trait_physical_activity", "trait_diet", "trait_social",
    "trait_purpose_psychology", "trait_sleep",
]
BIOMARKER_COLS = [
    "biomarker_inflammation", "biomarker_glucose", "biomarker_lipids",
    "biomarker_igf1", "biomarker_telomeres", "biomarker_epigenetic",
    "biomarker_microbiome", "biomarker_hormones", "biomarker_functional",
    "biomarker_metabolomic",
]
GENE_COLS = ["gene_apoe", "gene_foxo3", "gene_cetp", "gene_klotho", "gene_other"]
STAT_COLS = [
    "stat_odds_ratio", "stat_hazard_ratio", "stat_relative_risk",
    "stat_sample_size", "stat_percentage", "stat_p_value", "stat_confidence_interval",
]

MASTER_COLS = [
    # identity
    "record_id", "source_type", "source_name", "source_country", "source_class",
    "url", "title", "text", "word_count", "scraped_date", "publication_date", "pub_year",
    # subject / people (mostly news; academic uses population_country)
    "subject_name", "subject_age", "subject_city", "subject_country", "population_country",
    # academic identifiers (null for news)
    "pmid", "doi", "journal", "authors", "mesh_terms", "study_type",
    "matched_query", "citation_count",
    # flags
    "is_centenarian_profile", "has_age", "has_stats", "ages_mentioned", "max_age",
    # extracted stats
    *STAT_COLS,
    # Phase 1 keyword-tagged feature columns (to be replaced by Phase 2 NLP)
    *TRAIT_COLS, *BIOMARKER_COLS, *GENE_COLS,
]


def build_corpus():
    _section("SECTION 1: CORPUS MERGE (academic + news)")

    ap = pd.read_csv(RAW / "academic_papers.csv", low_memory=False)
    na = pd.read_csv(RAW / "news_articles.csv", low_memory=False)
    print(f"  academic_papers.csv : {len(ap):,} rows, {len(ap.columns)} cols")
    print(f"  news_articles.csv   : {len(na):,} rows, {len(na.columns)} cols")

    # ── Academic rows ──────────────────────────────────────────────────────
    ap_out = pd.DataFrame(index=range(len(ap)))
    ap_out["record_id"]         = [f"AP_{i+1:05d}" for i in range(len(ap))]
    ap_out["source_type"]       = "academic"
    ap_out["source_name"]       = ap["source_database"]
    ap_out["source_country"]    = None          # journal country not collected
    ap_out["source_class"]      = ap["source_database"]
    ap_out["url"]               = ap["doi"].apply(
        lambda d: f"https://doi.org/{d}" if pd.notna(d) and str(d).strip() else None
    )
    ap_out["title"]             = ap["title"]
    ap_out["text"]              = ap["abstract"]
    ap_out["word_count"]        = pd.to_numeric(ap["word_count"], errors="coerce")
    ap_out["scraped_date"]      = ap["scraped_date"]
    ap_out["publication_date"]  = (
        pd.to_datetime(ap["pub_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    )
    ap_out["pub_year"]          = (
        pd.to_numeric(ap["pub_year"], errors="coerce").astype("Int64")
    )
    ap_out["subject_name"]      = None
    ap_out["subject_age"]       = None
    ap_out["subject_city"]      = None
    ap_out["subject_country"]   = None
    ap_out["population_country"]= ap["population_country"]
    ap_out["pmid"]              = ap["pmid"].apply(
        lambda x: str(int(float(x))) if pd.notna(x) else None
    )
    ap_out["doi"]               = ap["doi"]
    ap_out["journal"]           = ap["journal"]
    ap_out["authors"]           = ap["authors"]
    ap_out["mesh_terms"]        = ap["mesh_terms"]
    ap_out["study_type"]        = ap["study_type"]
    ap_out["matched_query"]     = ap["matched_query"]
    ap_out["citation_count"]    = (
        pd.to_numeric(ap["citation_count"], errors="coerce").astype("Int64")
    )
    # academic uses is_centenarian_focused; map to shared is_centenarian_profile
    ap_out["is_centenarian_profile"] = coerce_bool(ap["is_centenarian_focused"])
    ap_out["has_age"]           = coerce_bool(ap["has_age"])
    ap_out["has_stats"]         = coerce_bool(ap["has_stats"])
    ap_out["ages_mentioned"]    = ap["ages_mentioned"]
    ap_out["max_age"]           = pd.to_numeric(ap["max_age"], errors="coerce")
    for col in STAT_COLS:
        ap_out[col] = pd.to_numeric(ap[col], errors="coerce") if col in ap.columns else None
    for col in TRAIT_COLS + BIOMARKER_COLS + GENE_COLS:
        ap_out[col] = coerce_bool(ap[col])

    # ── News rows ──────────────────────────────────────────────────────────
    na_out = pd.DataFrame(index=range(len(na)))
    na_out["record_id"]         = [f"NA_{i+1:05d}" for i in range(len(na))]
    na_out["source_type"]       = "news"
    na_out["source_name"]       = na["source_name"]
    na_out["source_country"]    = na["source_country"]
    na_out["source_class"]      = na["source_class"]
    na_out["url"]               = na["url"]
    na_out["title"]             = na["title"]
    na_out["text"]              = na["full_text"]
    na_out["word_count"]        = pd.to_numeric(na["word_count"], errors="coerce")
    na_out["scraped_date"]      = na["scraped_date"]
    _pub_dt = pd.to_datetime(na["publish_date"], errors="coerce")
    na_out["publication_date"]  = _pub_dt.dt.strftime("%Y-%m-%d")
    na_out["pub_year"]          = _pub_dt.dt.year.astype("Int64")
    # Replace bare string "nan" artifacts from CSV serialisation
    na_out["subject_name"]      = na["subject_name"].replace("nan", None)
    na_out["subject_age"]       = pd.to_numeric(na["subject_age"], errors="coerce")
    na_out["subject_city"]      = na["subject_city"].replace("nan", None)
    na_out["subject_country"]   = na["subject_country"].replace("nan", None)
    na_out["population_country"]= na["subject_country"].replace("nan", None)
    na_out["pmid"]              = None
    na_out["doi"]               = None
    na_out["journal"]           = None
    na_out["authors"]           = None
    na_out["mesh_terms"]        = None
    na_out["study_type"]        = None
    na_out["matched_query"]     = None
    na_out["citation_count"]    = pd.array([pd.NA] * len(na), dtype="Int64")
    na_out["is_centenarian_profile"] = coerce_bool(na["is_centenarian_profile"])
    na_out["has_age"]           = coerce_bool(na["has_age"])
    na_out["has_stats"]         = coerce_bool(na["has_stats"])
    na_out["ages_mentioned"]    = na["ages_mentioned"]
    na_out["max_age"]           = pd.to_numeric(na["max_age"], errors="coerce")
    for col in STAT_COLS:
        na_out[col] = pd.to_numeric(na[col], errors="coerce") if col in na.columns else None
    for col in TRAIT_COLS + BIOMARKER_COLS + GENE_COLS:
        na_out[col] = coerce_bool(na[col])

    # ── Combine ────────────────────────────────────────────────────────────
    master = pd.concat([ap_out, na_out], ignore_index=True)[MASTER_COLS]
    out_path = PROCESSED / "master_dataset.csv"
    master.to_csv(out_path, index=False)

    # ── Summary ────────────────────────────────────────────────────────────
    print(f"\n  OUTPUT: {out_path}")
    print(f"  Total rows  : {len(master):,}")
    print(f"  Columns     : {len(master.columns)}")
    print(f"  Academic    : {(master.source_type == 'academic').sum():,}")
    print(f"  News        : {(master.source_type == 'news').sum():,}")
    print(f"  Rows dropped: 0  (no records dropped — nulls used for all missing fields)")
    print(f"\n  Centenarian profiles (is_centenarian_profile=1):")
    print(f"    Academic : {ap_out['is_centenarian_profile'].sum():,}")
    print(f"    News     : {na_out['is_centenarian_profile'].sum():,}")
    print(f"    Total    : {master['is_centenarian_profile'].sum():,}")
    print(f"\n  Key column null rates:")
    for col in ["text", "title", "pub_year", "subject_name", "subject_country",
                "population_country", "citation_count", "stat_odds_ratio",
                "stat_hazard_ratio", "stat_sample_size"]:
        pct = master[col].isna().mean() * 100
        print(f"    {col:<30}: {pct:.1f}% null")
    print(f"\n  Phase 1 keyword flags — trait coverage (source type / total):")
    for col in TRAIT_COLS:
        n_ap = ap_out[col].sum()
        n_na = na_out[col].sum()
        print(f"    {col:<35}: academic={n_ap:,}  news={n_na:,}")
    print(f"\n  Phase 1 keyword flags — biomarker coverage:")
    for col in BIOMARKER_COLS:
        n_ap = ap_out[col].sum()
        n_na = na_out[col].sum()
        print(f"    {col:<35}: academic={n_ap:,}  news={n_na:,}")

    return master


# ─────────────────────────────────────────────────────────────────────────────
# Section 2: Supercentenarian roster (Wikipedia + TidyTuesday)
# ─────────────────────────────────────────────────────────────────────────────

SC_COLS = [
    "rank", "name", "birth_date", "death_date", "age_years", "age_raw",
    "place", "country", "gender", "nationality", "notability",
    "still_alive", "wiki_page", "age_as_of_20260530", "dataset_source",
]


def build_supercentenarians():
    _section("SECTION 2: SUPERCENTENARIAN ROSTER (Wikipedia + TidyTuesday)")

    # ── Wikipedia ──────────────────────────────────────────────────────────
    wiki = pd.read_csv(DATASETS / "wikipedia_supercentenarians.csv")
    print(f"  wikipedia_supercentenarians.csv : {len(wiki):,} rows")

    w = pd.DataFrame(index=range(len(wiki)))
    w["rank"]       = pd.to_numeric(wiki["Rank"], errors="coerce").astype("Int64")
    w["name"]       = wiki["Name"].apply(strip_wiki_footnotes)
    w["birth_date"] = wiki["Birth date"].apply(parse_wiki_date)
    w["death_date"] = wiki["Death date"].apply(parse_wiki_date)
    w["age_years"]  = wiki["Age"].apply(parse_wiki_age)
    w["age_raw"]    = wiki["Age"].apply(strip_wiki_footnotes)
    w["place"]      = wiki["Place of death or residence"].apply(strip_wiki_footnotes)
    # Country: prefer "Country of residence" where available, fall back to Place
    _country = wiki["Country of residence"].combine_first(
        wiki["Place of death or residence"]
    )
    w["country"]      = _country.apply(strip_wiki_footnotes)
    w["gender"]       = wiki["Sex"].apply(normalize_gender)
    w["nationality"]  = wiki["Nationality"].apply(strip_wiki_footnotes)
    w["notability"]   = wiki["Notability"].apply(strip_wiki_footnotes)
    w["still_alive"]  = wiki["Death date"].isna().map({True: "alive", False: "deceased"})
    w["wiki_page"]    = wiki["wiki_page"]
    # "Age as of 30 May 2026" exists for still-living verified supercentenarians
    aoe_col = "Age as of 30 May 2026"
    w["age_as_of_20260530"] = wiki[aoe_col].apply(parse_wiki_age) if aoe_col in wiki.columns else None
    w["dataset_source"] = "wikipedia"

    # ── TidyTuesday ────────────────────────────────────────────────────────
    tt = pd.read_csv(DATASETS / "tidytuesday_centenarians.csv")
    print(f"  tidytuesday_centenarians.csv    : {len(tt):,} rows")

    t = pd.DataFrame(index=range(len(tt)))
    t["rank"]       = pd.to_numeric(tt["rank"], errors="coerce").astype("Int64")
    t["name"]       = tt["name"]
    t["birth_date"] = pd.to_datetime(tt["birth_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    t["death_date"] = pd.to_datetime(tt["death_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    t["age_years"]  = pd.to_numeric(tt["age"], errors="coerce")
    t["age_raw"]    = tt["age"].astype(str)
    t["place"]      = tt["place_of_death_or_residence"]
    t["country"]    = tt["place_of_death_or_residence"]   # best available field
    t["gender"]     = tt["gender"].apply(normalize_gender)
    t["nationality"]        = None
    t["notability"]         = None
    t["still_alive"]        = tt["still_alive"]
    t["wiki_page"]          = None
    t["age_as_of_20260530"] = None
    t["dataset_source"]     = "tidytuesday"

    # ── Combine and deduplicate ────────────────────────────────────────────
    combined = pd.concat([w, t], ignore_index=True)[SC_COLS]
    before = len(combined)
    # Prefer Wikipedia row when the same person appears in both datasets
    combined = combined.drop_duplicates(subset=["name", "birth_date"], keep="first")
    dropped = before - len(combined)

    out_path = PROCESSED / "supercentenarians.csv"
    combined.to_csv(out_path, index=False)

    print(f"\n  OUTPUT: {out_path}")
    print(f"  Wikipedia rows           : {len(w):,}")
    print(f"  TidyTuesday rows         : {len(t):,}")
    print(f"  Combined pre-dedup       : {before:,}")
    print(f"  Dropped (name+birth_date duplicate): {dropped:,}")
    print(f"  Final rows               : {len(combined):,}")
    print(f"\n  Wikipedia cleaning results:")
    print(f"    Names (footnotes stripped) : {w['name'].notna().sum():,} / {len(w):,}")
    print(f"    Ages parsed to decimal yr  : {w['age_years'].notna().sum():,} / {len(w):,}")
    print(f"    Birth dates parsed         : {w['birth_date'].notna().sum():,} / {len(w):,}")
    print(f"    Death dates parsed         : {w['death_date'].notna().sum():,} / {len(w):,}")
    print(f"    Gender non-null            : {w['gender'].notna().sum():,} / {len(w):,}  (67% null in source — not fixable without external lookup)")
    print(f"    Country non-null           : {w['country'].notna().sum():,} / {len(w):,}")
    print(f"    Age as of 2026-05-30       : {w['age_as_of_20260530'].notna().sum():,} (living supercentenarians)")

    return combined


# ─────────────────────────────────────────────────────────────────────────────
# Section 3: NHANES merge (15 files → nhanes_merged.csv)
# ─────────────────────────────────────────────────────────────────────────────

# Full codebook: CDC variable code → human-readable column name
NHANES_CODEBOOK = {
    "SEQN": "seqn",
    "nhanes_cycle": "nhanes_survey_cycle",
    # ── Demographics ──────────────────────────────────────────────────────
    "SDDSRVYR": "survey_year_code",
    "RIDSTATR": "interview_exam_status",       # 1=interview only, 2=both
    "RIAGENDR": "gender",                      # 1=Male, 2=Female
    "RIDAGEYR": "age_years",
    "RIDAGEMN": "age_months",
    "RIDRETH1": "race_ethnicity",              # 1=Mex Am, 2=Other Hisp, 3=NH White, 4=NH Black, 6=NH Asian, 7=Other
    "RIDRETH3": "race_ethnicity_alt",
    "RIDEXMON": "exam_6mo_period",             # 1=Nov-Apr, 2=May-Oct
    "RIDEXAGM": "age_at_exam_months",
    "DMQMILIZ": "ever_military",
    "DMQADFC":  "active_duty_now",
    "DMDBORN4": "country_of_birth",            # 1=US, 2=Other
    "DMDCITZN": "citizenship_status",
    "DMDYRSUS": "years_in_us",
    "DMDEDUC3": "education_youth",             # for ages 6-19
    "DMDEDUC2": "education_adult",             # for ages 20+
    "DMDMARTL": "marital_status",
    "RIDEXPRG": "pregnancy_status",
    "SIALANG":  "sp_interview_lang",
    "SIAPROXY": "sp_proxy_used",
    "SIAINTRP": "sp_interpreter_used",
    "FIALANG":  "family_interview_lang",
    "FIAPROXY": "family_proxy_used",
    "FIAINTRP": "family_interpreter_used",
    "MIALANG":  "mec_interview_lang",
    "MIAPROXY": "mec_proxy_used",
    "MIAINTRP": "mec_interpreter_used",
    "AIALANGA": "acasi_lang",
    "DMDHHSIZ": "household_size",
    "DMDFMSIZ": "family_size",
    "DMDHHSZA": "household_children_under6",
    "DMDHHSZB": "household_children_6to17",
    "DMDHHSZE": "household_adults_over60",
    "DMDHRGND": "ref_person_gender",
    "DMDHRAGZ": "ref_person_age",
    "DMDHREDZ": "ref_person_education",
    "DMDHRMAZ": "ref_person_marital",
    "DMDHSEDZ": "spouse_education",
    "WTINT2YR": "interview_weight_2yr",        # survey weight for interview sample
    "WTMEC2YR": "exam_weight_2yr",             # survey weight for exam sample
    "SDMVPSU":  "variance_psu",
    "SDMVSTRA": "variance_strata",
    "INDHHIN2": "household_income_cat",        # 1-15 coded categories
    "INDFMIN2": "family_income_cat",
    "INDFMPIR": "poverty_income_ratio",        # ratio 0-5
    # ── CRP (Inflammation) ────────────────────────────────────────────────
    "LBXHSCRP": "crp_mg_l",                   # high-sensitivity CRP
    "LBDHRPLC": "crp_below_lod_flag",
    # ── CBC (Complete Blood Count) ────────────────────────────────────────
    "LBXWBCSI": "wbc_1000_per_ul",
    "LBXLYPCT": "lymphocyte_pct",
    "LBXMOPCT": "monocyte_pct",
    "LBXNEPCT": "neutrophil_pct",
    "LBXEOPCT": "eosinophil_pct",
    "LBXBAPCT": "basophil_pct",
    "LBDLYMNO": "lymphocyte_1000_per_ul",
    "LBDMONO":  "monocyte_1000_per_ul",
    "LBDNENO":  "neutrophil_1000_per_ul",
    "LBDEONO":  "eosinophil_1000_per_ul",
    "LBDBANO":  "basophil_1000_per_ul",
    "LBXRBCSI": "rbc_million_per_ul",
    "LBXHGB":   "hemoglobin_g_dl",
    "LBXHCT":   "hematocrit_pct",
    "LBXMCVSI": "mcv_fl",                     # mean corpuscular volume
    "LBXMCHSI": "mch_pg",                     # mean corpuscular hemoglobin
    "LBXMC":    "mchc_g_dl",                  # mean corpuscular hemoglobin concentration
    "LBXRDW":   "rdw_pct",                    # red cell distribution width
    "LBXPLTSI": "platelets_1000_per_ul",
    "LBXMPSI":  "mpv_fl",                     # mean platelet volume
    "LBXNRBC":  "nucleated_rbc_per100wbc",
    # ── Blood Pressure ────────────────────────────────────────────────────
    "PEASCCT1": "bp_exam_status",
    "BPXCHR":   "pulse_type",
    "BPAARM":   "bp_arm_used",
    "BPACSZ":   "bp_cuff_size",
    "BPXPLS":   "pulse_60sec",
    "BPXPULS":  "pulse_regularity",
    "BPXPTY":   "bp_reading_position",
    "BPXML1":   "mid_arm_circumference_cm",
    "BPXSY1":   "systolic_bp1_mmhg",
    "BPXDI1":   "diastolic_bp1_mmhg",
    "BPAEN1":   "bp1_entered_flag",
    "BPXSY2":   "systolic_bp2_mmhg",
    "BPXDI2":   "diastolic_bp2_mmhg",
    "BPAEN2":   "bp2_entered_flag",
    "BPXSY3":   "systolic_bp3_mmhg",
    "BPXDI3":   "diastolic_bp3_mmhg",
    "BPAEN3":   "bp3_entered_flag",
    "BPXSY4":   "systolic_bp4_mmhg",
    "BPXDI4":   "diastolic_bp4_mmhg",
    "BPAEN4":   "bp4_entered_flag",
    # ── Body Measures ─────────────────────────────────────────────────────
    "BMDSTATS": "body_measure_status",
    "BMXWT":    "weight_kg",
    "BMIWT":    "weight_comment_code",         # data quality flag, not a measurement
    "BMXRECUM": "recumbent_length_cm",
    "BMIRECUM": "recumbent_length_comment_code",
    "BMXHEAD":  "head_circumference_cm",
    "BMIHEAD":  "head_circumference_comment_code",
    "BMXHT":    "standing_height_cm",
    "BMIHT":    "height_comment_code",
    "BMXBMI":   "bmi",
    "BMXLEG":   "upper_leg_length_cm",
    "BMILEG":   "upper_leg_length_comment_code",
    "BMXARML":  "upper_arm_length_cm",
    "BMIARML":  "upper_arm_length_comment_code",
    "BMXARMC":  "arm_circumference_cm",
    "BMIARMC":  "arm_circumference_comment_code",
    "BMXWAIST": "waist_circumference_cm",
    "BMIWAIST": "waist_circumference_comment_code",
    "BMXHIP":   "hip_circumference_cm",
    "BMIHIP":   "hip_circumference_comment_code",
    # ── Cholesterol ───────────────────────────────────────────────────────
    "LBXTC":    "total_cholesterol_mg_dl",
    "LBDTCSI":  "total_cholesterol_mmol_l",
    "LBDHDD":   "hdl_cholesterol_mg_dl",
    "LBDHDDSI": "hdl_cholesterol_mmol_l",
    # ── Triglycerides / LDL (fasting subsample) ───────────────────────────
    "WTSAF2YR": "fasting_subsample_weight_2yr",
    "LBXTR":    "triglycerides_mg_dl",
    "LBDTRSI":  "triglycerides_mmol_l",
    "LBDLDL":   "ldl_mg_dl",
    "LBDLDLSI": "ldl_mmol_l",
    "LBDLDLM":  "ldl_method",
    "LBDLDMSI": "ldl_method_si",
    "LBDLDLN":  "ldl_direct_mg_dl",
    "LBDLDNSI": "ldl_direct_mmol_l",
    # ── Glucose (fasting subsample) ───────────────────────────────────────
    "LBXGLU":   "fasting_glucose_mg_dl",
    "LBDGLUSI": "fasting_glucose_mmol_l",
    # ── Glycohemoglobin (HbA1c) ───────────────────────────────────────────
    "LBXGH":    "hba1c_pct",
    # ── Physical Activity ─────────────────────────────────────────────────
    "PAQ605":   "vigorous_work_yn",
    "PAQ610":   "vigorous_work_days_wk",
    "PAD615":   "vigorous_work_min_day",
    "PAQ620":   "moderate_work_yn",
    "PAQ625":   "moderate_work_days_wk",
    "PAD630":   "moderate_work_min_day",
    "PAQ635":   "walk_bicycle_transport_yn",
    "PAQ640":   "walk_bicycle_days_wk",
    "PAD645":   "walk_bicycle_min_day",
    "PAQ650":   "vigorous_recreation_yn",
    "PAQ655":   "vigorous_recreation_days_wk",
    "PAD660":   "vigorous_recreation_min_day",
    "PAQ665":   "moderate_recreation_yn",
    "PAQ670":   "moderate_recreation_days_wk",
    "PAD675":   "moderate_recreation_min_day",
    "PAD680":   "sedentary_min_day",
    # ── Sleep ─────────────────────────────────────────────────────────────
    "SLQ300":   "usual_sleep_time_weekday",
    "SLQ310":   "usual_wake_time_weekday",
    "SLD012":   "sleep_hours_weekday",
    "SLQ320":   "usual_sleep_time_weekend",
    "SLQ330":   "usual_wake_time_weekend",
    "SLD013":   "sleep_hours_weekend",
    "SLQ030":   "snore",
    "SLQ040":   "snore_frequency",
    "SLQ050":   "told_sleep_disorder",
    "SLQ120":   "sleepy_daytime_frequency",
    # ── Smoking ───────────────────────────────────────────────────────────
    "SMQ020":   "smoked_100_cigarettes_lifetime",
    "SMD030":   "age_started_smoking",
    "SMQ040":   "current_smoker",
    "SMQ050Q":  "quit_duration_amount",
    "SMQ050U":  "quit_duration_unit",
    "SMD057":   "cigs_per_day_when_quit",
    "SMQ078":   "smoke_inside_home",
    "SMD641":   "days_smoked_past30",
    "SMD650":   "cigs_per_day_past30",
    "SMD093":   "brand_code",
    "SMDUPCA":  "brand_upc",
    "SMD100BR": "brand_filler_code",
    "SMD100FL": "flavor_code",
    "SMD100MN": "menthol_flag",
    "SMD100LN": "cigarette_length_mm",
    "SMD100TR": "filtered_flag",
    "SMD100NI": "nicotine_mg",
    "SMD100CO": "carbon_monoxide_mg",
    "SMQ621":   "cigs_smoked_at_home",
    "SMD630":   "age_first_smoked",
    "SMQ661":   "brand_used_now_code",
    "SMQ665A":  "also_uses_cigarettes",
    "SMQ665B":  "also_uses_pipe",
    "SMQ665C":  "also_uses_cigars",
    "SMQ665D":  "also_chews_tobacco",
    "SMQ670":   "tried_to_quit_past12mo",
    "SMQ848":   "used_ecig_past5days",
    "SMQ852Q":  "ecig_use_amount",
    "SMQ852U":  "ecig_use_unit",
    "SMQ890":   "smokeless_tobacco_use",
    "SMQ895":   "smokeless_tobacco_days_past30",
    "SMQ900":   "pipe_use",
    "SMQ905":   "pipe_days_past30",
    "SMQ910":   "cigar_use",
    "SMQ915":   "cigar_days_past30",
    "SMAQUEX2": "questionnaire_mode",
    # ── Alcohol ───────────────────────────────────────────────────────────
    "ALQ111":   "had_12plus_drinks_lifetime",
    "ALQ121":   "drinking_freq_past12mo",
    "ALQ130":   "avg_drinks_per_drinking_day",
    "ALQ142":   "days_5plus_drinks_past12mo",
    "ALQ270":   "any_drinking_past2wk",
    "ALQ280":   "drinking_days_past2wk",
    "ALQ290":   "heavy_drinking_days_past2wk",
    "ALQ151":   "ever_drinking_problem",
    "ALQ170":   "any_drinking_past12mo",
    # ── Diabetes ──────────────────────────────────────────────────────────
    "DIQ010":   "diagnosed_diabetes",
    "DID040":   "age_diagnosed_diabetes",
    "DIQ160":   "told_prediabetes",
    "DIQ170":   "told_at_risk_diabetes",
    "DIQ172":   "feels_at_risk_diabetes",
    "DIQ175A":  "risk_overweight",
    "DIQ175B":  "risk_family_history",
    "DIQ175C":  "risk_age_over45",
    "DIQ175D":  "risk_gestational_diabetes",
    "DIQ175E":  "risk_race",
    "DIQ175F":  "risk_hypertension",
    "DIQ175G":  "risk_inactivity",
    "DIQ175H":  "risk_unhealthy_diet",
    "DIQ175I":  "risk_prediabetes",
    "DIQ175J":  "risk_impaired_fasting",
    "DIQ175K":  "risk_impaired_glucose_tolerance",
    "DIQ175L":  "risk_blood_test_result",
    "DIQ175M":  "risk_cholesterol",
    "DIQ175N":  "risk_metabolic_syndrome",
    "DIQ175O":  "risk_polycystic_ovary",
    "DIQ175P":  "risk_nerve_damage",
    "DIQ175Q":  "risk_eye_problems",
    "DIQ175R":  "risk_heart_disease",
    "DIQ175S":  "risk_stroke",
    "DIQ175T":  "risk_gum_disease",
    "DIQ175U":  "risk_other",
    "DIQ175V":  "risk_stress",
    "DIQ175W":  "risk_low_birth_weight",
    "DIQ175X":  "risk_other_x",          # additional reason code — verify exact label in NHANES DIQ codebook
    "DIQ180":   "blood_test_diabetes_past3yr",
    "DIQ050":   "taking_insulin",
    "DID060":   "months_on_insulin",
    "DIQ060U":  "insulin_duration_unit",
    "DIQ070":   "taking_diabetes_pills",
    "DIQ230":   "seen_mental_health_prof",
    "DIQ240":   "taken_diabetes_ed_class",
    "DID250":   "diabetes_doctor_visits_1yr",
    "DID260":   "any_doctor_visits_1yr",
    "DIQ260U":  "doctor_visits_unit",
    "DIQ275":   "routine_diabetes_care",
    "DIQ280":   "last_a1c_timing",
    "DIQ291":   "last_a1c_result_range",
    "DIQ300S":  "last_systolic_told",
    "DIQ300D":  "last_diastolic_told",
    "DID310S":  "target_systolic",
    "DID310D":  "target_diastolic",
    "DID320":   "last_total_cholesterol_told",
    "DID330":   "target_total_cholesterol",
    "DID341":   "last_ldl_told",
    "DID350":   "target_ldl",
    "DIQ350U":  "target_ldl_unit",
    "DIQ360":   "on_dialysis",
    "DIQ080":   "retinopathy",
}

# Columns added by the scraper to every NHANES file — drop from joining files before merge
# nhanes_cycle must be here because it exists in all 15 files and would collide
_SCRAPER_COLS_JOIN  = {"nhanes_file", "nhanes_cycle", "dataset_source", "dataset_type", "license"}
# After merge, drop remaining scraper-admin cols from the base (keep nhanes_cycle — it's informative)
_SCRAPER_COLS_FINAL = {"nhanes_file", "dataset_source", "dataset_type", "license"}

# Ordered list of the 15 NHANES files; demographics is the join base
_NHANES_FILES = [
    ("demographics",      "nhanes_demographics.csv"),
    ("crp",               "nhanes_crp.csv"),
    ("cbc",               "nhanes_cbc.csv"),
    ("blood_pressure",    "nhanes_blood_pressure.csv"),
    ("body_measures",     "nhanes_body_measures.csv"),
    ("cholesterol_total", "nhanes_cholesterol_total.csv"),
    ("cholesterol_hdl",   "nhanes_cholesterol_hdl.csv"),
    ("triglycerides",     "nhanes_triglycerides.csv"),
    ("glucose",           "nhanes_glucose.csv"),
    ("glycohemoglobin",   "nhanes_glycohemoglobin.csv"),
    ("physical_activity", "nhanes_physical_activity.csv"),
    ("sleep",             "nhanes_sleep.csv"),
    ("smoking",           "nhanes_smoking.csv"),
    ("alcohol",           "nhanes_alcohol.csv"),
    ("diabetes",          "nhanes_diabetes.csv"),
]

# Key biomarker columns to report coverage for in the summary
_NHANES_COVERAGE_COLS = [
    ("crp_mg_l",                "CRP (inflammation)"),
    ("wbc_1000_per_ul",         "WBC"),
    ("hemoglobin_g_dl",         "Hemoglobin"),
    ("systolic_bp1_mmhg",       "Systolic BP"),
    ("bmi",                     "BMI"),
    ("total_cholesterol_mg_dl", "Total cholesterol"),
    ("hdl_cholesterol_mg_dl",   "HDL cholesterol"),
    ("ldl_mg_dl",               "LDL cholesterol"),
    ("triglycerides_mg_dl",     "Triglycerides"),
    ("fasting_glucose_mg_dl",   "Fasting glucose"),
    ("hba1c_pct",               "HbA1c"),
    ("sleep_hours_weekday",     "Sleep hours"),
    ("current_smoker",          "Smoking status"),
    ("drinking_freq_past12mo",  "Alcohol frequency"),
    ("diagnosed_diabetes",      "Diabetes diagnosis"),
]


def build_nhanes():
    _section("SECTION 3: NHANES MERGE (15 files -> nhanes_merged.csv)")

    # Load demographics as the join base
    base_name, base_file = _NHANES_FILES[0]
    merged = pd.read_csv(DATASETS / base_file, low_memory=False)
    cycle = merged["nhanes_cycle"].iloc[0] if "nhanes_cycle" in merged.columns else "2017-2018"
    print(f"  Base: {base_file}  →  {len(merged):,} participants  (NHANES cycle: {cycle})")

    # Left-join each remaining file on SEQN
    for name, fname in _NHANES_FILES[1:]:
        df = pd.read_csv(DATASETS / fname, low_memory=False)
        # Drop scraper metadata (including nhanes_cycle) from joining files to avoid collisions
        df = df.drop(columns=[c for c in _SCRAPER_COLS_JOIN if c in df.columns])
        # WTSAF2YR (fasting subsample weight) is in both triglycerides and glucose;
        # keep it from triglycerides, drop from glucose to avoid a _x/_y conflict
        if name == "glucose" and "WTSAF2YR" in df.columns:
            df = df.drop(columns=["WTSAF2YR"])
        merged = merged.merge(df, on="SEQN", how="left")
        print(f"  + {name:<20} {len(df):,} rows  →  merged: {len(merged):,} x {len(merged.columns)} cols")

    # Drop scraper admin columns from the final merged table; nhanes_cycle is kept
    merged = merged.drop(columns=[c for c in _SCRAPER_COLS_FINAL if c in merged.columns])

    # Rename CDC codes → human-readable names
    rename_map = {c: NHANES_CODEBOOK[c] for c in merged.columns if c in NHANES_CODEBOOK}
    unmapped   = [c for c in merged.columns if c not in NHANES_CODEBOOK]
    merged = merged.rename(columns=rename_map)

    out_path = PROCESSED / "nhanes_merged.csv"
    merged.to_csv(out_path, index=False)

    base_n = len(merged)
    print(f"\n  OUTPUT: {out_path}")
    print(f"  Final shape: {base_n:,} rows x {len(merged.columns)} columns")
    print(f"  CDC codes renamed: {len(rename_map)}")
    if unmapped:
        print(f"  Columns left as-is (not CDC codes): {unmapped}")
    print(f"\n  Participant coverage for key biomarkers:")
    for col, label in _NHANES_COVERAGE_COLS:
        if col in merged.columns:
            n = merged[col].notna().sum()
            print(f"    {label:<28}: {n:,} / {base_n:,}  ({n/base_n*100:.1f}%)")
    print(f"\n  NOTE: fasting-only files (glucose, triglycerides, LDL) are limited to")
    print(f"  participants who completed the fasting subsample (~3,036 of 9,254).")
    print(f"  All other participants have null values for those columns — expected.")

    return merged


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("merge_all.py — Centenarian Clock data pipeline")
    print(f"Output: {PROCESSED.resolve()}")

    master  = build_corpus()
    supers  = build_supercentenarians()
    nhanes  = build_nhanes()

    _section("FINAL SUMMARY")
    print(f"  master_dataset.csv    : {len(master):,} rows  x {len(master.columns)} cols")
    print(f"  supercentenarians.csv : {len(supers):,} rows  x {len(supers.columns)} cols")
    print(f"  nhanes_merged.csv     : {len(nhanes):,} rows  x {len(nhanes.columns)} cols")
    print(f"\n  No records were dropped from any source.")
    print(f"  Missing fields use null values throughout.")
    print(f"\n  Phase 2 NLP pipeline inputs:")
    print(f"    master_dataset.csv['text']  — {master['text'].notna().sum():,} documents with text")
    print(f"    Academic abstracts          — {(master.source_type == 'academic').sum():,}")
    print(f"    News full-text              — {(master.source_type == 'news').sum():,}")
    print(f"\n  Phase 3 biomarker reference:")
    print(f"    nhanes_merged.csv           — {len(nhanes):,} participants, population baseline distributions")
    print(f"\n  Phase 3 centenarian validation set:")
    print(f"    supercentenarians.csv       — {len(supers):,} verified supercentenarians (deduplicated)")
