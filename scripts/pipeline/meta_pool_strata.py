"""
Phase 2.9b - STRATIFIED random-effects (DerSimonian-Laird) pooling.

Guardrail (user, 2026-06-01): a pooled estimate may become a model parameter
ONLY if the underlying studies are actually commensurable. So we never pool an
OR with an HR, and we never pool across different contrasts or subject classes.

Stratum key = (biomarker_name, effect_measure, contrast_type, subject_class).
DerSimonian-Laird (pymare) runs per stratum on log-effects. Direction
consistency and I^2 then decide whether the stratum is usable.

contrast_type (rule-based, transparent, stored for audit):
  prognostic_outcome   - biomarker name is itself a death/survival OUTCOME
                         (mortality, survival ...). Pools heterogeneous
                         exposures -> NOT commensurable, directional only.
  prevalence_longlived - OR in a long-lived class (centenarian / nonagenarian /
                         supercentenarian); "feature present in the long-lived".
                         Similarity-relevant -> primary candidate.
  prognostic_mortality - HR for a (non-outcome) biomarker exposure -> the
                         biomarker predicts time-to-event. Supporting/prognostic.
  disease_risk         - OR/RR in a general/elderly sample, non-mortality.
                         Supporting/prognostic.

Outputs:
  data/processed/biomarker_pooled_strata.csv   (one row per stratum)
  data/processed/biomarker_summary.csv         (one row per biomarker, rolled up)
"""
import re
import numpy as np
import pandas as pd
from scipy.stats import norm
from pymare import Dataset
from pymare.estimators import DerSimonianLaird

REF_PATH = "data/processed/centenarian_biomarker_reference.csv"
SUMMARY_PATH = "data/processed/biomarker_summary.csv"
STRATA_PATH = "data/processed/biomarker_pooled_strata.csv"

EFFECT_MEASURE = {"odds_ratio": "OR", "hazard_ratio": "HR", "relative_risk": "RR"}
LONGLIVED = {"centenarian", "nonagenarian", "supercentenarian"}
Z = norm.ppf(0.975)
MORT_RE = re.compile(r"mortalit|surviv|death|fatal|lethal", re.IGNORECASE)

# heterogeneity thresholds
I2_A_MAX = 50.0    # Grade A needs I^2 <= 50
I2_USABLE_MAX = 75.0  # above this a (structurally clean) pool is directional only

ORIGINAL_COLS = [
    "biomarker_name", "n_mentions", "n_independent_sources", "n_countries",
    "countries_sample", "subject_classes_seen", "value_types", "units_seen",
    "median_sample_size", "in_nhanes", "in_gwas",
]


def study_id(row):
    pid = row["pmid"]
    if pd.notna(pid) and str(pid) not in ("", "nan"):
        return f"pmid:{pid}"
    return f"rec:{row['record_id']}"


def contrast_type(name, measure, subject_class):
    if name and MORT_RE.search(str(name)):
        return "prognostic_outcome"
    if measure == "HR":
        return "prognostic_mortality"
    if measure == "OR":
        return "prevalence_longlived" if subject_class in LONGLIVED else "disease_risk"
    return "disease_risk"  # RR


def collapse_to_studies(g):
    """One representative estimate per study: prefer CI-bearing rows, pick the
    one nearest the study's median CI'd value."""
    rows = []
    for sid, s in g.groupby("study_id"):
        ci = s[s["ci_lower"].notna()]
        if len(ci):
            med = ci["value"].median()
            rep = ci.iloc[(ci["value"] - med).abs().argmin()]
            rows.append((sid, rep["value"], rep["ci_lower"], rep["ci_upper"], True))
        else:
            rows.append((sid, s["value"].median(), np.nan, np.nan, False))
    return pd.DataFrame(rows, columns=["study_id", "value", "ci_lower", "ci_upper", "has_ci"])


def dl_pool(studies_ci):
    yi = np.log(studies_ci["value"].to_numpy(float))
    vi = ((np.log(studies_ci["ci_upper"].to_numpy(float)) -
           np.log(studies_ci["ci_lower"].to_numpy(float))) / (2 * Z)) ** 2
    k = len(yi)
    wi = 1.0 / vi
    ybar_fe = np.sum(wi * yi) / np.sum(wi)
    Q = float(np.sum(wi * (yi - ybar_fe) ** 2))
    df = k - 1
    C = np.sum(wi) - np.sum(wi**2) / np.sum(wi)
    tau2 = max(0.0, (Q - df) / C) if C > 0 else 0.0
    I2 = max(0.0, (Q - df) / Q) * 100 if Q > 0 else 0.0
    ds = Dataset(y=yi.reshape(-1, 1), v=vi.reshape(-1, 1))
    fe = DerSimonianLaird().fit_dataset(ds).summary().get_fe_stats()
    mu = float(fe["est"].ravel()[0])
    se = float(fe["se"].ravel()[0])
    ci_l = float(fe["ci_l"].ravel()[0])
    ci_u = float(fe["ci_u"].ravel()[0])
    direction_consistent = bool(np.all(yi > 0) or np.all(yi < 0))
    return dict(pooled_log_effect=mu, se=se, ci_lower=np.exp(ci_l),
                ci_upper=np.exp(ci_u), pooled_OR=np.exp(mu), I_squared=I2,
                tau_squared=tau2, n_ci_bearing_studies=k,
                direction_consistent=direction_consistent)


def grade_and_use(contrast, commensurable, n_ci, I2, direction_consistent, single):
    """Return (evidence_grade, model_use)."""
    if not commensurable:
        return "C", "directional_only"
    # commensurable from here
    if single:  # exactly one study, has CI
        grade = "B"
    elif n_ci >= 3 and I2 <= I2_A_MAX:
        grade = "A"
    elif n_ci >= 2 and I2 <= I2_USABLE_MAX:
        grade = "B"
    else:
        grade = "C"
    if contrast == "prevalence_longlived":
        use = "similarity_primary" if grade in ("A", "B") else "similarity_supporting"
    else:  # prognostic_mortality / disease_risk
        use = "prognostic_supporting" if grade in ("A", "B") else "directional_only"
    return grade, use


def wilson_ci(k, n):
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    d = 1 + Z**2 / n
    c = (p + Z**2 / (2 * n)) / d
    h = (Z * np.sqrt(p * (1 - p) / n + Z**2 / (4 * n**2))) / d
    return (max(0.0, c - h), min(1.0, c + h))


def main():
    ref = pd.read_csv(REF_PATH)
    ref["value"] = pd.to_numeric(ref["value"], errors="coerce")
    ref["ci_lower"] = pd.to_numeric(ref["ci_lower"], errors="coerce")
    ref["ci_upper"] = pd.to_numeric(ref["ci_upper"], errors="coerce")
    ref["study_id"] = ref.apply(study_id, axis=1)
    ref["subject_class"] = ref["subject_class"].fillna("unspecified")

    eff = ref[ref["value_type"].isin(EFFECT_MEASURE) & ref["value"].notna()].copy()
    eff["effect_measure"] = eff["value_type"].map(EFFECT_MEASURE)
    eff["contrast_type"] = [
        contrast_type(n, m, s)
        for n, m, s in zip(eff["biomarker_name"], eff["effect_measure"],
                           eff["subject_class"])
    ]

    strata_rows = []
    keys = ["biomarker_name", "effect_measure", "contrast_type", "subject_class"]
    for (name, measure, contrast, sclass), g in eff.groupby(keys):
        studies = collapse_to_studies(g)
        n_studies = len(studies)
        ci = studies[studies["has_ci"]]
        n_ci = len(ci)
        row = dict(biomarker_name=name, effect_measure=measure,
                   contrast_type=contrast, subject_class=sclass,
                   n_studies=n_studies, n_ci_bearing_studies=n_ci,
                   pooled_log_effect=np.nan, se=np.nan, pooled_OR=np.nan,
                   ci_lower=np.nan, ci_upper=np.nan, I_squared=np.nan,
                   tau_squared=np.nan, direction_consistent=pd.NA,
                   commensurable_pool=False, evidence_grade="C",
                   model_use="directional_only")

        structurally_ok = contrast != "prognostic_outcome"  # outcome = mixed exposures

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
            commensurable = structurally_ok
            row["commensurable_pool"] = commensurable
            row["evidence_grade"], row["model_use"] = grade_and_use(
                contrast, commensurable, 1, 0.0, True, single=True)
        else:
            # point estimate(s) only, no CI -> no variance, directional
            row["evidence_grade"], row["model_use"] = "C", "directional_only"
            row["pooled_OR"] = studies["value"].median()
        strata_rows.append(row)

    strata = pd.DataFrame(strata_rows)
    strata = strata.sort_values(
        ["commensurable_pool", "n_ci_bearing_studies", "I_squared"],
        ascending=[False, False, True])
    col_order = ["biomarker_name", "effect_measure", "contrast_type",
                 "subject_class", "pooled_log_effect", "se", "pooled_OR",
                 "ci_lower", "ci_upper", "I_squared", "tau_squared",
                 "n_studies", "n_ci_bearing_studies", "direction_consistent",
                 "commensurable_pool", "evidence_grade", "model_use"]
    strata = strata[col_order]
    strata.to_csv(STRATA_PATH, index=False)

    # ---------- roll up into biomarker_summary.csv ----------
    summ = pd.read_csv(SUMMARY_PATH)
    if "evidence_grade_legacy" not in summ.columns:
        summ["evidence_grade_legacy"] = summ["evidence_grade"]
    summ = summ[[c for c in ORIGINAL_COLS if c in summ.columns]
                + ["evidence_grade_legacy"]].copy()

    n_corpus = ref["study_id"].nunique()
    use_priority = {"similarity_primary": 0, "prognostic_supporting": 1,
                    "similarity_supporting": 2, "directional_only": 3}
    grade_rank = {"A": 0, "B": 1, "C": 2}

    addcols = {c: [] for c in [
        "n_strata", "n_commensurable_strata", "primary_effect_measure",
        "primary_contrast_type", "primary_subject_class", "primary_pooled_OR",
        "primary_ci_lower", "primary_ci_upper", "primary_I_squared",
        "primary_tau_squared", "primary_n_studies", "primary_n_ci_studies",
        "evidence_grade", "model_use", "base_rate", "base_rate_CI_lower",
        "base_rate_CI_upper"]}

    for _, b in summ.iterrows():
        name = b["biomarker_name"]
        st = strata[strata["biomarker_name"] == name]
        k_src = int(b["n_independent_sources"])
        bl, bu = wilson_ci(k_src, n_corpus)
        rec = {c: np.nan for c in addcols}
        rec["base_rate"] = k_src / n_corpus if n_corpus else np.nan
        rec["base_rate_CI_lower"], rec["base_rate_CI_upper"] = bl, bu
        rec["n_strata"] = len(st)
        rec["n_commensurable_strata"] = int(st["commensurable_pool"].sum()) if len(st) else 0

        cand = st[st["commensurable_pool"]].copy()
        if len(cand):
            cand["_u"] = cand["model_use"].map(use_priority)
            cand["_g"] = cand["evidence_grade"].map(grade_rank)
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
            rec["evidence_grade"] = "C"
            rec["model_use"] = "qualitative_baserate" if len(st) == 0 else "directional_only"

        for c in addcols:
            addcols[c].append(rec[c])

    for c, v in addcols.items():
        summ[c] = v
    for c in ["n_strata", "n_commensurable_strata", "primary_n_studies",
              "primary_n_ci_studies"]:
        summ[c] = summ[c].astype("Int64")
    summ.to_csv(SUMMARY_PATH, index=False)

    # ---------------- report ----------------
    print(f"corpus denominator (distinct studies): {n_corpus}")
    print(f"total strata: {len(strata)} | commensurable: {int(strata['commensurable_pool'].sum())}")
    print("\ncontrast_type distribution (all strata):")
    print(strata["contrast_type"].value_counts().to_string())
    print("\nbiomarker-level evidence_grade (rolled up):")
    print("  " + "  ".join(f"{g}={int((summ['evidence_grade']==g).sum())}"
                           for g in ["A", "B", "C"]))
    print("\nbiomarker-level model_use:")
    print(summ["model_use"].value_counts().to_string())
    return strata, summ


if __name__ == "__main__":
    main()
