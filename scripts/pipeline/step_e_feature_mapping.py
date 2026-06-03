"""
Step E — feature selection, composite evidence scoring, and layer assignment.

Composite evidence score (Layer 1/2 BEHAVIORAL features), confirmed weights:
  corroboration_tier   0.35   (gold=1.0 / silver=0.66 / bronze=0.33)
  individual_count     0.25   (log1p -> min-max 0..1)
  academic_paper_count 0.25   (log1p -> min-max 0..1)
  prevalence_ratio     0.15   (|ln(ratio)| -> min-max; redistributed when absent)
  gwas_corroborated    0.00   (flag only at L1/2; reintroduced with weight at L3/Step F)
Each component is normalized 0..1 first so no input dominates by scale.

Genetics is ~20-50% of longevity variance (heritability literature) but is not
scoreable from behavioral inputs and we have a single GWAS source -> weight 0.00
here is a KNOWN LIMITATION, not a finding (see MODEL_CARD.md).

Outputs:
  data/processed/step_e_feature_layer_assignments.csv
  data/processed/layer1_quiz_features.csv

Run from the project root:  python scripts/pipeline/step_e_feature_mapping.py
"""
import math
import numpy as np
import pandas as pd

P = "data/processed/"
LOCK = P + "tier1_features_locked.csv"
ASSOC = P + "step_d_trait_associations.csv"
LAYER1 = P + "layer1_trait_frequency.csv"
BIO = P + "biomarker_summary.csv"
PATH = P + "gwas_biomarker_pathways.csv"
OUT_ASSIGN = P + "step_e_feature_layer_assignments.csv"
OUT_QUIZ = P + "layer1_quiz_features.csv"

TIER_N = {"gold": 1.0, "silver": 0.66, "bronze": 0.33}
GRADE_N = {"A": 1.0, "B": 0.66, "C": 0.33}
W = dict(tier=0.35, indiv=0.25, acad=0.25, ratio=0.15)  # gwas=0.00 at L1/2
COMPLETENESS = {1: 30, 2: 50, 3: 80}
GENETIC_NOTE = ("Genetics ~20-50% of longevity variance (heritability lit.) but not "
                "scoreable from behavioral/self-report inputs and single-source GWAS; "
                "gwas weight=0.00 at L1/2 is a known limitation, reintroduced at L3.")

# trait -> consolidated domain (user spec; overrides raw trait_category).
DOMAIN = {}
for t in ["staying active", "walking daily", "gardening", "dancing", "running/marathon",
          "regular exercise", "cycling", "swimming", "golf"]:
    DOMAIN[t] = "physical_activity"
for t in ["sense of purpose", "still working", "volunteering", "reads daily",
          "keeping busy", "curiosity/learning"]:
    DOMAIN[t] = "purpose_meaning"
for t in ["positive outlook", "humor/laughter", "low stress / calm", "gratitude"]:
    DOMAIN[t] = "psychological_resilience"
for t in ["friendships", "socializing", "community ties"]:
    DOMAIN[t] = "social_connectedness"
for t in ["close family", "grandchildren", "married (long)"]:
    DOMAIN[t] = "family_bonds"
for t in ["creative hobbies", "puzzles/games", "music"]:
    DOMAIN[t] = "cognitive_engagement"
for t in ["faith/religion", "religious community"]:
    DOMAIN[t] = "faith_religion"
for t in ["good sleep", "naps"]:
    DOMAIN[t] = "sleep"
for t in ["smoking_status_never", "smoking_status_former", "smoking_status_current",
          "drinks alcohol (moderate)", "no alcohol"]:
    DOMAIN[t] = "substance_use"
DOMAIN["lives independently"] = "functional_independence"
# all diet traits -> diet
DIET = ["sweets/sugar", "rice staple", "eats fish", "tea", "chocolate", "eats fruit",
        "eats eggs", "beans/legumes", "eats vegetables", "eating in moderation", "coffee",
        "honey", "home cooking", "olive oil", "vegetarian diet", "oatmeal/porridge"]
for t in DIET:
    DOMAIN[t] = "diet"

FINDING_CONTEXT = {
    "drinks alcohol (moderate)":
        "Centenarians in this corpus report light-to-moderate alcohol at higher rates "
        "than the general 60+ population (75.5% vs 62.4% of documented drinkers). Current "
        "WHO/IARC evidence indicates no universally safe level for cancer risk. Genetic "
        "variants may influence individual risk — explored in Layer 3.",
    "smoking_status_former":
        "Former smokers are less common among centenarians than the general 60+ population "
        "(14.7% vs 36.7%). Protective effect of cessation increases with years since "
        "quitting; cessation timing is a Layer-3 modifier, not captured at quiz level.",
}


def minmax(s):
    s = s.astype(float)
    rng = s.max() - s.min()
    return (s - s.min()) / rng if rng > 0 else pd.Series(0.5, index=s.index)


def main():
    lock = pd.read_csv(LOCK)
    assoc = pd.read_csv(ASSOC).set_index("trait")
    lay = pd.read_csv(LAYER1).set_index("trait")

    # ---- composite behavioral evidence score (54 traits) ----
    lock["norm_tier"] = lock["corroboration_tier"].map(TIER_N)
    lock["norm_indiv"] = minmax(np.log1p(lock["individual_count"]))
    lock["norm_acad"] = minmax(np.log1p(lock["academic_paper_count"]))
    # prevalence-ratio strength |ln(ratio)| for traits that have it
    rs = {}
    for tr in lock["trait"]:
        pr = assoc["prevalence_ratio"].get(tr, np.nan) if tr in assoc.index else np.nan
        rs[tr] = abs(math.log(pr)) if (isinstance(pr, (int, float)) and pr == pr and pr > 0) else np.nan
    lock["ratio_strength_raw"] = lock["trait"].map(rs)
    has_r = lock["ratio_strength_raw"].notna()
    lock["norm_ratio"] = np.nan
    if has_r.any():
        lock.loc[has_r, "norm_ratio"] = minmax(lock.loc[has_r, "ratio_strength_raw"])

    def score(r):
        base = W["tier"] * r["norm_tier"] + W["indiv"] * r["norm_indiv"] + W["acad"] * r["norm_acad"]
        if pd.notna(r["norm_ratio"]):
            return round(base + W["ratio"] * r["norm_ratio"], 4)
        # redistribute the 0.15 proportionally across the present components
        return round(base / (W["tier"] + W["indiv"] + W["acad"]), 4)
    lock["evidence_score"] = lock.apply(score, axis=1)
    lock["domain"] = lock["trait"].map(lambda t: DOMAIN.get(t, "other"))

    rows = []
    for _, r in lock.iterrows():
        tr = r["trait"]
        a = assoc.loc[tr] if tr in assoc.index else None
        rows.append(dict(
            feature=tr, layer=1, domain=r["domain"], evidence_score=r["evidence_score"],
            corroboration_tier=r["corroboration_tier"], gwas_corroborated=False,
            direction=r.get("direction", ""), quiz_question_eligible=True,
            nhanes_prevalence=(a["population_prevalence_pct"] if a is not None else np.nan),
            centenarian_prevalence=(a["centenarian_prevalence_pct"] if a is not None else np.nan),
            prevalence_ratio=(a["prevalence_ratio"] if a is not None else np.nan),
            finding_context=FINDING_CONTEXT.get(tr, ""),
            genetic_evidence_note=GENETIC_NOTE, confidence_completeness_pct=COMPLETENESS[1]))

    # ---- Layer 2: self-reported clinical + family history of longevity ----
    bio = pd.read_csv(BIO).set_index("biomarker_name")
    def bscore(name):
        g = bio["evidence_grade"].get(name, "C")
        return round(GRADE_N.get(g, 0.33), 4)
    L2 = [("diabetes", "diabetes"), ("hypertension", "hypertension"),
          ("body_mass_index", "body_composition"), ("waist_circumference", "body_composition")]
    for name, dom in L2:
        rows.append(dict(feature=f"{name} (self-report)", layer=2, domain=dom,
                         evidence_score=bscore(name),
                         corroboration_tier=bio["evidence_grade"].get(name, "C"),
                         gwas_corroborated=(name in ("diabetes", "hypertension")),
                         direction="context_dependent", quiz_question_eligible=True,
                         nhanes_prevalence=np.nan, centenarian_prevalence=np.nan,
                         prevalence_ratio=np.nan, finding_context="",
                         genetic_evidence_note=GENETIC_NOTE, confidence_completeness_pct=COMPLETENESS[2]))
    rows.append(dict(feature="family_history_of_longevity (parent/grandparent past 90)",
                     layer=2, domain="genetic_family_history", evidence_score=0.75,
                     corroboration_tier="gwas_supported", gwas_corroborated=True,
                     direction="positive", quiz_question_eligible=True,
                     nhanes_prevalence=np.nan, centenarian_prevalence=np.nan, prevalence_ratio=np.nan,
                     finding_context="332 parental-longevity associations in gwas_longevity.csv "
                     "(parental extreme longevity 95+, parental age at death) support a heritable "
                     "basis; included as a self-report proxy for genetic predisposition.",
                     genetic_evidence_note=GENETIC_NOTE, confidence_completeness_pct=COMPLETENESS[2]))

    # ---- Layer 3: clinical biomarkers (similarity_primary/prognostic_supporting) ----
    l3 = bio[bio["model_use"].isin(["similarity_primary", "prognostic_supporting"])]
    for name, br in l3.iterrows():
        rows.append(dict(feature=name, layer=3, domain="clinical_biomarker",
                         evidence_score=round(GRADE_N.get(br["evidence_grade"], 0.33), 4),
                         corroboration_tier=br["evidence_grade"], gwas_corroborated=bool(br.get("in_gwas", False)),
                         direction=("enriched" if br.get("primary_pooled_OR", 1) and br["primary_pooled_OR"] > 1 else "depleted"),
                         quiz_question_eligible=False, nhanes_prevalence=np.nan,
                         centenarian_prevalence=np.nan, prevalence_ratio=np.nan, finding_context="",
                         genetic_evidence_note=GENETIC_NOTE, confidence_completeness_pct=COMPLETENESS[3]))
    # ---- Layer 3: genetic variants (from gwas_biomarker_pathways) ----
    for _, pr in pd.read_csv(PATH).iterrows():
        rows.append(dict(feature=f"{pr['gene']} ({pr['variant']})", layer=3, domain="genetic_variant",
                         evidence_score=0.70, corroboration_tier="gwas", gwas_corroborated=True,
                         direction=pr["effect_direction"][:40], quiz_question_eligible=False,
                         nhanes_prevalence=np.nan, centenarian_prevalence=np.nan, prevalence_ratio=np.nan,
                         finding_context=f"Influences {pr['influenced_biomarker']} via {pr['pathway']} "
                         f"(see gwas_biomarker_pathways.csv).",
                         genetic_evidence_note=GENETIC_NOTE, confidence_completeness_pct=COMPLETENESS[3]))
    # ---- Layer 3: microbiome (flagged, not blocking) ----
    rows.append(dict(feature="gut_microbiome_diversity", layer=3, domain="microbiome",
                     evidence_score=np.nan, corroboration_tier="pending_integration", gwas_corroborated=False,
                     direction="positive (diversity)", quiz_question_eligible=False,
                     nhanes_prevalence=np.nan, centenarian_prevalence=np.nan, prevalence_ratio=np.nan,
                     finding_context="FLAGGED PENDING: centenarian gut bacteriophage diversity (Zenodo "
                     "6579480) + age-group microbiota (PLOS One pone.0305583) acquired; taxa/diversity "
                     "metrics not yet integrated. Does not block Layer 3 finalization.",
                     genetic_evidence_note=GENETIC_NOTE, confidence_completeness_pct=COMPLETENESS[3]))

    assign = pd.DataFrame(rows)
    assign.to_csv(OUT_ASSIGN, index=False)

    # ---- layer1_quiz_features.csv (per behavioral domain) ----
    l1 = lock.copy()
    quiz = []
    for dom, g in l1.groupby("domain"):
        w = g["individual_count"].clip(lower=1)
        es = round(float((g["evidence_score"] * w).sum() / w.sum()), 4)
        top = g.sort_values("individual_count", ascending=False)
        examples = ""
        for tr in top["trait"].head(2):
            ex = lay["centenarian_examples"].get(tr, "")
            if isinstance(ex, str) and ex:
                examples = ex; break
        fc = next((FINDING_CONTEXT[t] for t in top["trait"] if t in FINDING_CONTEXT), "")
        strongest = top.iloc[0]
        quiz.append(dict(
            domain_name=dom,
            contributing_traits="|".join(top["trait"].tolist()),
            evidence_score=es,
            gwas_corroborated=False,
            top_centenarian_examples=("|".join(str(examples).split("|")[:5]) if examples else ""),
            sample_finding=f"{int(g['individual_count'].sum())} centenarian-trait mentions across "
                           f"{len(g)} sub-traits; strongest: '{strongest['trait']}' "
                           f"({strongest['corroboration_tier']}, n={int(strongest['individual_count'])})",
            finding_context=fc))
    quiz = pd.DataFrame(quiz).sort_values("evidence_score", ascending=False).reset_index(drop=True)
    quiz.to_csv(OUT_QUIZ, index=False)

    print(f"Wrote {OUT_ASSIGN} ({len(assign)} features: "
          f"L1={int((assign.layer==1).sum())} L2={int((assign.layer==2).sum())} L3={int((assign.layer==3).sum())})")
    print(f"Wrote {OUT_QUIZ} ({len(quiz)} Layer-1 quiz domains)\n")
    pd.set_option("display.width", 240); pd.set_option("display.max_colwidth", 60)
    print("=== layer1_quiz_features.csv (FULL) ===")
    print(quiz[["domain_name", "evidence_score", "contributing_traits", "sample_finding"]].to_string(index=False))


if __name__ == "__main__":
    main()
