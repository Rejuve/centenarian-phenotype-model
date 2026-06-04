"""Data-first feature re-check on the (enriched) academic corpus.

Purpose: after expanding the corpus (foundational aging-biology backbone + NECS papers), check
whether any feature NOT already in the model earns inclusion under the data-first rule — without
pre-entering candidates. Reports:
  1. Frequency of the existing tag categories (trait_* / biomarker_* / gene_*) in the
     longevity/centenarian-focused subset.
  2. An OPEN term scan over title+abstract for candidate constructs that are not currently modelled
     (sensory, oral health, fitness, SES, sleep apnea, etc.), so something only shows up
     if the corpus actually discusses it in a longevity context.

This is a screen, not a confirmatory test: a strong corpus signal is a CANDIDATE that then needs the
usual evidence grading + (for Tier 2/3) a centenarian-correlation check before inclusion.

Usage: python scripts/analysis/corpus_feature_recheck.py
"""
from __future__ import annotations

import re

import pandas as pd

CORPUS = "data/raw/academic_papers.csv"

# candidate constructs NOT currently modelled — each maps to regex alternations over title+abstract.
CANDIDATES = {
    "parental/offspring longevity": r"parental longevity|offspring of centenarian|familial longevity|long-lived (parent|famil)",
    "hearing": r"hearing (loss|impairment)|audiometr|presbycusis",
    "vision": r"vision (loss|impairment)|visual acuity|cataract|macular degeneration",
    "oral/periodontal": r"periodont|tooth loss|edentulous|oral health|dental",
    "sleep apnea": r"sleep apn('|o)ea|OSA|sleep-disordered breathing",
    "cardiorespiratory fitness": r"VO2 ?max|cardiorespiratory fitness|aerobic capacity",
    "gait/walking speed": r"gait speed|walking speed|usual pace",
    "education/SES": r"educational attainment|socioeconomic|income|years of education",
    "vitamin D": r"vitamin ?d|25-?hydroxyvitamin",
    "hearing aid/prosthetic (anti-signal check)": r"hearing aid|prosthe(sis|tic)|wheelchair",
}

# already-modelled constructs, for context (not re-flagged)
MODELLED = {"physical activity", "diet", "social", "purpose", "sleep", "smoking", "alcohol",
            "bmi", "telomere", "inflammation", "glucose", "lipids", "igf1", "epigenetic",
            "microbiome", "grip", "apoe", "foxo3"}


def main():
    df = pd.read_csv(CORPUS, low_memory=False)
    df["text"] = (df["title"].fillna("") + " . " + df["abstract"].fillna("")).str.lower()
    n = len(df)

    # longevity/centenarian-focused subset
    if "is_centenarian_focused" in df:
        focus = df[df["is_centenarian_focused"] == True]  # noqa: E712
    else:
        focus = df
    nf = len(focus)
    print(f"corpus N={n}; longevity/centenarian-focused subset={nf}\n")

    # 1. existing tag-category frequencies in the focused subset
    tagcols = [c for c in df.columns if c.startswith(("trait_", "biomarker_", "gene_"))]
    print("=== existing tag categories (focused subset prevalence) ===")
    rows = []
    for c in tagcols:
        v = pd.to_numeric(focus[c], errors="coerce").fillna(0)
        hits = int((v > 0).sum())
        rows.append((c, hits, round(100 * hits / nf, 1)))
    for c, h, p in sorted(rows, key=lambda r: -r[1]):
        print(f"  {c:<28} {h:>5}  ({p}%)")

    # 2. open scan for non-modelled candidate constructs
    print("\n=== candidate constructs NOT currently modelled (corpus mentions) ===")
    print("  construct                                  all-corpus   focused-subset")
    res = []
    for name, pat in CANDIDATES.items():
        rx = re.compile(pat, re.I)
        allc = int(df["text"].str.contains(rx).sum())
        foc = int(focus["text"].str.contains(rx).sum())
        res.append((name, allc, foc))
    for name, allc, foc in sorted(res, key=lambda r: -r[2]):
        print(f"  {name:<42} {allc:>6}      {foc:>6}")

    print("\nInterpretation: high focused-subset counts = a construct the longevity literature actually "
          "discusses -> a CANDIDATE for evidence grading + centenarian-correlation check (not an "
          "automatic inclusion). Low counts = no data-first basis for adding it.")


if __name__ == "__main__":
    main()
