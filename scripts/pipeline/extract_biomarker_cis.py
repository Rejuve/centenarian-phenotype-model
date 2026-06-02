"""
Phase 2.8 - Re-extract 95% CI bounds for OR/HR/RR biomarker mentions.

The v2 biomarker extractor captured point OR/HR/RR values into
centenarian_biomarker_reference.csv but did NOT pair the confidence-interval
bounds (only 3/203 rows had value_low/value_high; the `ci`-type rows are noise).

DerSimonian-Laird random-effects pooling needs a per-study variance, which we
derive from the CI. This pass looks each OR/HR/RR mention up by PMID in
master_dataset.csv (`text` field = abstract for academic rows) and extracts the
CI bounds, accepting:

    HR 1.52 (95% CI 1.24-1.86)
    HR 1.52, 95% CI 1.20-1.85
    OR=0.34 (95% CI=0.21-0.55)
    HR=1.52 [1.20, 1.85]          (bracket form, no "95% CI" label)

Where the abstract reports no CI, ci_lower/ci_upper stay null. NOTHING is
imputed. Output columns ci_lower, ci_upper, ci_sep_format, ci_match_value are
written back to centenarian_biomarker_reference.csv.
"""
import re
import pandas as pd

REF_PATH = "data/processed/centenarian_biomarker_reference.csv"
MASTER_PATH = "data/processed/master_dataset.csv"
EFFECT_TYPES = {"odds_ratio", "hazard_ratio", "relative_risk"}

NUM = r"[0-9]+(?:\.[0-9]+)?"
SEP = r"(?:\s*(?:-|–|—|to)\s*|\s*,\s*)"  # hyphen / en-dash / em-dash / "to" / comma

# effect keyword followed by its point value
EFFECT_RE = re.compile(
    r"(?P<kw>a?OR|a?HR|RR|odds ratios?|hazard ratios?|relative risk|risk ratio)"
    r"\s*[:=]?\s*(?:of\s+)?[\[\(]?\s*(?P<val>" + NUM + r")",
    re.IGNORECASE,
)
# labelled CI: "95% CI <lo> <sep> <hi>"
CI_LABEL_RE = re.compile(
    r"95\s*%?\s*(?:CI|confidence interval)\s*[:=]?\s*[\[\(]?\s*"
    r"(?P<lo>" + NUM + r")" + SEP + r"(?P<hi>" + NUM + r")",
    re.IGNORECASE,
)
# bracket CI with no label: "[<lo> <sep> <hi>]" or "(<lo> <sep> <hi>)"
CI_BRACKET_RE = re.compile(
    r"[\[\(]\s*(?P<lo>" + NUM + r")" + SEP + r"(?P<hi>" + NUM + r")\s*[\]\)]"
)


def _norm_pmid(s: pd.Series) -> pd.Series:
    return s.astype("string").str.replace(r"\.0$", "", regex=True)


def find_ci_for_value(text: str, value: float):
    """Return (lo, hi, fmt) for the effect mention whose point value matches
    `value`, by locating the effect token then the nearest following CI."""
    if not text or pd.isna(value):
        return None
    label_hits = [(m.start(), float(m.group("lo")), float(m.group("hi")))
                  for m in CI_LABEL_RE.finditer(text)]
    bracket_hits = [(m.start(), float(m.group("lo")), float(m.group("hi")))
                    for m in CI_BRACKET_RE.finditer(text)]

    best = None  # (distance, lo, hi, fmt)
    for em in EFFECT_RE.finditer(text):
        ev = float(em.group("val"))
        if abs(ev - value) > max(0.03, 0.03 * abs(value)):
            continue
        end = em.end()
        # labelled CI within ~45 chars after the value
        for pos, lo, hi in label_hits:
            if 0 <= pos - end <= 45 and lo < hi:
                cand = (pos - end, lo, hi, "labelled")
                if best is None or cand[0] < best[0]:
                    best = cand
        # bracket CI immediately after the value, validated to bracket it
        for pos, lo, hi in bracket_hits:
            if -1 <= pos - end <= 6 and lo < hi and lo <= value <= hi:
                cand = (pos - end, lo, hi, "bracket")
                if best is None or cand[0] < best[0]:
                    best = cand
    if best is None:
        return None
    return best[1], best[2], best[3]


def main():
    ref = pd.read_csv(REF_PATH)
    ref["pmid"] = _norm_pmid(ref["pmid"])
    ref["value"] = pd.to_numeric(ref["value"], errors="coerce")

    master = pd.read_csv(MASTER_PATH, dtype={"pmid": str})
    master["pmid"] = _norm_pmid(master["pmid"])
    text_by_pmid = (master.dropna(subset=["pmid"])
                    .drop_duplicates("pmid")
                    .set_index("pmid")["text"].astype(str).to_dict())

    ref["ci_lower"] = pd.NA
    ref["ci_upper"] = pd.NA
    ref["ci_sep_format"] = pd.NA

    is_effect = ref["value_type"].isin(EFFECT_TYPES)
    n_rows = int(is_effect.sum())
    n_with_text = 0
    n_recovered = 0

    for idx in ref.index[is_effect]:
        pmid = ref.at[idx, "pmid"]
        text = text_by_pmid.get(pmid)
        if not text or text == "nan":
            continue
        n_with_text += 1
        res = find_ci_for_value(text, ref.at[idx, "value"])
        if res:
            lo, hi, fmt = res
            ref.at[idx, "ci_lower"] = lo
            ref.at[idx, "ci_upper"] = hi
            ref.at[idx, "ci_sep_format"] = fmt
            n_recovered += 1

    ref.to_csv(REF_PATH, index=False)

    print(f"OR/HR/RR mention rows           : {n_rows}")
    print(f"  with abstract text by PMID    : {n_with_text}")
    print(f"  CI recovered (ci_lower/upper) : {n_recovered} "
          f"({100*n_recovered/n_rows:.0f}% of effect rows)")
    fmt_counts = ref.loc[is_effect, "ci_sep_format"].value_counts()
    print(f"  by format                     : {dict(fmt_counts)}")

    # per-biomarker poolability: how many distinct studies have effect+CI
    eff = ref[is_effect].copy()
    eff["has_ci"] = eff["ci_lower"].notna()
    grp = eff.groupby("biomarker_name").agg(
        n_effect_studies=("pmid", "nunique"),
        n_studies_with_ci=("pmid", lambda s: eff.loc[s.index][eff.loc[s.index, "has_ci"]]["pmid"].nunique()),
    ).sort_values("n_studies_with_ci", ascending=False)
    poolable = (grp["n_studies_with_ci"] >= 2).sum()
    print(f"\nBiomarkers with >=2 studies that have OR/HR + CI (poolable): {poolable}")
    print(grp[grp["n_studies_with_ci"] >= 2].head(20).to_string())


if __name__ == "__main__":
    main()
