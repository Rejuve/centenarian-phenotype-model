"""
Data-first biomarker extraction from the academic-paper corpus.

Approach:
  1. Filter master_dataset.csv to academic papers where:
        is_centenarian_profile == 1
     OR (has_stats == 1 AND any biomarker_* == 1)
  2. For every row's text, find every number-with-unit OR ratio pattern.
     For each match: walk back through tokens to find the closest noun
     phrase — that's the biomarker name (as it appears in text).
     Classify value_type by surrounding-text cues (mean, median, range,
     SD, OR, HR, CI).
  3. Tag each row with subject_class derived from ages_mentioned:
        nonagenarian   (90-99)
        centenarian    (100-109)
        supercentenarian (110+)
  4. Aggregate by normalized biomarker name (lowercased; common synonym
     collapses for hs-CRP/CRP, HDL-c/HDL, etc.). Count distinct PMIDs and
     countries.
  5. Cross-validate:
        in_nhanes  → biomarker keyword matches NHANES_FEATURE_MAP / nhanes_merged.csv columns
        in_gwas    → biomarker phrase matches a DISEASE/TRAIT in gwas_longevity.csv
  6. Assign evidence_grade:
        A = (n_sources>=3 AND n_countries>=2) AND (in_nhanes OR in_gwas)
        B = (n_sources>=3 AND n_countries>=2) AND NOT cross-validated
            OR (n_sources>=2 AND in_nhanes AND in_gwas)
        C = everything else (deliberately rare — flagged as exploratory)

Outputs:
  data/processed/centenarian_biomarker_reference.csv  (one row per extraction)
  data/processed/biomarker_summary.csv                 (one row per normalized biomarker)

Run: PYTHONIOENCODING=utf-8 python -u extract_biomarkers.py
"""
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd
import numpy as np

# Canonical biomarker-name helper (shared snake_case vocabulary used across all
# four biomarker files, so `biomarker_name` is a consistent cross-file join key).
from normalize_strata_names import canonicalize, simple_snake


def canonical_name(raw):
    """raw extracted/normalized name -> snake_case canonical join key."""
    canon, how = canonicalize(str(raw))
    return canon if how.startswith("matched") else simple_snake(str(raw))


PROC = Path("data/processed")
RAW  = Path("data/raw/datasets")
MASTER  = PROC / "master_dataset.csv"
NHANES  = PROC / "nhanes_merged.csv"
GWAS    = RAW  / "gwas_longevity.csv"
OUT_ROWS = PROC / "centenarian_biomarker_reference.csv"
OUT_SUM  = PROC / "biomarker_summary.csv"

# ─────────────────────────────────────────────────────────────────────────────
# Unit + value patterns
# ─────────────────────────────────────────────────────────────────────────────

# All units we expect to see in centenarian biomarker reports.
# Order matters — longer / more specific patterns first.
_UNIT_TOKENS = [
    "mg/dL", "mg/dl", "mg/L", "mg/l", "g/dL", "g/dl", "g/L", "g/l",
    "ng/mL", "ng/ml", "pg/mL", "pg/ml",
    "µg/mL", "ug/mL", "μg/mL", "ug/ml", "µg/ml", "μg/ml",
    "mmol/L", "mmol/l", "µmol/L", "umol/L", "μmol/L", "umol/l",
    "nmol/L", "nmol/l", "pmol/L", "pmol/l",
    "IU/L", "IU/l", "iu/L", "iu/l", "U/L", "U/l", "u/L", "u/l",
    "U/mL", "u/mL",
    "mmHg", "mmhg", "mm Hg",
    "kg/m²", "kg/m2", "kg m-2",
    "bpm", "beats/min",
    "fL", "fl",
    "g/dL", "g/L",
    "%", "percent",
    "×10⁹/L", "x10⁹/L", "10⁹/L", "x10^9/L", "10^9/L",
    "cells/mm³", "cells/mm3", "cells/µL", "cells/uL",
    # Functional / aerobic
    "mL/kg/min", "ml/kg/min", "mL/min/kg", "ml/min/kg",
    "mL/min", "ml/min", "L/min", "l/min",
    # Telomere length
    "kb", "bp",
    # Methylation / epigenetic age — usually unitless but reported "years"
    # variants already excluded; nothing to add.
    # NB: "years" is intentionally excluded — it captures ages, not biomarkers.
]
_UNIT_ALT = "|".join(re.escape(u) for u in sorted(set(_UNIT_TOKENS), key=len, reverse=True))

# Numeric value: 123, 1.5, 0.45 (optional thousands separator)
_NUM = r"\d{1,4}(?:,\d{3})*(?:\.\d+)?"

# Master pattern — captures:
#   value1, optional comparator (± / – / to / -), value2, optional unit
_VAL_RE = re.compile(
    rf"""
    \b
    (?P<v1>{_NUM})
    (?:
       \s*(?P<sep>±|\+/-|±|–|—|-|to|\s*-\s*)\s*
       (?P<v2>{_NUM})
    )?
    \s*
    (?P<unit>{_UNIT_ALT})?
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Odds / hazard / relative risk patterns (and their alt forms)
_RATIO_RE = re.compile(
    rf"""
    \b
    (?P<kind>OR|HR|RR|odds\s+ratio|hazard\s+ratio|relative\s+risk)
    \s*[=:]?\s*
    (?P<val>{_NUM})
    (?:
        \s*\(\s*
        (?:95\s*%\s*CI[:\s]*)?
        (?P<lo>{_NUM})\s*[-–—to,]+\s*(?P<hi>{_NUM})
        \s*\)
    )?
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Context keywords that disambiguate value_type
_KW_MEAN     = re.compile(r"\bmean\b|\baverage\b|\bavg\.?\b", re.I)
_KW_MEDIAN   = re.compile(r"\bmedian\b", re.I)
_KW_RANGE    = re.compile(r"\brange\b|\bIQR\b|interquartile", re.I)
_KW_CI       = re.compile(r"\b95\s*%?\s*CI\b|confidence interval", re.I)
_KW_SD       = re.compile(r"\bSD\b|\bstandard deviation\b|\bstdev\b", re.I)
_KW_SE       = re.compile(r"\bSE\b|standard error|\bSEM\b", re.I)
_KW_P_LO     = re.compile(r"\bp\s*[<≤]\s*0?\.\d+", re.I)

# Stopwords that disqualify a candidate biomarker name (too generic)
_NAME_STOPWORDS = {
    "year", "years", "age", "ages", "aged", "month", "months", "day", "days",
    "subject", "subjects", "patient", "patients", "participant", "participants",
    "control", "controls", "case", "cases", "group", "groups", "sample",
    "samples", "study", "studies", "result", "results", "individual",
    "individuals", "cohort", "cohorts", "data", "value", "values",
    "level", "levels", "score", "scores", "table", "figure", "abstract",
    "background", "method", "methods", "conclusion", "objective", "aim",
    "we", "the", "this", "that", "these", "those", "their", "his", "her",
    "of", "in", "to", "for", "with", "from", "by", "on", "at", "as",
    "between", "across", "among", "during", "after", "before", "within",
    "high", "low", "elevated", "reduced", "decreased", "increased",
    "higher", "lower", "greater", "lesser", "more", "less", "compared",
    "older", "younger", "old", "young", "above", "below", "least", "most",
    "first", "second", "third", "last", "next", "period", "baseline",
    "follow-up", "followup", "median", "mean", "average", "range", "iqr",
    "respectively", "overall", "general", "specific", "total", "subtotal",
    "study", "studies", "trial", "trials", "review", "n", "p",
    "association", "associated", "associations", "increase", "decrease",
    "risk", "risks", "rate", "rates", "ratio", "ratios", "percent",
    "factor", "factors", "marker", "markers", "test", "tests",
    "examination", "examinations", "measurement", "measurements",
    "adults", "adult", "elderly", "centenarian", "centenarians",
    "nonagenarian", "nonagenarians", "supercentenarian", "supercentenarians",
    "people", "person", "persons", "men", "women", "male", "female",
    "community", "community-dwelling", "hospital", "hospitalized",
    "baseline", "follow",
}

# A discovered name must include at least one biomedical-looking token to be
# considered a "real" biomarker. This is the data-first quality gate: it
# avoids surfacing generic clinical-trial vocabulary as fake biomarkers.
_BIOMED_TOKENS = {
    # Lipids
    "cholesterol", "ldl", "hdl", "vldl", "lipid", "lipids", "lipoprotein",
    "triglyceride", "triglycerides", "apolipoprotein", "apoa", "apob",
    # Glucose / metabolism
    "glucose", "insulin", "hba1c", "a1c", "glycated", "glycohemoglobin",
    "homa", "homa-ir", "homeostatic",
    # Inflammation
    "crp", "c-reactive", "interleukin", "il-6", "il-1", "il-10", "il-8",
    "tnf", "tnf-alpha", "tnfalpha", "cytokine", "cytokines", "ferritin",
    "inflammatory", "inflammation", "fibrinogen",
    # Blood cells
    "hemoglobin", "haemoglobin", "hematocrit", "platelet", "platelets",
    "leukocyte", "leukocytes", "lymphocyte", "lymphocytes",
    "neutrophil", "neutrophils", "monocyte", "monocytes", "eosinophil",
    "wbc", "rbc", "mcv", "mch", "mchc", "rdw",
    # Body composition / vitals
    "bmi", "mass", "weight", "height", "waist", "hip", "circumference",
    "systolic", "diastolic", "blood pressure", "pulse", "hr",
    "grip", "strength", "muscle", "lean", "fat", "adiposity",
    # Endocrine
    "igf", "igf-1", "igf1", "igfbp", "dhea", "dheas", "cortisol",
    "testosterone", "estrogen", "estradiol", "tsh", "t3", "t4",
    "thyroid", "growth hormone",
    # Kidney
    "creatinine", "egfr", "gfr", "albumin", "cystatin", "urea", "bun", "uric",
    # Liver
    "alt", "ast", "ggt", "bilirubin", "alp",
    # Bone
    "calcium", "phosphate", "vitamin", "25-oh", "25(oh)d",
    # Epigenetic
    "horvath", "phenoage", "grimage", "dunedinpace", "methylation",
    "epigenetic", "biological age",
    # Telomere / aging molecular
    "telomere", "telomerase", "klotho", "sirtuin", "nad", "nad+",
    "p21", "p16",
    # Genes already in the catalogue
    "apoe", "foxo3", "cetp",
    # Outcomes that are quantifiable
    "mortality", "longevity", "survival", "lifespan", "hazard",
    "incidence", "prevalence", "morbidity",
    # Diseases reported with ORs/HRs
    "hypertension", "diabetes", "stroke", "cancer", "dementia",
    "alzheimer", "alzheimer's", "frailty", "sarcopenia", "osteoporosis",
    "cardiovascular", "coronary", "myocardial",
    # Lab-style markers
    "marker", "biomarker", "panel", "score",
    # Microbiome
    "microbiome", "microbiota", "bacteroides", "firmicutes",
    "akkermansia", "bifidobacterium",
}


def _looks_like_biomarker(name):
    """Quality gate: a real biomarker name should contain at least one
    biomedical-looking token. Lets through known abbreviations + multi-word
    phrases with biomedical substrings; filters out generic clinical-trial
    vocabulary like 'older adults aged' or 'at baseline'."""
    if not name:
        return False
    nl = name.lower()
    # Cheap whole-name match (covers known abbreviations like "crp")
    if nl in _BIOMED_TOKENS or normalize_name(nl) in _BIOMED_TOKENS:
        return True
    # Token-level substring match (covers compounds like "hdl cholesterol")
    for tok in re.split(r"[\s\-/]+", nl):
        if tok in _BIOMED_TOKENS:
            return True
        # Substring fallback for compound tokens with hyphens / suffixes
        for bm in _BIOMED_TOKENS:
            if len(bm) >= 5 and bm in tok:
                return True
    return False

# Generic biomarker-name normalizer: collapse common synonyms.
_SYNONYMS = {
    # Inflammation
    "hs-crp":   "c-reactive protein",
    "hscrp":    "c-reactive protein",
    "crp":      "c-reactive protein",
    "hs crp":   "c-reactive protein",
    "il-6":     "interleukin-6",
    "il6":      "interleukin-6",
    "tnf-α":    "tnf-alpha",
    "tnfα":     "tnf-alpha",
    "tnf alpha":"tnf-alpha",
    # Lipids
    "hdl-c":    "hdl cholesterol",
    "hdl":      "hdl cholesterol",
    "ldl-c":    "ldl cholesterol",
    "ldl":      "ldl cholesterol",
    "tc":       "total cholesterol",
    "tg":       "triglycerides",
    "trigs":    "triglycerides",
    # Glucose
    "fbg":      "fasting glucose",
    "fpg":      "fasting glucose",
    "hba1c":    "hba1c",
    "a1c":      "hba1c",
    "glycated hemoglobin": "hba1c",
    "glycohemoglobin":     "hba1c",
    # Body
    "bmi":      "body mass index",
    "sbp":      "systolic blood pressure",
    "dbp":      "diastolic blood pressure",
    # Blood
    "wbc":      "white blood cell count",
    "rbc":      "red blood cell count",
    "hgb":      "hemoglobin",
    "hb":       "hemoglobin",
    "plt":      "platelets",
    # Kidney
    "egfr":     "estimated glomerular filtration rate",
    "gfr":      "glomerular filtration rate",
    "scr":      "serum creatinine",
    # Hormones / growth
    "igf-1":    "insulin-like growth factor 1",
    "igf1":     "insulin-like growth factor 1",
    "igfbp-3":  "igfbp-3",
    "dhea-s":   "dheas",
    "dheas":    "dheas",
    "tsh":      "thyroid stimulating hormone",
    "ft4":      "free t4",
    "ft3":      "free t3",
    # Aging clocks
    "horvath":      "horvath clock",
    "phenoage":     "phenoage",
    "grimage":      "grimage",
    "dunedinpace":  "dunedinpace",
    "biological age":"epigenetic biological age",
}


# Core biomarker substrings — if a phrase contains one of these, collapse the
# WHOLE phrase down to that core. This catches "shorter telomere length",
# "log telomere length", "lymphocyte telomere length" → "telomere length";
# "phenoage acceleration mediated", "phenoageaccel", "ferritin and phenoage
# acceleration" → "phenoage"; etc.
# Order matters — longer / more specific cores first.
_CORE_REDUCTIONS = [
    # Epigenetic clocks
    "horvath clock", "horvath",
    "phenoage", "grimage", "dunedinpace",
    "epigenetic age acceleration", "epigenetic age", "epigenetic clock",
    "dna methylation age", "methylation age",
    # Telomeres
    "telomere length", "leukocyte telomere", "telomere",
    "telomerase activity", "telomerase",
    # IGF / growth axis
    "igf-1", "igfbp-3", "insulin-like growth factor",
    "mtor", "rapamycin",
    # Cytokines
    "interleukin-6", "il-6", "il-1", "il-10",
    "tnf-alpha", "tumor necrosis factor",
    "inflammaging",
    # Kidney
    "estimated glomerular filtration rate", "egfr",
    "serum creatinine", "creatinine",
    "cystatin c", "cystatin",
    # Microbiome
    "gut microbiome", "microbiome", "microbiota diversity", "microbiota",
    # Nutrition
    "serum albumin", "albumin", "hypoalbuminemia",
    "25-hydroxyvitamin d", "vitamin d", "vitamin",
    # Functional
    "handgrip strength", "grip strength",
    "gait speed", "vo2 max", "vo2max",
    # Hormones
    "dheas", "dhea-s", "dhea", "dehydroepiandrosterone",
    "testosterone", "cortisol",
    "thyroid stimulating hormone", "tsh",
    "free t4", "free t3",
    "estradiol", "estrogen",
    # Body / vitals
    "body mass index", "bmi",
    "systolic blood pressure", "diastolic blood pressure", "blood pressure",
    "waist circumference",
    "hand grip strength",
    # Lipids
    "hdl cholesterol", "ldl cholesterol", "total cholesterol", "cholesterol",
    "triglycerides", "lipoprotein",
    # Glucose
    "fasting glucose", "hba1c", "glycated hemoglobin",
    # Blood cells
    "white blood cell", "red blood cell",
    "neutrophil", "lymphocyte", "monocyte", "platelet",
    "hemoglobin", "haemoglobin", "ferritin",
    # Inflammation
    "c-reactive protein", "crp", "fibrinogen",
]


def _apply_core_reduction(name):
    """If name contains a known biomarker core, return the core. Else None."""
    nl = name.lower()
    for core in _CORE_REDUCTIONS:
        if core in nl:
            return core
    return None


def normalize_name(raw):
    n = raw.strip().lower()
    n = re.sub(r"[\(\)\[\]]", "", n)
    n = re.sub(r"\s+", " ", n)
    n = n.strip(" .,;:")
    # Drop leading connectives ("and X" / "or X" / "with X")
    n = re.sub(r"^(and|or|with|of|in|for|by|to)\s+", "", n)
    # Drop trailing redundant abbreviation suffixes ("body mass index bmi" → "body mass index")
    n = re.sub(r"\s+(bmi|crp|hdl|ldl|sbp|dbp|hba1c|or|hr|rr)$", "", n)
    # Strip common qualifier prefixes that don't change the biomarker identity
    n = re.sub(
        r"^(had|has|have|is|was|were|are|been|"
        r"log|logged|sup|the|"
        r"shorter|longer|short|long|"
        r"higher|lower|elevated|reduced|increased|decreased|"
        r"abnormal|normal|preserved|impaired|worsening|"
        r"memory|naive|cord blood leukocyte|cord blood|"
        r"lymphocyte|granulocyte|leukocyte|"
        r"ultra-long|ultra long|three|areas?)\s+",
        "", n
    )
    # Strip trailing qualifier suffixes
    n = re.sub(
        r"\s+(activity|mediated|explained|adjusted|concentrations?|"
        r"levels?|values?|measures?|measurements?|accel|acceleration|"
        r"and \w+|with \w+|in \w+|of \w+)$",
        "", n
    )
    n = n.strip()
    if n in {"hr", "or", "rr", "ci"}:
        return ""
    # First check exact synonyms map
    if n in _SYNONYMS:
        return _SYNONYMS[n]
    # Then apply substring-based core reduction (catches "phenoageaccel" →
    # "phenoage", "memory t-cell telomere length" → "telomere length", etc.)
    core = _apply_core_reduction(n)
    if core:
        return _SYNONYMS.get(core, core)
    return n


# ─────────────────────────────────────────────────────────────────────────────
# Subject-class detection from a row's metadata
# ─────────────────────────────────────────────────────────────────────────────

def detect_subject_class(row):
    """
    Returns one of: 'supercentenarian', 'centenarian', 'nonagenarian', 'general'
    based on ages_mentioned + max_age + title/text content.
    Prefers the most-specific class actually studied.
    """
    ages_str = str(row.get("ages_mentioned") or "")
    ages = []
    for tok in re.split(r"[,;\s]+", ages_str):
        try:
            ages.append(int(tok))
        except ValueError:
            pass
    try:
        max_age = int(row.get("max_age") or 0)
        if max_age:
            ages.append(max_age)
    except (ValueError, TypeError):
        pass

    title_text = (str(row.get("title") or "") + " " + str(row.get("text") or ""))[:4000].lower()

    has_super = any(a >= 110 for a in ages) or "supercentenarian" in title_text
    has_cent  = any(100 <= a < 110 for a in ages) or "centenarian" in title_text
    has_nona  = any(90 <= a < 100 for a in ages) or "nonagenarian" in title_text

    # The most-specific class wins, but if a paper studies cents AND supercents,
    # the dominant study population is usually the lower (cents) — so we keep
    # the LOWEST level present rather than the highest. Empirically this matches
    # how the corpus reads.
    if has_nona and not (has_cent or has_super):
        return "nonagenarian"
    if has_cent:
        return "centenarian"
    if has_super:
        return "supercentenarian"
    return "general"


# ─────────────────────────────────────────────────────────────────────────────
# Per-paper biomarker extraction (regex-driven, fast)
# ─────────────────────────────────────────────────────────────────────────────

# Words preceding a value that nominate the biomarker — captured via a noun-phrase
# heuristic (up to 4 tokens of letters / hyphens / digits, not in stopwords).
_NAME_BACK_RE = re.compile(
    r"""
    (?P<name>
        (?:[A-Za-z][A-Za-z0-9\-ααβγ]{1,30}\s+){0,3}
        [A-Za-z][A-Za-z0-9\-ααβγ]{1,30}
    )
    \s*
    (?:level|levels|concentration|concentrations|count|counts|value|values)?
    \s*
    (?:was|were|of|=|:|reached|measured|reported|observed|found|exhibited|showed|\()?
    \s*$
    """,
    re.VERBOSE,
)


def _detect_value_type(left_ctx, right_ctx, sep, has_unit):
    """Classify value type from surrounding context. left_ctx/right_ctx are
    short strings around the match site."""
    s = (left_ctx + " " + right_ctx)
    if _KW_MEAN.search(s):
        return "mean"
    if _KW_MEDIAN.search(s):
        return "median"
    if sep in ("±", "+/-", "±"):
        return "mean_sd" if _KW_SD.search(s) or has_unit else "mean_sd"
    if sep in ("–", "—", "-", "to") or _KW_RANGE.search(s):
        return "range"
    if _KW_CI.search(s):
        return "ci"
    # Default: a single value with unit
    return "point_estimate"


def extract_from_text(text, max_matches=80):
    """Run value + ratio extraction over a single abstract. Returns list of dicts."""
    if not text:
        return []
    out = []

    # Ratio extraction first — OR/HR/RR (the user explicitly asked for these)
    for m in _RATIO_RE.finditer(text):
        kind = m.group("kind").strip().lower()
        kind_norm = {"or": "odds_ratio", "hr": "hazard_ratio",
                     "rr": "relative_risk"}.get(kind, kind.replace(" ", "_"))
        # Look back ~60 chars for the noun-phrase target of the ratio
        back = text[max(0, m.start() - 80):m.start()]
        name = _name_before(back)
        if not name or not _looks_like_biomarker(name):
            continue
        norm = normalize_name(name)
        if not norm:
            continue
        out.append({
            "biomarker_name_raw":  name,
            "biomarker_name_norm": normalize_name(name),
            "value":               m.group("val"),
            "value_low":           m.group("lo") or "",
            "value_high":          m.group("hi") or "",
            "unit":                "",
            "value_type":          kind_norm,
        })
        if len(out) >= max_matches:
            return out

    # Now value matches — only keep those with a recognized unit OR percent
    for m in _VAL_RE.finditer(text):
        unit = m.group("unit")
        if not unit:
            continue
        # Skip if it looks like a year, age, or sample size in disguise
        v_str = m.group("v1")
        try:
            v_num = float(v_str.replace(",", ""))
        except ValueError:
            continue
        if unit.lower() in ("years",) and 80 <= v_num <= 130:
            continue   # ages — already captured upstream
        # Find name preceding the match
        back  = text[max(0, m.start() - 100):m.start()]
        name  = _name_before(back)
        if not name or not _looks_like_biomarker(name):
            continue
        norm = normalize_name(name)
        if not norm:
            continue
        right_ctx = text[m.end(): m.end() + 60]
        v_type    = _detect_value_type(back, right_ctx, m.group("sep") or "", True)
        out.append({
            "biomarker_name_raw":  name,
            "biomarker_name_norm": normalize_name(name),
            "value":               v_str,
            "value_low":           "",
            "value_high":          m.group("v2") or "",
            "unit":                unit,
            "value_type":          v_type,
        })
        if len(out) >= max_matches:
            break

    return out


def _name_before(left_text):
    """
    Walk back through the text just before a value match to find the
    biomarker name (last noun-phrase-like token sequence). Returns "" if no
    plausible name exists in the last ~6 tokens.
    """
    # Trim to the last sentence boundary so we don't pull a name from the
    # previous sentence.
    last_sent = re.split(r"[.;!?]", left_text)[-1]
    toks = re.findall(
        r"[A-Za-z][A-Za-z0-9\-ααβγ·]{1,40}",
        last_sent,
    )
    if not toks:
        return ""
    # Drop trailing connective words (was/of/were/etc.) so the name itself wins
    while toks and toks[-1].lower() in {"was", "were", "of", "in", "the", "a",
                                          "an", "is", "are", "with", "for",
                                          "had", "have", "has", "to", "and",
                                          "or", "than", "by", "on", "as",
                                          "from", "between", "across",
                                          "respectively", "value", "values",
                                          "level", "levels", "concentration",
                                          "concentrations", "count", "counts",
                                          "mean", "median", "average"}:
        toks.pop()
    if not toks:
        return ""
    # Take the last 1-4 tokens that aren't stopwords
    name_toks = []
    for tok in reversed(toks[-6:]):
        if tok.lower() in _NAME_STOPWORDS:
            break
        name_toks.insert(0, tok)
        if len(name_toks) >= 4:
            break
    if not name_toks:
        return ""
    name = " ".join(name_toks).strip()
    if len(name) < 2 or len(name) > 60:
        return ""
    return name


# ─────────────────────────────────────────────────────────────────────────────
# Cross-validation lookups
# ─────────────────────────────────────────────────────────────────────────────

def build_nhanes_keyword_set():
    """Set of lowercase tokens / phrases from nhanes_merged column names."""
    if not NHANES.exists():
        return set()
    cols = pd.read_csv(NHANES, nrows=0, low_memory=False).columns.tolist()
    out = set()
    for c in cols:
        for tok in re.split(r"[_\s\-/]+", c.lower()):
            if len(tok) >= 3:
                out.add(tok)
    # Add some explicit phrase aliases
    out.update({
        "c-reactive protein", "hdl cholesterol", "ldl cholesterol",
        "total cholesterol", "triglycerides", "fasting glucose", "hba1c",
        "body mass index", "systolic blood pressure", "diastolic blood pressure",
        "hemoglobin", "white blood cell", "red blood cell",
    })
    return out


def build_gwas_trait_set():
    """Set of lowercased phrases drawn from gwas_longevity.csv DISEASE/TRAIT."""
    if not GWAS.exists():
        return set()
    g = pd.read_csv(GWAS, low_memory=False, dtype=str)
    trait_col = "DISEASE/TRAIT" if "DISEASE/TRAIT" in g.columns else None
    if not trait_col:
        return set()
    out = set()
    for t in g[trait_col].dropna().astype(str):
        out.add(t.lower())
        for tok in re.split(r"[,;\(\)\s/]+", t.lower()):
            if len(tok) >= 4:
                out.add(tok)
    return out


def biomarker_in_set(name_norm, kw_set):
    if not name_norm:
        return False
    nl = name_norm.lower()
    if nl in kw_set:
        return True
    # Token-level match — at least one informative token from name appears in kw_set
    for tok in re.split(r"[\s\-/]+", nl):
        if len(tok) >= 4 and tok in kw_set:
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print(f"Loading {MASTER} ...")
    df = pd.read_csv(MASTER, low_memory=False)
    acad = df[df["source_type"] == "academic"].copy()
    print(f"  Academic rows: {len(acad):,}")

    # Filter: centenarian-focused OR (has_stats AND any biomarker_* True)
    biomarker_cols = [c for c in df.columns if c.startswith("biomarker_")]
    bio_any = acad[biomarker_cols].astype(str).apply(
        lambda r: any(v in {"True", "1", "1.0"} for v in r), axis=1
    )
    is_centenarian = acad["is_centenarian_profile"].astype(str).isin({"True", "1", "1.0"})
    has_stats      = acad["has_stats"].astype(str).isin({"True", "1", "1.0"})
    keep = is_centenarian | (has_stats & bio_any)
    sub = acad[keep].reset_index(drop=True)
    print(f"  Filtered (centenarian OR stats+biomarker): {len(sub):,}")

    # Subject class per paper
    sub["subject_class"] = sub.apply(detect_subject_class, axis=1)
    print(f"  Subject-class distribution:")
    for cls, n in sub["subject_class"].value_counts().items():
        print(f"    {cls:<20} {n:,}")

    # Extract
    print(f"\nExtracting biomarker mentions ...")
    t0 = time.time()
    rows = []
    for i, r in enumerate(sub.itertuples(index=False), 1):
        if i % 500 == 0:
            print(f"  [{i:,}/{len(sub):,}]  elapsed {time.time()-t0:.0f}s  rows so far {len(rows):,}")
        text = str(r.text or "")
        if not text:
            continue
        extractions = extract_from_text(text)
        for x in extractions:
            rows.append({
                **x,
                "pmid":              str(r.pmid or ""),
                "record_id":         r.record_id,
                "pub_year":          r.pub_year,
                "study_type":        r.study_type,
                "sample_size":       r.stat_sample_size,
                "population_country":r.population_country,
                "subject_class":     r.subject_class,
                "source_journal":    r.journal,
            })

    print(f"  Extracted {len(rows):,} biomarker mentions in {time.time()-t0:.0f}s")

    ref = pd.DataFrame(rows)
    if ref.empty:
        print("  No biomarker rows extracted — abort")
        return

    # Standardized name schema: biomarker_name_raw (as-extracted) + biomarker_name
    # (snake_case canonical join key). Keep biomarker_name_norm in `ref` in memory
    # for the grading groupby below.
    ref_out = ref.copy()
    ref_out["biomarker_name"] = ref_out["biomarker_name_norm"].map(canonical_name)
    ref_out = ref_out.drop(columns=["biomarker_name_norm"])
    _front = ["biomarker_name_raw", "biomarker_name"]
    ref_out = ref_out[_front + [c for c in ref_out.columns if c not in _front]]
    ref_out.to_csv(OUT_ROWS, index=False)
    print(f"  Saved per-mention reference → {OUT_ROWS}")

    # Aggregate by normalized biomarker
    print(f"\nAggregating by normalized biomarker ...")
    nhanes_kw = build_nhanes_keyword_set()
    gwas_kw   = build_gwas_trait_set()
    print(f"  NHANES keyword set: {len(nhanes_kw)}")
    print(f"  GWAS trait set:     {len(gwas_kw)}")

    grouped = []
    for name, grp in ref.groupby("biomarker_name_norm"):
        pmids = grp["pmid"].dropna().astype(str).str.strip()
        pmids = pmids[pmids != ""]
        n_pmids   = pmids.nunique()
        countries = grp["population_country"].dropna().astype(str).str.strip()
        countries = countries[countries.str.lower().isin({"nan", ""}) == False]
        n_countries = countries.nunique()
        classes  = sorted(set(grp["subject_class"]))
        units_seen = sorted(set(u for u in grp["unit"].dropna() if u))
        value_types = sorted(set(grp["value_type"].dropna()))
        sample_sizes = pd.to_numeric(grp["sample_size"], errors="coerce").dropna()
        median_n = int(sample_sizes.median()) if len(sample_sizes) else 0
        in_nh = biomarker_in_set(name, nhanes_kw)
        in_gw = biomarker_in_set(name, gwas_kw)

        # Evidence grading. Two paths to A:
        #   (i) corpus breadth: n_pmids>=3 AND n_countries>=2 AND cross-validated
        #   (ii) publishable cross-validation: in NHANES AND in GWAS AND a
        #        meaningful corpus presence (n_pmids>=3 OR n_mentions>=5),
        #        AND the normalized name is short enough (≤4 words) that the
        #        cross-validation isn't an artifact of a long compound phrase.
        name_token_count = len(name.split())
        is_well_formed   = name_token_count <= 4
        cross_validated  = in_nh and in_gw
        corpus_signal    = (n_pmids >= 3) or (len(grp) >= 5)

        if (n_pmids >= 3 and n_countries >= 2) and (in_nh or in_gw):
            grade = "A"
        elif cross_validated and corpus_signal and is_well_formed:
            grade = "A"
        elif n_pmids >= 3 and n_countries >= 2:
            grade = "B"
        elif (n_pmids >= 2) and cross_validated and is_well_formed:
            grade = "B"
        elif (n_pmids >= 2) and (in_nh or in_gw) and is_well_formed:
            grade = "B"
        elif n_pmids >= 3 and is_well_formed:
            grade = "B"   # multi-source corpus signal alone
        else:
            grade = "C"

        grouped.append({
            "biomarker_normalized":     name,
            "n_mentions":               len(grp),
            "n_independent_sources":    n_pmids,
            "n_countries":              n_countries,
            "countries_sample":         "|".join(sorted(countries.unique())[:6]),
            "subject_classes_seen":     "|".join(classes),
            "value_types":              "|".join(value_types),
            "units_seen":               "|".join(units_seen[:6]),
            "median_sample_size":       median_n,
            "in_nhanes":                in_nh,
            "in_gwas":                  in_gw,
            "evidence_grade":           grade,
        })

    summary = pd.DataFrame(grouped)
    # Sort: grade A first, then B, then by n_sources
    grade_order = {"A": 0, "B": 1, "C": 2}
    summary["_g"] = summary["evidence_grade"].map(grade_order)
    summary = summary.sort_values(
        ["_g", "n_independent_sources", "n_mentions"],
        ascending=[True, False, False],
    ).drop(columns="_g").reset_index(drop=True)
    # Standardized name schema: biomarker_name = snake_case canonical join key.
    # Keep `summary` with biomarker_normalized for the headline print below.
    summary_out = summary.rename(columns={"biomarker_normalized": "biomarker_name"})
    summary_out["biomarker_name"] = summary_out["biomarker_name"].map(canonical_name)
    summary_out = summary_out[["biomarker_name"] + [c for c in summary_out.columns if c != "biomarker_name"]]
    summary_out.to_csv(OUT_SUM, index=False)
    print(f"  Saved summary → {OUT_SUM}")

    # Print headline
    print(f"\n{'=' * 80}")
    print("  BIOMARKER SUMMARY")
    print(f"{'=' * 80}")
    grade_counts = summary["evidence_grade"].value_counts().reindex(["A", "B", "C"]).fillna(0).astype(int)
    print(f"  Total normalized biomarkers: {len(summary):,}")
    print(f"  Grade A: {int(grade_counts['A'])}")
    print(f"  Grade B: {int(grade_counts['B'])}")
    print(f"  Grade C: {int(grade_counts['C'])}")

    print(f"\n  Top 40 (by grade, then n_independent_sources):")
    fmt = "  {:<32} {:>4} {:>4} {:>4}  NHANES={:<3} GWAS={:<3} grade={}"
    print(fmt.format("biomarker", "src", "cty", "ment", "", "", ""))
    for r in summary.head(40).itertuples():
        nh = "Y" if r.in_nhanes else "-"
        gw = "Y" if r.in_gwas   else "-"
        print(fmt.format(
            r.biomarker_normalized[:30], r.n_independent_sources,
            r.n_countries, r.n_mentions, nh, gw, r.evidence_grade
        ))


if __name__ == "__main__":
    main()
