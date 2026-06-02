"""
Promote canonical biomarker names into the production files.

Renaming alone would create incoherent duplicate stratum keys (e.g. `diabetes`
and `diabetes mellitus dm` are both OR/prevalence_longlived/centenarian), so we
RE-POOL on the canonical key: studies that only differed by name string are now
combined and DerSimonian-Laird is recomputed. This can legitimately form new
multi-study pools.

Writes (overwrites):
  data/processed/biomarker_pooled_strata.csv   (canonical names, re-pooled)
  data/processed/biomarker_summary.csv         (canonical rollup)
The raw->canonical audit trail lives in biomarker_pooled_strata_normalized.csv.
"""
import numpy as np
import pandas as pd

from normalize_strata_names import canonicalize, simple_snake, DROP_RAW
from meta_pool_strata import (
    study_id, contrast_type, EFFECT_MEASURE, collapse_to_studies, dl_pool,
    grade_and_use, wilson_ci, I2_USABLE_MAX,
)

REF_PATH = "data/processed/centenarian_biomarker_reference.csv"
SUMMARY_PATH = "data/processed/biomarker_summary.csv"
STRATA_PATH = "data/processed/biomarker_pooled_strata.csv"
GRADE_RANK = {"A": 0, "B": 1, "C": 2}
# canonical terms excluded from the feature set entirely (user, 2026-06-01):
# depression has no clean source yet and should not appear as a feature.
DROP_CANONICAL = {"depression"}


def canonical_name(raw):
    """Reviewed dictionary match -> canonical; otherwise just snake_case the
    original (no unreviewed semantic stripping of qualitative biomarkers)."""
    canon, how = canonicalize(str(raw))
    return canon if how.startswith("matched") else simple_snake(str(raw))


def best_grade(series):
    g = [x for x in series if isinstance(x, str)]
    return min(g, key=lambda x: GRADE_RANK.get(x, 9)) if g else "C"


def join_unique(series, sep="|", cap=None):
    vals = sorted({str(v).strip() for v in series.dropna() if str(v).strip()})
    if cap:
        vals = vals[:cap]
    return sep.join(vals)


def main():
    ref = pd.read_csv(REF_PATH)
    ref["value"] = pd.to_numeric(ref["value"], errors="coerce")
    ref["ci_lower"] = pd.to_numeric(ref["ci_lower"], errors="coerce")
    ref["ci_upper"] = pd.to_numeric(ref["ci_upper"], errors="coerce")
    ref["study_id"] = ref.apply(study_id, axis=1)
    ref["subject_class"] = ref["subject_class"].fillna("unspecified")

    # drop the agreed raw names, then canonicalize, then drop excluded canonicals
    ref = ref[~ref["biomarker_name"].isin(DROP_RAW)].copy()
    ref["canonical"] = ref["biomarker_name"].map(canonical_name)
    ref = ref[~ref["canonical"].isin(DROP_CANONICAL)].copy()

    n_corpus = ref["study_id"].nunique()

    # ---------------- re-pool strata on the canonical key ----------------
    eff = ref[ref["value_type"].isin(EFFECT_MEASURE) & ref["value"].notna()].copy()
    eff["effect_measure"] = eff["value_type"].map(EFFECT_MEASURE)
    eff["contrast_type"] = [
        contrast_type(n, m, s) for n, m, s in
        zip(eff["canonical"], eff["effect_measure"], eff["subject_class"])
    ]

    rows = []
    for (name, measure, contrast, sclass), g in eff.groupby(
            ["canonical", "effect_measure", "contrast_type", "subject_class"]):
        studies = collapse_to_studies(g)
        ci = studies[studies["has_ci"]]
        n_ci = len(ci)
        row = dict(biomarker_name=name, effect_measure=measure,
                   contrast_type=contrast, subject_class=sclass,
                   n_studies=len(studies), n_ci_bearing_studies=n_ci,
                   pooled_log_effect=np.nan, se=np.nan, pooled_OR=np.nan,
                   ci_lower=np.nan, ci_upper=np.nan, I_squared=np.nan,
                   tau_squared=np.nan, direction_consistent=pd.NA,
                   commensurable_pool=False, evidence_grade="C",
                   model_use="directional_only")
        structurally_ok = contrast != "prognostic_outcome"

        if n_ci >= 2:
            p = dl_pool(ci)
            row.update({k: p[k] for k in
                        ["pooled_log_effect", "se", "pooled_OR", "ci_lower",
                         "ci_upper", "I_squared", "tau_squared",
                         "direction_consistent"]})
            commensurable = (structurally_ok and p["direction_consistent"]
                             and p["I_squared"] <= I2_USABLE_MAX)
            row["commensurable_pool"] = commensurable
            row["evidence_grade"], row["model_use"] = grade_and_use(
                contrast, commensurable, n_ci, p["I_squared"],
                p["direction_consistent"], single=False)
        elif n_ci == 1:
            s = ci.iloc[0]
            row.update(pooled_OR=s["value"], ci_lower=s["ci_lower"],
                       ci_upper=s["ci_upper"],
                       pooled_log_effect=np.log(s["value"]),
                       direction_consistent=True)
            row["commensurable_pool"] = structurally_ok
            row["evidence_grade"], row["model_use"] = grade_and_use(
                contrast, structurally_ok, 1, 0.0, True, single=True)
        else:
            row["pooled_OR"] = studies["value"].median()
        rows.append(row)

    strata = pd.DataFrame(rows).sort_values(
        ["commensurable_pool", "n_ci_bearing_studies", "I_squared"],
        ascending=[False, False, True])
    col_order = ["biomarker_name", "effect_measure", "contrast_type",
                 "subject_class", "pooled_log_effect", "se", "pooled_OR",
                 "ci_lower", "ci_upper", "I_squared", "tau_squared",
                 "n_studies", "n_ci_bearing_studies", "direction_consistent",
                 "commensurable_pool", "evidence_grade", "model_use"]
    strata = strata[col_order]
    strata.to_csv(STRATA_PATH, index=False)

    # ---------------- regenerate canonical biomarker_summary ----------------
    old = pd.read_csv(SUMMARY_PATH)
    if "evidence_grade_legacy" not in old.columns:
        old["evidence_grade_legacy"] = old["evidence_grade"]
    old = old[~old["biomarker_name"].isin(DROP_RAW)].copy()
    old["canonical"] = old["biomarker_name"].map(canonical_name)
    flags = old.groupby("canonical").agg(
        in_nhanes=("in_nhanes", "any"),
        in_gwas=("in_gwas", "any"),
        evidence_grade_legacy=("evidence_grade_legacy", best_grade),
    )

    use_priority = {"similarity_primary": 0, "prognostic_supporting": 1,
                    "similarity_supporting": 2, "directional_only": 3}
    out = []
    for name, g in ref.groupby("canonical"):
        k_src = g["study_id"].nunique()
        bl, bu = wilson_ci(k_src, n_corpus)
        rec = dict(
            biomarker_name=name,
            n_mentions=len(g),
            n_independent_sources=k_src,
            n_countries=g["population_country"].dropna().nunique(),
            countries_sample=join_unique(g["population_country"], cap=6),
            subject_classes_seen=join_unique(g["subject_class"]),
            value_types=join_unique(g["value_type"]),
            units_seen=join_unique(g["unit"]),
            median_sample_size=float(np.nan_to_num(
                pd.to_numeric(g["sample_size"], errors="coerce").median())),
            in_nhanes=bool(flags.loc[name, "in_nhanes"]) if name in flags.index else False,
            in_gwas=bool(flags.loc[name, "in_gwas"]) if name in flags.index else False,
            evidence_grade_legacy=flags.loc[name, "evidence_grade_legacy"] if name in flags.index else "C",
            base_rate=k_src / n_corpus if n_corpus else np.nan,
            base_rate_CI_lower=bl, base_rate_CI_upper=bu,
        )
        st = strata[strata["biomarker_name"] == name]
        rec["n_strata"] = len(st)
        rec["n_commensurable_strata"] = int(st["commensurable_pool"].sum()) if len(st) else 0
        cand = st[st["commensurable_pool"]].copy()
        if len(cand):
            cand["_u"] = cand["model_use"].map(use_priority)
            cand["_g"] = cand["evidence_grade"].map(GRADE_RANK)
            cand = cand.sort_values(["_u", "_g", "n_ci_bearing_studies"],
                                    ascending=[True, True, False])
            p = cand.iloc[0]
            rec.update(
                primary_effect_measure=p["effect_measure"],
                primary_contrast_type=p["contrast_type"],
                primary_subject_class=p["subject_class"],
                primary_pooled_OR=p["pooled_OR"],
                primary_ci_lower=p["ci_lower"], primary_ci_upper=p["ci_upper"],
                primary_I_squared=p["I_squared"],
                primary_tau_squared=p["tau_squared"],
                primary_n_studies=p["n_studies"],
                primary_n_ci_studies=p["n_ci_bearing_studies"],
                evidence_grade=p["evidence_grade"], model_use=p["model_use"])
        else:
            for c in ["primary_effect_measure", "primary_contrast_type",
                      "primary_subject_class", "primary_pooled_OR",
                      "primary_ci_lower", "primary_ci_upper", "primary_I_squared",
                      "primary_tau_squared", "primary_n_studies",
                      "primary_n_ci_studies"]:
                rec[c] = np.nan
            rec["evidence_grade"] = "C"
            rec["model_use"] = "qualitative_baserate" if len(st) == 0 else "directional_only"
        out.append(rec)

    summ = pd.DataFrame(out)
    col_seq = ["biomarker_name", "n_mentions", "n_independent_sources",
               "n_countries", "countries_sample", "subject_classes_seen",
               "value_types", "units_seen", "median_sample_size", "in_nhanes",
               "in_gwas", "evidence_grade_legacy", "n_strata",
               "n_commensurable_strata", "primary_effect_measure",
               "primary_contrast_type", "primary_subject_class",
               "primary_pooled_OR", "primary_ci_lower", "primary_ci_upper",
               "primary_I_squared", "primary_tau_squared", "primary_n_studies",
               "primary_n_ci_studies", "evidence_grade", "model_use",
               "base_rate", "base_rate_CI_lower", "base_rate_CI_upper"]
    summ = summ[col_seq].sort_values("n_independent_sources", ascending=False)
    for c in ["n_strata", "n_commensurable_strata", "primary_n_studies",
              "primary_n_ci_studies"]:
        summ[c] = summ[c].astype("Int64")
    summ.to_csv(SUMMARY_PATH, index=False)

    # ---------------- report ----------------
    print(f"corpus denominator (distinct studies): {n_corpus}")
    print(f"strata rows: {len(strata)} | commensurable: {int(strata['commensurable_pool'].sum())}")
    pools = strata[(strata['commensurable_pool']) & (strata['n_ci_bearing_studies'] >= 2)]
    print(f"true multi-study pools (>=2 commensurable CI studies): {len(pools)}")
    print("\nCANONICAL FEATURE COUNT")
    print(f"  total canonical biomarkers : {len(summ)}  (was 421 raw)")
    print(f"  by evidence_grade          : " +
          "  ".join(f"{gd}={int((summ['evidence_grade']==gd).sum())}" for gd in 'ABC'))
    print("  by model_use:")
    for k, v in summ["model_use"].value_counts().items():
        print(f"    {k:24} {v}")
    print("\nTRUE MULTI-STUDY POOLS (canonical):")
    for _, r in pools.sort_values("I_squared").iterrows():
        print(f"  {r['biomarker_name'][:24]:25} {r['effect_measure']} {r['contrast_type'][:20]:21} "
              f"{r['subject_class'][:12]:13} OR {r['pooled_OR']:.2f} "
              f"({r['ci_lower']:.2f}-{r['ci_upper']:.2f}) I2={r['I_squared']:.0f}% "
              f"n={r['n_ci_bearing_studies']} {r['evidence_grade']}")
    return strata, summ


if __name__ == "__main__":
    main()
