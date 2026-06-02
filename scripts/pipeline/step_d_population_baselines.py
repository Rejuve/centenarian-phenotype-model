"""
Step D — Population baselines & trait associations (NHANES 60+).

For each gold_eligible Tier-1 trait with an NHANES baseline, compute the
weighted population prevalence among adults 60+ (NHANES 2017-2018), then compare
to the centenarian documentation rate from layer1_trait_frequency.csv.

Also restructures the ambiguous "smoked" trait into smoking_status (never/former/
current) — the only smoking detail the corpus actually supports (amount/pack-years
/cessation are essentially absent; see scripts/analysis/smoking_snippets.py).

Outputs:
  data/processed/step_d_population_baselines.csv   (one row per NHANES indicator)
  data/processed/step_d_trait_associations.csv     (centenarian vs population)

IMPORTANT CAVEAT (documentation bias): the centenarian "prevalence" is
individual_count / total_named_individuals — a *documentation* rate (the trait was
mentioned), NOT a measured prevalence. Absence of mention != absence of trait, so
absolute prevalence_ratios are biased downward and are NOT directly interpretable
as biological enrichment. The relative RANKING across traits is the usable signal.

Run from the project root:  python scripts/pipeline/step_d_population_baselines.py
"""
import math
import numpy as np
import pandas as pd

RAW = "data/raw/datasets"
LAYER1 = "data/processed/layer1_trait_frequency.csv"
LOCK = "data/processed/tier1_features_locked.csv"
OUT_BASE = "data/processed/step_d_population_baselines.csv"
OUT_ASSOC = "data/processed/step_d_trait_associations.csv"
SENTINEL = 5.397605346934028e-79
TOTAL_NAMED = 3640           # distinct named centenarians in the regenerated corpus
CYCLE = "2017-2018"


def wilson(p, n, z=1.96):
    if n == 0 or p is None or (isinstance(p, float) and math.isnan(p)):
        return (np.nan, np.nan)
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def wprev(pos, valid, w):
    """Weighted prevalence among valid responders; returns dict of stats."""
    pos = pos & valid
    n_unw = int(valid.sum())
    wv = float((w * valid).sum())
    p = float((w * pos).sum() / wv) if wv > 0 else np.nan
    lo, hi = wilson(p, n_unw)
    return dict(n_unweighted=n_unw, n_weighted_60plus=round(wv),
                prevalence_pct=round(100 * p, 2) if not math.isnan(p) else np.nan,
                ci_lower=round(100 * lo, 2) if not math.isnan(lo) else np.nan,
                ci_upper=round(100 * hi, 2) if not math.isnan(hi) else np.nan)


def main():
    demo = pd.read_csv(f"{RAW}/nhanes_demographics.csv")
    demo = demo[["SEQN", "RIDAGEYR", "RIAGENDR", "WTMEC2YR"]]
    sm = pd.read_csv(f"{RAW}/nhanes_smoking.csv")
    al = pd.read_csv(f"{RAW}/nhanes_alcohol.csv")
    pa = pd.read_csv(f"{RAW}/nhanes_physical_activity.csv")
    sl = pd.read_csv(f"{RAW}/nhanes_sleep.csv")

    df = demo
    for x in (sm, al, pa, sl):
        df = df.merge(x.drop(columns=[c for c in x.columns
                      if c in ("nhanes_file", "nhanes_cycle", "dataset_source",
                               "dataset_type", "license")], errors="ignore"),
                      on="SEQN", how="left")
    df = df.replace(SENTINEL, 0.0)
    df = df[(df["RIDAGEYR"] >= 60) & df["WTMEC2YR"].notna() & (df["WTMEC2YR"] > 0)].copy()
    w = df["WTMEC2YR"]

    # ---- NHANES indicator definitions: name -> (module, var_note, pos, valid) ----
    smq020 = df["SMQ020"]; smq040 = df["SMQ040"]
    smk_valid = smq020.isin([1, 2])
    alq111 = df["ALQ111"]; alq121 = df["ALQ121"]
    alc_valid = alq111.isin([1, 2])
    drinks = (alq121 > 0)
    paq650 = df["PAQ650"]; paq665 = df["PAQ665"]; paq635 = df["PAQ635"]
    pa_valid = paq650.isin([1, 2]) | paq665.isin([1, 2])
    sld = df["SLD012"]

    INDICATORS = {
        "smoking_status_never":   ("nhanes_smoking", "SMQ020==2", smq020.eq(2), smk_valid),
        "smoking_status_former":  ("nhanes_smoking", "SMQ020==1 & SMQ040==3", smq020.eq(1) & smq040.eq(3), smk_valid),
        "smoking_status_current": ("nhanes_smoking", "SMQ020==1 & SMQ040 in (1,2)", smq020.eq(1) & smq040.isin([1, 2]), smk_valid),
        "pa_recreational_mvpa":   ("nhanes_physical_activity", "PAQ650==1 | PAQ665==1", paq650.eq(1) | paq665.eq(1), pa_valid),
        "pa_vigorous_recreational": ("nhanes_physical_activity", "PAQ650==1", paq650.eq(1), paq650.isin([1, 2])),
        "pa_walk_bike_transport": ("nhanes_physical_activity", "PAQ635==1", paq635.eq(1), paq635.isin([1, 2])),
        "alcohol_current_drinker": ("nhanes_alcohol", "ALQ121>0 (drank past yr)", drinks, alc_valid),
        "alcohol_none_past_year": ("nhanes_alcohol", "ALQ121==0 or never", ~drinks, alc_valid),
        "sleep_7_9_hours":        ("nhanes_sleep", "SLD012 in [7,9]", sld.between(7, 9), sld.notna()),
    }
    base_rows = []
    base_stats = {}
    for name, (mod, note, pos, valid) in INDICATORS.items():
        st = wprev(pos, valid, w)
        base_stats[name] = st
        base_rows.append(dict(indicator=name, nhanes_module=mod, nhanes_variable=note,
                              survey_cycle=CYCLE, **st))
    pd.DataFrame(base_rows).to_csv(OUT_BASE, index=False)

    # ---- trait -> NHANES indicator + centenarian count ----
    # Two comparison methods:
    #  status_composition (VALID): the corpus documents the CATEGORY (smoking/
    #    alcohol status), so centenarian prevalence = count / documented-in-domain,
    #    apples-to-apples with the NHANES within-domain composition. Eligible for gold.
    #  mention_rate (DOCUMENTATION-BIASED): a profile only mentions e.g. "dancing"
    #    when notable; absence != inactive. centenarian "prevalence" = count /
    #    total_named is a documentation rate, NOT comparable to a measured NHANES
    #    prevalence. Reported for completeness but NEVER gold.
    lay = pd.read_csv(LAYER1).set_index("trait")["individual_count"].to_dict()
    # documented-in-domain totals (smoking from scripts/analysis/smoking_snippets.py:
    # never 75 / former 14 / current 6; alcohol from layer1 drinks 71 + none 23)
    SMK = {"never": 75, "former": 14, "current": 6}; SMK_DOC = sum(SMK.values())
    ALC_DOC = lay.get("drinks alcohol (moderate)", 0) + lay.get("no alcohol", 0)
    # trait, indicator, cent_count, cent_denom, method, expected_direction
    MAP = [
        ("smoking_status_never",  "smoking_status_never",  SMK["never"],  SMK_DOC, "status_composition", "positive"),
        ("smoking_status_former", "smoking_status_former", SMK["former"], SMK_DOC, "status_composition", "context_dependent"),
        ("smoking_status_current","smoking_status_current",SMK["current"],SMK_DOC, "status_composition", "negative"),
        ("drinks alcohol (moderate)", "alcohol_current_drinker", lay.get("drinks alcohol (moderate)", 0), ALC_DOC, "status_composition", "context_dependent"),
        ("no alcohol",            "alcohol_none_past_year", lay.get("no alcohol", 0), ALC_DOC, "status_composition", "context_dependent"),
        ("staying active",        "pa_recreational_mvpa",  lay.get("staying active", 0), TOTAL_NAMED, "mention_rate", "positive"),
        ("regular exercise",      "pa_recreational_mvpa",  lay.get("regular exercise", 0), TOTAL_NAMED, "mention_rate", "positive"),
        ("gardening",             "pa_recreational_mvpa",  lay.get("gardening", 0), TOTAL_NAMED, "mention_rate", "positive"),
        ("dancing",               "pa_recreational_mvpa",  lay.get("dancing", 0), TOTAL_NAMED, "mention_rate", "positive"),
        ("cycling",               "pa_recreational_mvpa",  lay.get("cycling", 0), TOTAL_NAMED, "mention_rate", "positive"),
        ("swimming",              "pa_recreational_mvpa",  lay.get("swimming", 0), TOTAL_NAMED, "mention_rate", "positive"),
        ("running/marathon",      "pa_vigorous_recreational", lay.get("running/marathon", 0), TOTAL_NAMED, "mention_rate", "positive"),
        ("walking daily",         "pa_walk_bike_transport", lay.get("walking daily", 0), TOTAL_NAMED, "mention_rate", "positive"),
        ("good sleep",            "sleep_7_9_hours",       lay.get("good sleep", 0), TOTAL_NAMED, "mention_rate", "positive"),
        ("naps",                  None,                    lay.get("naps", 0), TOTAL_NAMED, "mention_rate", "positive"),
    ]

    arows = []
    for trait, ind, c_count, c_denom, method, exp_dir in MAP:
        cp = c_count / c_denom if c_denom else np.nan
        biased = (method == "mention_rate")
        if ind is None or ind not in base_stats or math.isnan(base_stats[ind]["prevalence_pct"]):
            arows.append(dict(trait=trait, nhanes_indicator=ind or "(none)", method=method,
                              centenarian_count=c_count, centenarian_denominator=c_denom,
                              centenarian_prevalence_pct=round(100 * cp, 2) if not math.isnan(cp) else np.nan,
                              population_prevalence_pct=np.nan, prevalence_ratio=np.nan,
                              log_odds_ratio=np.nan, direction="unavailable",
                              expected_direction=exp_dir, documentation_biased=biased,
                              association_quantified=False, gold=False))
            continue
        pp = base_stats[ind]["prevalence_pct"] / 100.0
        ratio = cp / pp if pp > 0 else np.nan
        cp_a = min(max(cp, 1e-6), 1 - 1e-6); pp_a = min(max(pp, 1e-6), 1 - 1e-6)
        lor = math.log((cp_a / (1 - cp_a)) / (pp_a / (1 - pp_a)))
        direction = "enriched" if ratio > 1.1 else ("depleted" if ratio < 0.9 else "neutral")
        # Only a VALID (non-documentation-biased) quantified association with a
        # determinate direction earns gold.
        gold = (not biased) and direction != "neutral"
        arows.append(dict(trait=trait, nhanes_indicator=ind, method=method,
                          centenarian_count=c_count, centenarian_denominator=c_denom,
                          centenarian_prevalence_pct=round(100 * cp, 2),
                          population_prevalence_pct=round(100 * pp, 2),
                          prevalence_ratio=round(ratio, 3) if not math.isnan(ratio) else np.nan,
                          log_odds_ratio=round(lor, 3),
                          direction=direction, expected_direction=exp_dir,
                          documentation_biased=biased, association_quantified=True, gold=gold))
    adf = pd.DataFrame(arows)
    adf.to_csv(OUT_ASSOC, index=False)

    pd.set_option("display.width", 200)
    print(f"Wrote {OUT_BASE} ({len(base_rows)} indicators) and {OUT_ASSOC} ({len(adf)} traits)\n")
    print("=== POPULATION BASELINES (NHANES 60+, WTMEC2YR weighted, 2017-2018) ===")
    print(pd.DataFrame(base_rows)[["indicator", "nhanes_variable", "n_unweighted",
          "prevalence_pct", "ci_lower", "ci_upper"]].to_string(index=False))
    print("\n=== VALID associations — status_composition (apples-to-apples, gold-eligible) ===")
    v = adf[adf["method"] == "status_composition"].sort_values("prevalence_ratio", ascending=False)
    print(v[["trait", "centenarian_prevalence_pct", "population_prevalence_pct",
             "prevalence_ratio", "log_odds_ratio", "direction", "expected_direction", "gold"]].to_string(index=False))
    print("\n=== mention_rate traits — DOCUMENTATION-BIASED (ranking only, never gold) ===")
    m = adf[adf["method"] == "mention_rate"].sort_values("prevalence_ratio", ascending=False, na_position="last")
    print(m[["trait", "centenarian_prevalence_pct", "population_prevalence_pct",
             "prevalence_ratio", "direction"]].to_string(index=False))
    print(f"\ngold conferred: {int(adf['gold'].sum())} (from valid status_composition only) | "
          f"naps unavailable (no NHANES nap variable)")


if __name__ == "__main__":
    main()
