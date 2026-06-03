"""Relative-longevity context — anchoring the phenotype score in open demography.

The model is moving from "similarity to a rare *absolute* class (verified centenarians)" toward
"**relative** healthspan/longevity": is this profile consistent with outliving the typical
survival trajectory for the person's own country and sex, with less age-related decline? This
module provides the two halves of that framing and keeps them strictly separated by evidence status:

1. **Population baseline — VALIDATED open demography.** Straight from Human Mortality Database life
   tables (`models/longevity_baselines.yaml`, built by `scripts/pipeline/step_g_longevity_baselines.py`):
   remaining life expectancy and the probability of reaching 90 / 100 given survival to 65 / 80, by
   country x sex. No modelling — this is the population denominator and the eventual calibration target.

2. **Phenotype position — CALIBRATION-PENDING.** A qualitative band placing the profile relative to a
   typical-centenarian trajectory, plus (only on explicit opt-in) an *illustrative, not-validated*
   relative-risk band. Converting this into a calibrated personal probability of reaching a target age
   is the validation deliverable (gold standard: data from a person at 60–75 followed to 100+;
   platinum: from youth to 100+ — see VALIDATION_PLAN.md). Until then, **no fabricated personal odds
   are emitted by default.**
"""
from __future__ import annotations

import math
from importlib import resources

import yaml

_BASELINES: dict | None = None
_CALIB: dict | None = None
_CALIB_MISSING = False

# Common user inputs -> HMD country code.
_COUNTRY_ALIASES = {
    "us": "USA", "usa": "USA", "united states": "USA", "united states of america": "USA",
    "uk": "GBR", "united kingdom": "GBR", "great britain": "GBR", "england": "GBR",
    "south korea": "KOR", "korea": "KOR", "hong kong": "HKG", "russia": "RUS",
    "czech republic": "CZE", "deutschland": "DEU",
}


def _load() -> dict:
    global _BASELINES
    if _BASELINES is None:
        text = resources.files(__package__).joinpath("models", "longevity_baselines.yaml").read_text(
            encoding="utf-8")
        _BASELINES = yaml.safe_load(text)
    return _BASELINES


def _load_calibration():
    """Load the bundled score->10yr-mortality calibration artifact, or None if not present."""
    global _CALIB, _CALIB_MISSING
    if _CALIB is None and not _CALIB_MISSING:
        try:
            text = resources.files(__package__).joinpath(
                "models", "survival_calibration.yaml").read_text(encoding="utf-8")
            _CALIB = yaml.safe_load(text)
        except (FileNotFoundError, ModuleNotFoundError):
            _CALIB_MISSING = True
    return _CALIB


def calibrated_mortality(score_pct: float, age: float, sex=None) -> dict | None:
    """Calibrated 10-year all-cause mortality from the bundled NHANES model (None if unavailable).

    Returns the modelled 10-yr mortality probability and its ratio vs a same-age/sex person with an
    *average* phenotype score. ALL-CAUSE US mortality — NOT centenarian attainment.
    """
    cal = _load_calibration()
    if cal is None or age is None:
        return None
    sex_male = 1.0 if _norm_sex(sex) == "male" else 0.0
    stats = cal["feature_stats"]
    w = cal["standardized_weights"]
    b = cal["bias"]

    def p_of(score):
        x = [score, float(age), sex_male]
        z = b + sum(w[j] * (x[j] - stats[j][0]) / stats[j][1] for j in range(len(w)))
        return 1.0 / (1.0 + math.exp(-z))

    p = p_of(float(score_pct))
    p_avg = p_of(stats[0][0])  # same age/sex, average phenotype score
    return {
        "p_10yr_all_cause_mortality": round(p, 4),
        "relative_to_average_phenotype_same_age_sex": round(p / p_avg, 3) if p_avg else None,
        "horizon_years": cal["horizon_months"] // 12,
        "heldout_auc": cal.get("heldout", {}).get("auc"),
        "basis": "NHANES 1999-2016 linked mortality (held-out calibrated); all-cause, not centenarian attainment",
        "model_version": cal.get("version"),
    }


def _norm_sex(sex) -> str:
    if not sex:
        return "both"
    s = str(sex).strip().lower()
    if s in ("f", "female", "woman", "w"):
        return "female"
    if s in ("m", "male", "man"):
        return "male"
    return "both"


def _resolve_code(country) -> str | None:
    if not country:
        return None
    base = _load()["baselines"]
    c = str(country).strip()
    cu = c.upper()
    # direct code
    if any(k.startswith(cu + "|") for k in base):
        return cu
    cl = c.lower()
    if cl in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[cl]
    # match by country_name
    for k, v in base.items():
        if v["country_name"].lower() == cl:
            return k.split("|", 1)[0]
    return None


def list_countries() -> list[dict]:
    base = _load()["baselines"]
    seen = {}
    for k, v in base.items():
        code = k.split("|", 1)[0]
        seen[code] = v["country_name"]
    return [{"country_code": c, "country_name": n} for c, n in sorted(seen.items())]


def population_baseline(country, sex=None, age: float = 65, target: int = 100) -> dict | None:
    """Validated demographic baseline for country x sex. Returns the anchored survival probability
    closest to (age, target) plus life expectancy at 60/65. None if the country is unknown."""
    code = _resolve_code(country)
    if code is None:
        return None
    sex = _norm_sex(sex)
    base = _load()["baselines"]
    row = base.get(f"{code}|{sex}") or base.get(f"{code}|both")
    if row is None:
        return None

    # Pick the anchored probability nearest to the requested (age, target).
    if target >= 100:
        if age >= 73:
            prob, anchor = row["p_reach_100_from_80"], 80
        else:
            prob, anchor = row["p_reach_100_from_65"], 65
        tlabel = 100
    else:
        prob, anchor = row["p_reach_90_from_65"], 65
        tlabel = 90

    return {
        "country_code": code, "country_name": row["country_name"], "sex": sex,
        "data_year": row["year"], "source": "Human Mortality Database life tables",
        "life_expectancy_at_60": row["ex60"], "life_expectancy_at_65": row["ex65"],
        "p_reach_target": prob, "target_age": tlabel, "from_age": anchor,
        "quality_warning": row["quality_warning"],
        "note": f"P(reach {tlabel} | alive at {anchor}) for {row['country_name']} {sex}, "
                f"{row['year']}; validated demography (population, not this individual).",
    }


# Phenotype-position bands. ILLUSTRATIVE thresholds pending calibration against survival data —
# see VALIDATION_PLAN.md. They place the *score* relative to a typical centenarian trajectory.
_BANDS = [
    (85, "exceptional", "above the typical verified-centenarian profile"),
    (70, "typical_centenarian_range", "consistent with a typical verified-centenarian profile"),
    (55, "approaching_typical", "approaching the typical centenarian profile"),
    (0, "below_typical", "below the typical centenarian profile"),
]


def _band(score_pct: float):
    for thresh, name, desc in _BANDS:
        if score_pct >= thresh:
            return name, desc
    return "below_typical", "below the typical centenarian profile"


def relative_longevity(score_pct: float, country=None, sex=None, age: float = 65,
                       bio_age_delta: float | None = None,
                       allow_uncalibrated_odds: bool = False) -> dict:
    """Combine the validated population baseline with a calibration-pending phenotype position.

    Returns the demographic anchor (validated), a qualitative phenotype band (illustrative), an
    optional biological-age note, and a plain-language trajectory statement. A numeric personal
    odds band is emitted ONLY if `allow_uncalibrated_odds=True`, stamped not-validated.
    """
    band, band_desc = _band(score_pct)
    pop = population_baseline(country, sex=sex, age=age, target=100) if country else None

    cal_mort = calibrated_mortality(score_pct, age, sex=sex) if age else None
    out = {
        "population_baseline": pop,                         # validated demography (or None)
        "phenotype_band": band,                             # qualitative
        "phenotype_band_description": band_desc,
        "calibrated_mortality": cal_mort,                   # real, held-out NHANES calibration (or None)
        "calibration": ("10yr_all_cause_mortality_calibrated_NHANES_1999_2016" if cal_mort
                        else "phenotype_to_survival_mapping_uncalibrated"),
        "biological_age_context": None,
        "disclaimers": [
            "Population baseline (reaching 100) is validated demography. The calibrated_mortality "
            "field, when present, is a held-out NHANES calibration of ALL-CAUSE 10-year mortality — "
            "NOT centenarian attainment, single US cohort, not externally replicated.",
            "This is a similarity/trajectory context, not a personal lifespan prediction or medical "
            "advice. It can change as more data is added.",
        ],
    }
    if bio_age_delta is not None:
        younger = bio_age_delta < 0
        out["biological_age_context"] = {
            "delta_years": round(float(bio_age_delta), 1),
            "interpretation": ("biologically younger than chronological age (favourable)" if younger
                               else "biologically older than chronological age"),
        }

    where = f"for a {age:.0f}-year-old" if age else ""
    ctry = f" in {pop['country_name']}" if pop else ""
    out["trajectory_statement"] = (
        f"This profile is {band_desc} {where}{ctry}. "
        + (f"Population baseline: about {pop['p_reach_target']*100:.1f}% of {pop['sex']} alive at "
           f"{pop['from_age']}{ctry} reach {pop['target_age']} ({pop['data_year']})."
           if pop else "Provide country and sex for a population baseline."))

    if allow_uncalibrated_odds and pop and cal_mort is None:
        # ILLUSTRATIVE ONLY: a conservative, documented relative-risk band tied to the phenotype band.
        # NOT a validated personal probability. Multipliers are placeholders pending calibration.
        mult = {"exceptional": 2.0, "typical_centenarian_range": 1.5,
                "approaching_typical": 1.0, "below_typical": 0.6}[band]
        out["illustrative_relative_odds"] = {
            "multiplier_vs_population": mult,
            "illustrative_p_reach_100": round(min(0.95, pop["p_reach_target"] * mult), 4),
            "status": "illustrative_not_validated",
        }
    return out
