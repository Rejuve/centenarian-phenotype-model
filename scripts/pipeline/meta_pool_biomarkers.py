"""
Phase 2.9 - Random-effects (DerSimonian-Laird) meta-analytic pooling of
biomarker OR/HR/RR effects, replacing the hand-assigned A/B/C weight
multipliers with statistically grounded estimates + heterogeneity.

Inputs
  data/processed/centenarian_biomarker_reference.csv  (per-mention; now carries
      ci_lower/ci_upper from extract_biomarker_cis.py)
  data/processed/biomarker_summary.csv                (one row per biomarker)

For each biomarker:
  * >=2 studies with OR/HR + CI  -> DerSimonian-Laird pooled estimate
        (pooled_OR, pooled_CI_lower/upper, I_squared, tau_squared). [primary]
  * exactly 1 study with CI      -> reported OR/HR + its CI (single_*).
  * has effect value(s) but no CI-> recorded, but no usable variance (no pool).
  * no numeric effect (qualitative)-> base-rate presence feature with Wilson CI.

One estimate per study: multiple correlated effects reported in the same PMID
are collapsed to the median-value CI row so a single paper counts once.

evidence_grade is recomputed as a human-readable label only:
  A = pooled from 3+ studies with narrow CI (upper/lower ratio <= 3)
  B = pooled from 2 studies, OR a single study with a CI, OR pooled-3+ but wide
  C = qualitative only / no study reports a usable CI
The model consumes the numeric statistics, not the letter.
"""
import numpy as np
import pandas as pd
from scipy.stats import norm
from pymare import Dataset
from pymare.estimators import DerSimonianLaird

REF_PATH = "data/processed/centenarian_biomarker_reference.csv"
SUMMARY_PATH = "data/processed/biomarker_summary.csv"
EFFECT_TYPES = {"odds_ratio", "hazard_ratio", "relative_risk"}
Z = norm.ppf(0.975)  # 1.959964
NARROW_CI_RATIO = 3.0  # pooled CI upper/lower <= this -> "narrow"


def study_id(row):
    """Stable per-study key: PMID when present, else the source record_id."""
    pid = row["pmid"]
    if pd.notna(pid) and str(pid) not in ("", "nan"):
        return f"pmid:{pid}"
    return f"rec:{row['record_id']}"


def collapse_to_studies(g):
    """One representative effect estimate per study. Prefer rows with a CI;
    among those pick the one whose value is the study's median CI'd value."""
    out = []
    for sid, s in g.groupby("study_id"):
        ci = s[s["ci_lower"].notna()].copy()
        if len(ci):
            med = ci["value"].median()
            rep = ci.iloc[(ci["value"] - med).abs().argmin()]
            out.append((sid, rep["value"], rep["ci_lower"], rep["ci_upper"], True))
        else:
            out.append((sid, s["value"].median(), np.nan, np.nan, False))
    return pd.DataFrame(out, columns=["study_id", "value", "ci_lower", "ci_upper", "has_ci"])


def dl_pool(studies):
    """DerSimonian-Laird on log scale. Returns dict of pooled stats."""
    s = studies[studies["has_ci"]].copy()
    yi = np.log(s["value"].to_numpy(dtype=float))
    vi = ((np.log(s["ci_upper"].to_numpy(float)) -
           np.log(s["ci_lower"].to_numpy(float))) / (2 * Z)) ** 2
    k = len(yi)

    # manual Q / I^2 / tau^2 (DL)
    wi = 1.0 / vi
    ybar_fe = np.sum(wi * yi) / np.sum(wi)
    Q = float(np.sum(wi * (yi - ybar_fe) ** 2))
    df = k - 1
    C = np.sum(wi) - np.sum(wi ** 2) / np.sum(wi)
    tau2 = max(0.0, (Q - df) / C) if C > 0 else 0.0
    I2 = max(0.0, (Q - df) / Q) * 100 if Q > 0 else 0.0

    # pooled random-effects estimate via pymare (cross-checks the math)
    ds = Dataset(y=yi.reshape(-1, 1), v=vi.reshape(-1, 1))
    fe = DerSimonianLaird().fit_dataset(ds).summary().get_fe_stats()
    mu = float(fe["est"].ravel()[0])
    ci_l = float(fe["ci_l"].ravel()[0])
    ci_u = float(fe["ci_u"].ravel()[0])
    return {
        "pooled_OR": np.exp(mu),
        "pooled_CI_lower": np.exp(ci_l),
        "pooled_CI_upper": np.exp(ci_u),
        "I_squared": I2,
        "tau_squared": tau2,
        "Q": Q,
        "n_pooled": k,
    }


def wilson_ci(k, n):
    """Wilson 95% interval for a proportion."""
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    denom = 1 + Z**2 / n
    centre = (p + Z**2 / (2 * n)) / denom
    half = (Z * np.sqrt(p * (1 - p) / n + Z**2 / (4 * n**2))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def main():
    ref = pd.read_csv(REF_PATH)
    ref["value"] = pd.to_numeric(ref["value"], errors="coerce")
    ref["ci_lower"] = pd.to_numeric(ref["ci_lower"], errors="coerce")
    ref["ci_upper"] = pd.to_numeric(ref["ci_upper"], errors="coerce")
    ref["study_id"] = ref.apply(study_id, axis=1)

    summ = pd.read_csv(SUMMARY_PATH)
    if "evidence_grade_legacy" not in summ.columns:
        summ["evidence_grade_legacy"] = summ["evidence_grade"]

    # corpus denominator for base-rate presence features
    n_corpus = ref["study_id"].nunique()

    eff = ref[ref["value_type"].isin(EFFECT_TYPES) & ref["value"].notna()].copy()

    new_cols = {c: [] for c in [
        "pooled_OR", "pooled_CI_lower", "pooled_CI_upper", "I_squared",
        "tau_squared", "single_OR", "single_CI_lower", "single_CI_upper",
        "n_effect_studies", "n_studies_with_ci", "n_pooled", "effect_model",
        "base_rate", "base_rate_CI_lower", "base_rate_CI_upper",
        "evidence_grade",
    ]}

    for _, brow in summ.iterrows():
        name = brow["biomarker_name"]
        g = eff[eff["biomarker_name"] == name]
        rec = {k: np.nan for k in new_cols}

        # base-rate presence feature (every biomarker gets one)
        k_src = int(brow["n_independent_sources"])
        bl, bu = wilson_ci(k_src, n_corpus)
        rec["base_rate"] = k_src / n_corpus if n_corpus else np.nan
        rec["base_rate_CI_lower"], rec["base_rate_CI_upper"] = bl, bu

        if len(g) == 0:
            rec["n_effect_studies"] = 0
            rec["n_studies_with_ci"] = 0
            rec["n_pooled"] = 0
            rec["effect_model"] = "qualitative_baserate"
            rec["evidence_grade"] = "C"
        else:
            studies = collapse_to_studies(g)
            n_studies = len(studies)
            n_ci = int(studies["has_ci"].sum())
            rec["n_effect_studies"] = n_studies
            rec["n_studies_with_ci"] = n_ci

            if n_ci >= 2:
                p = dl_pool(studies)
                rec.update({k: p[k] for k in
                            ["pooled_OR", "pooled_CI_lower", "pooled_CI_upper",
                             "I_squared", "tau_squared"]})
                rec["n_pooled"] = p["n_pooled"]
                rec["effect_model"] = "pooled_DL"
                ratio = p["pooled_CI_upper"] / p["pooled_CI_lower"]
                if p["n_pooled"] >= 3 and ratio <= NARROW_CI_RATIO:
                    rec["evidence_grade"] = "A"
                else:
                    rec["evidence_grade"] = "B"
            elif n_ci == 1:
                s = studies[studies["has_ci"]].iloc[0]
                rec["single_OR"] = s["value"]
                rec["single_CI_lower"] = s["ci_lower"]
                rec["single_CI_upper"] = s["ci_upper"]
                rec["n_pooled"] = 0
                rec["effect_model"] = "single_study"
                rec["evidence_grade"] = "B"
            else:
                # has point estimate(s) but no recoverable CI -> no usable variance
                rec["n_pooled"] = 0
                rec["effect_model"] = "point_no_ci"
                rec["evidence_grade"] = "C"

        for k in new_cols:
            new_cols[k].append(rec[k])

    for k, v in new_cols.items():
        summ[k] = v

    # tidy dtypes
    for c in ["n_effect_studies", "n_studies_with_ci", "n_pooled"]:
        summ[c] = summ[c].astype("Int64")

    summ.to_csv(SUMMARY_PATH, index=False)

    # ---- console report ----
    print(f"corpus denominator (distinct studies): {n_corpus}\n")
    vc = summ["effect_model"].value_counts()
    print("effect_model distribution:")
    for k, v in vc.items():
        print(f"  {k:22} {v}")
    print("\nnew evidence_grade distribution:")
    print("  " + "  ".join(f"{g}={int((summ['evidence_grade']==g).sum())}"
                            for g in ["A", "B", "C"]))
    pooled = summ[summ["effect_model"] == "pooled_DL"]
    print(f"\npooled biomarkers: {len(pooled)}")
    return summ


if __name__ == "__main__":
    main()
