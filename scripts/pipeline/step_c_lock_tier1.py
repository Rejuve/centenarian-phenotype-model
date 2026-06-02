"""
STEP C (v2, corrected) - Lock Tier 1 lifestyle features with additive,
hierarchical corroboration (user spec, 2026-06-01).

  bronze = appears in news-corpus centenarian profiles (individual_count >= 3).
           All 24 keyword traits qualify -> baseline tier.
  silver = bronze + academically corroborated: a trait synonym AND a longevity
           term (centenarian/supercentenarian/longevity/lifespan/long-lived)
           co-occur in a paper's title+abstract. >= 2 papers => silver.
           Academic control-group prevalence (corpus_control) also lands here.
  gold   = DEFERRED to Step D. Gold means the feature is a highly supported
           correlate of superlongevity: the centenarian-vs-population
           ASSOCIATION has actually been quantified (Step D computes the
           population baseline and the enrichment/effect). Mere presence of the
           variable in a public reference dataset is NOT gold -- that presence
           is useful infrastructure (baselines, product) but is not evidence of
           association with exceptional longevity. So the lock-time ceiling is
           silver; `gold_eligible` flags the candidates Step D will test.

`baseline_source` records which independent population reference dataset (NHANES,
WHO, ...) is AVAILABLE to compute the baseline in Step D. LongeviQuest is never a
baseline -- it sources the centenarian case data (the numerator).

Tiers are hierarchical: every gold is silver, every silver is bronze.
Note: academic_papers.csv has no full_text column; we search title+abstract.

Output: data/processed/tier1_features_locked.csv with added columns
  academic_paper_count, nhanes_module, baseline_source.
"""
import re
import pandas as pd

LAYER1 = "data/processed/layer1_trait_frequency.csv"
ACADEMIC = "data/raw/academic_papers.csv"
OUT = "data/processed/tier1_features_locked.csv"

LONGEVITY = re.compile(
    r"centenarian|supercentenarian|longevity|lifespan|long[-\s]lived", re.I)

# trait -> synonyms (user-provided; grandchildren + alcohol filled in)
SYNONYMS = {
    "close family": ["close family", "family", "relatives", "children", "grandchildren"],
    "friendships": ["friendship", "friends", "social network", "peer relationship"],
    "socializing": ["socializing", "social engagement", "social participation"],
    "positive outlook": ["positive outlook", "optimism", "positive attitude", "wellbeing", "well-being", "happiness"],
    "reads daily": ["reading", "cognitive engagement", "intellectual activity"],
    "creative hobbies": ["hobbies", "creative activit", "arts", "crafts"],
    "faith/religion": ["religion", "religious", "spirituality", "church"],
    "community ties": ["community", "volunteering", "civic engagement"],
    "walking daily": ["walking", "ambulatory activity", "steps"],
    "drinks alcohol (moderate)": ["alcohol", "drinking", "wine", "moderate drink"],
    "regular exercise": ["exercise", "physical activity", "fitness training"],
    "staying active": ["active lifestyle", "physical function"],
    "grandchildren": ["grandchildren", "grandchild", "family"],
    "humor/laughter": ["humor", "laughter", "sense of humor"],
    "dancing": ["dance", "dancing"],
    "volunteering": ["volunteer", "volunteering", "community service"],
    "married (long)": ["marriage", "married", "spouse", "partnership"],
    "running/marathon": ["running", "jogging", "aerobic exercise", "marathon"],
    "puzzles/games": ["cognitive activit", "puzzles", "games", "mental exercise"],
    "religious community": ["religious community", "church community", "congregation"],
    "lives independently": ["independent living", "independence", "autonomy"],
    "chocolate": ["chocolate", "cocoa", "flavonoid"],
    "eats eggs": ["eggs", "dietary protein"],
    "music": ["music", "musical activity", "singing"],
}

# category / trait -> NHANES module on disk (None if no relevant module)
def nhanes_module_for(trait, category):
    t = trait.lower()
    if "smok" in t:
        return "nhanes_smoking"
    if "alcohol" in t or "drink" in t:
        return "nhanes_alcohol"
    return {"physical_activity": "nhanes_physical_activity",
            "sleep": "nhanes_sleep"}.get(category)

# WHO GHO age-standardized topics we can pull for 60+
def who_topic_for(trait, category):
    t = trait.lower()
    if category == "physical_activity":
        return "physical inactivity"
    if "alcohol" in t or "drink" in t:
        return "alcohol use"
    return None


# 30-word-window cues that a synonym is a study-design / sample / clinical-
# history descriptor rather than a reported behaviour of the subjects.
EXCLUDE_CTX = re.compile(
    r"community[-\s]?(?:dwelling|based|residing|living)|population[-\s]?based|"
    r"hospital[-\s]?based|family histor|in the community|"
    r"study (?:sample|population|participants|cohort|setting)|recruit|enroll|"
    r"inclusion criteria|baseline characteristics|disease activity|"
    r"active (?:comparator|surveillance|disease|control)|family (?:practice|medicine)|"
    r"children (?:in|of) the (?:study|cohort|sample)|number of children",
    re.I)
RECOUNT_THRESHOLD = 100  # only re-screen traits whose raw count exceeds this


def topical_count(treg, texts):
    """Count papers with >=1 synonym match that is NOT inside a design/sample/
    history context window (+/- 80 chars ~ 30 words)."""
    n = 0
    for t in texts:
        behavioral = False
        for mt in treg.finditer(t):
            w = t[max(0, mt.start() - 80): mt.end() + 80]
            if not EXCLUDE_CTX.search(w):
                behavioral = True
                break
        if behavioral:
            n += 1
    return n


def build_trait_regex(syns):
    parts = []
    for s in syns:
        if " " in s or "-" in s:
            parts.append(re.escape(s))
        else:
            parts.append(r"\b" + re.escape(s) + r"\w*")  # allow plural/suffix
    return re.compile("|".join(parts), re.I)


def main():
    df = pd.read_csv(LAYER1)
    k = df[(df["extraction_method"] == "keyword") & (df["individual_count"] >= 3)].copy()
    k = k.sort_values("individual_count", ascending=False)

    ap = pd.read_csv(ACADEMIC)
    text = (ap["title"].fillna("") + ". " + ap["abstract"].fillna("")).str.lower()
    long_mask = text.str.contains(LONGEVITY)
    long_text = text[long_mask]
    long_ap = ap[long_mask]
    has_effect = long_ap["stat_odds_ratio"].notna() | long_ap["stat_hazard_ratio"].notna()
    has_pct = long_ap["stat_percentage"].notna()
    control_re = re.compile(r"control|comparison group|non[-\s]?centenarian", re.I)

    rows = []
    for _, r in k.iterrows():
        trait, cat = r["trait"], r["trait_category"]
        # The expanded corpus can surface keyword traits beyond the hand-curated
        # SYNONYMS set; fall back to the trait's own significant words so academic
        # corroboration is still scored (never crash on a new trait).
        syns = SYNONYMS.get(trait) or [w for w in re.split(r"[/()\s]+", trait) if len(w) > 2] or [trait]
        treg = build_trait_regex(syns)
        tmask = long_text.str.contains(treg)
        n_raw = int(tmask.sum())
        # Fix 1: re-screen over-counted traits with a topical-aboutness filter
        if n_raw > RECOUNT_THRESHOLD:
            n_papers = topical_count(treg, long_text[tmask].tolist())
        else:
            n_papers = n_raw
        academically = n_papers >= 2

        # baseline sources
        module = nhanes_module_for(trait, cat)
        who = who_topic_for(trait, cat)
        # corpus control: a trait+longevity paper with an effect stat, a % and
        # a control/comparison mention in its abstract
        cc = bool((tmask & has_effect & has_pct &
                   long_text.str.contains(control_re)).any())

        # Which independent population reference dataset is AVAILABLE to compute
        # the baseline in Step D (infrastructure, not a tier-determiner).
        if module:
            pop_baseline = "nhanes"
        elif who:
            pop_baseline = "who"
        else:
            pop_baseline = ""   # HMD / UN WPP / GWAS carry no lifestyle-trait
                                # prevalence, so they do not anchor these traits
        baseline = pop_baseline or ("corpus_control" if cc else "none")

        # Gold is DEFERRED to Step D (requires a quantified centenarian-vs-
        # population association, not mere dataset presence). Lock-time ceiling
        # is silver. gold_eligible = academically corroborated AND an independent
        # population baseline is available -> the candidate set Step D will test.
        tier = "silver" if academically else "bronze"
        gold_eligible = bool(academically and pop_baseline)

        rows.append(dict(
            trait=trait, trait_category=cat,
            individual_count=int(r["individual_count"]),
            n_supercentenarian=int(r["n_supercentenarian"]),
            n_centenarian=int(r["n_centenarian"]),
            article_mention_count=int(r["article_mention_count"]),
            academic_paper_count_raw=n_raw,
            academic_paper_count=n_papers,
            nhanes_module=module or "",
            baseline_source=baseline,
            corroboration_tier=tier,
            gold_eligible=gold_eligible,
        ))

    out = pd.DataFrame(rows)
    tier_order = {"gold": 0, "silver": 1, "bronze": 2}
    out = out.sort_values(
        by=["corroboration_tier", "individual_count"],
        key=lambda c: c.map(tier_order) if c.name == "corroboration_tier" else c,
        ascending=[True, False])
    out.to_csv(OUT, index=False)

    print(f"locked Tier 1 features: {len(out)}  (searched title+abstract; "
          f"{int(long_mask.sum())} longevity-context papers)\n")

    rec = out[out["academic_paper_count_raw"] > RECOUNT_THRESHOLD]
    print(f"Fix 1 - topical-aboutness recount (raw count > {RECOUNT_THRESHOLD}):")
    print(f"  {'trait':26} {'raw':>5} -> {'topical':>7}  dropped")
    for _, r in rec.sort_values("academic_paper_count_raw", ascending=False).iterrows():
        print(f"  {r['trait']:26} {r['academic_paper_count_raw']:>5} -> "
              f"{r['academic_paper_count']:>7}  -{r['academic_paper_count_raw']-r['academic_paper_count']}")

    print("\ncorroboration_tier breakdown (gold deferred to Step D):")
    for t in ["gold", "silver", "bronze"]:
        print(f"  {t:7} {int((out['corroboration_tier']==t).sum())}")
    print(f"  gold_eligible (silver + population baseline available -> Step D tests these): "
          f"{int(out['gold_eligible'].sum())}")
    print("\nfull table (tier, then individual_count desc):")
    print(out[["trait", "trait_category", "individual_count", "academic_paper_count",
               "nhanes_module", "baseline_source", "corroboration_tier",
               "gold_eligible"]].to_string(index=False))


if __name__ == "__main__":
    main()
