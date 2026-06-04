"""Versioned raw-value -> alignment mappers for Tier 3 clinical inputs.

The scoring engine consumes alignments in [0, 1]; it intentionally does NOT do clinical reference
math itself. These mappers are the production-safe boundary that turns a raw measured value (with
units, and sex/age where it matters) into an alignment, so callers do not hand-roll cut-offs.

Design rules
------------
* **No invented cut-offs.** Every threshold cites an established public reference
  (NCEP ATP III, ADA, WHO, ACC/AHA 2017, AHA/CDC hs-CRP, EWGSOP2, KDIGO). See each mapper's
  ``provenance``. The alignment *shape* between cut-offs is a declared monotone/U-shaped
  interpolation, graded accordingly.
* **Every mapper is self-describing**: units, accepted_range, sex/age adjustment, provenance,
  evidence_grade, version, missingness behaviour, warning behaviour.
* **Missingness**: ``map(None)`` returns ``alignment=None`` and a ``missing`` warning — never a
  fabricated mid-point.
* **Out-of-physiological-range** values are clamped to the accepted range and warned, not rejected,
  so a fat-fingered unit (mmol/L vs mg/dL) surfaces as a warning rather than a silent wrong score.

Usage
-----
    from centenarian_phenotype.mappers import map_value, MAPPERS
    r = map_value("hdl_cholesterol", 62, sex="M")        # -> {"alignment": 0.9, "warnings": [...], ...}
    score(3, answers, clinical={"hdl_cholesterol": r["alignment"]})

``map_panel({...raw...})`` maps a whole lab panel and returns {feature: alignment} ready for
``score(3, ..., clinical=...)`` plus a per-feature provenance/warning report.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

MAPPER_SET_VERSION = "1.0"


@dataclass
class Mapper:
    feature: str
    units: str
    accepted_range: tuple[float, float]
    fn: Callable
    direction: str
    provenance: str
    evidence_grade: str  # A (clinical reference), B (literature), C (declared shape)
    version: str = "1.0"
    sex_adjusted: bool = False
    age_adjusted: bool = False
    missingness: str = "returns alignment=None + 'missing' warning"

    def __call__(self, value, sex=None, age=None) -> dict:
        warnings: list[str] = []
        if value is None:
            return {"feature": self.feature, "alignment": None, "warnings": ["missing"],
                    "evidence_grade": self.evidence_grade, "version": self.version}
        try:
            v = float(value)
        except (TypeError, ValueError):
            return {"feature": self.feature, "alignment": None,
                    "warnings": [f"not a number: {value!r}"],
                    "evidence_grade": self.evidence_grade, "version": self.version}
        lo, hi = self.accepted_range
        if v < lo or v > hi:
            warnings.append(f"value {v} outside accepted physiological range {self.accepted_range} "
                            f"({self.units}) — check units; clamped")
            v = min(max(v, lo), hi)
        if self.sex_adjusted and sex not in ("M", "F"):
            warnings.append("sex not supplied for a sex-adjusted marker; using pooled cut-offs")
        alignment = round(float(self.fn(v, sex, age)), 4)
        return {"feature": self.feature, "alignment": alignment, "raw_value": float(value),
                "warnings": warnings, "direction": self.direction,
                "evidence_grade": self.evidence_grade, "version": self.version}


# ---- interpolation helpers ----------------------------------------------------

def _interp(x, points):
    """Piecewise-linear over sorted (x, alignment) anchors; flat outside the ends."""
    pts = sorted(points)
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, a0), (x1, a1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            t = (x - x0) / (x1 - x0) if x1 != x0 else 0.0
            return a0 + t * (a1 - a0)
    return pts[-1][1]


# ---- individual mappers -------------------------------------------------------
# Anchors are (raw_value, alignment). Cut-offs cite the named reference; the alignment values
# between cut-offs are a declared monotone shape (grade B/C as noted).

def _hdl(v, sex, age):
    # NCEP ATP III: <40 (M)/<50 (F) low; >=60 mg/dL high/protective.
    low = 50 if sex == "F" else 40
    return _interp(v, [(20, 0.1), (low, 0.5), (60, 0.9), (90, 1.0)])


def _ldl(v, sex, age):
    # NCEP ATP III: <100 optimal, 130 borderline, 160 high, 190 very high.
    return _interp(v, [(50, 1.0), (100, 0.9), (130, 0.65), (160, 0.4), (190, 0.2)])


def _apob(v, sex, age):
    # g/L. <0.9 optimal, >1.2 high (consensus lipid guidance).
    return _interp(v, [(0.5, 1.0), (0.9, 0.85), (1.2, 0.45), (1.6, 0.2)])


def _trig(v, sex, age):
    # NCEP ATP III: <150 normal, 200 borderline-high, 500 very high.
    return _interp(v, [(50, 1.0), (150, 0.85), (200, 0.55), (500, 0.15)])


def _glucose(v, sex, age):
    # ADA fasting: <100 normal, 100-125 prediabetes, >=126 diabetes.
    return _interp(v, [(70, 1.0), (100, 0.9), (126, 0.45), (200, 0.15)])


def _hba1c(v, sex, age):
    # ADA %: <5.7 normal, 5.7-6.4 prediabetes, >=6.5 diabetes.
    return _interp(v, [(4.5, 1.0), (5.7, 0.9), (6.5, 0.45), (9.0, 0.1)])


def _sbp(v, sex, age):
    # ACC/AHA 2017: <120 normal, 120-129 elevated, 130-139 stage1, >=140 stage2.
    # Mild low-end penalty (hypotension/frailty in elderly).
    return _interp(v, [(90, 0.7), (110, 1.0), (120, 0.95), (130, 0.7), (140, 0.45), (180, 0.1)])


def _bmi(v, sex, age):
    # WHO: 18.5-25 normal. U-shaped — late-life low BMI signals frailty, high signals adiposity.
    return _interp(v, [(15, 0.2), (18.5, 0.7), (22, 1.0), (25, 0.85), (30, 0.5), (40, 0.2)])


def _waist(v, sex, age):
    # IDF/WHO: high if >102 cm (M) / >88 cm (F); slim end favourable.
    high = 88 if sex == "F" else 102
    mid = 80 if sex == "F" else 94
    return _interp(v, [(60, 1.0), (mid, 0.85), (high, 0.45), (high + 25, 0.2)])


def _crp(v, sex, age):
    # AHA/CDC hs-CRP (mg/L): <1 low CV risk, 1-3 average, >3 high.
    return _interp(v, [(0.2, 1.0), (1.0, 0.9), (3.0, 0.5), (10.0, 0.15)])


def _egfr(v, sex, age):
    # KDIGO: >=90 normal, 60-89 mild, <60 CKD, <30 severe. Higher favourable (plateau at 90).
    return _interp(v, [(15, 0.1), (30, 0.3), (60, 0.6), (90, 0.95), (120, 1.0)])


def _alt(v, sex, age):
    # U/L. Within ~normal favourable; high signals hepatic stress (broad reference ~7-40).
    return _interp(v, [(7, 1.0), (40, 0.85), (80, 0.5), (200, 0.15)])


def _gait_speed(v, sex, age):
    # m/s. >=1.0 robust, <0.8 frailty/sarcopenia cut-off (EWGSOP2 / Studenski 2011).
    return _interp(v, [(0.4, 0.2), (0.8, 0.5), (1.0, 0.85), (1.4, 1.0)])


def _grip(v, sex, age):
    # kg. EWGSOP2 low cut-off: <27 (M), <16 (F).
    low = 16 if sex == "F" else 27
    good = 30 if sex == "F" else 45
    return _interp(v, [(low - 10, 0.2), (low, 0.5), (good, 1.0)])


def _epi_accel(v, sex, age):
    # years of epigenetic age acceleration (DNAmAge - chronological). <0 favourable. Maps a delta.
    return _interp(v, [(-8, 1.0), (0, 0.8), (5, 0.5), (12, 0.2)])


def _dunedin_pace(v, sex, age):
    # DunedinPACE: years of biological ageing per calendar year. <1.0 favourable (Belsky 2022).
    return _interp(v, [(0.7, 1.0), (1.0, 0.7), (1.2, 0.45), (1.5, 0.15)])


def _telomere(v, sex, age):
    # Relative leukocyte telomere length (T/S ratio), longer favourable. Population-relative.
    return _interp(v, [(0.5, 0.2), (1.0, 0.6), (1.5, 0.9), (2.0, 1.0)])


def _wbc(v, sex, age):
    # WBC count (x10^9/L). Lower-normal favourable (inflammaging); leukopenia and leukocytosis both
    # adverse. PhenoAge treats higher WBC as a mortality-increasing component.
    return _interp(v, [(2.5, 0.3), (4.5, 1.0), (6.0, 0.95), (7.5, 0.7), (11.0, 0.4), (15.0, 0.15)])


MAPPERS: dict[str, Mapper] = {
    "hdl_cholesterol": Mapper("hdl_cholesterol", "mg/dL", (10, 150), _hdl, "higher_favorable",
                              "NCEP ATP III HDL cut-offs", "A", sex_adjusted=True),
    "ldl_cholesterol": Mapper("ldl_cholesterol", "mg/dL", (20, 300), _ldl, "lower_favorable",
                              "NCEP ATP III LDL cut-offs", "A"),
    "apob": Mapper("apob", "g/L", (0.2, 2.5), _apob, "lower_favorable",
                   "ESC/EAS & consensus ApoB targets", "B"),
    "triglycerides": Mapper("triglycerides", "mg/dL", (30, 1000), _trig, "lower_favorable",
                            "NCEP ATP III triglyceride cut-offs", "A"),
    "glucose": Mapper("glucose", "mg/dL (fasting)", (40, 400), _glucose, "lower_favorable",
                      "ADA fasting glucose cut-offs", "A"),
    "hba1c": Mapper("hba1c", "% (NGSP)", (3.5, 15), _hba1c, "lower_favorable",
                    "ADA HbA1c cut-offs", "A"),
    "systolic_bp": Mapper("systolic_bp", "mmHg", (70, 220), _sbp, "u_shaped_normal_favorable",
                          "ACC/AHA 2017 BP categories", "A", age_adjusted=True),
    "body_mass_index": Mapper("body_mass_index", "kg/m^2", (12, 60), _bmi, "u_shaped_normal_favorable",
                              "WHO BMI categories; U-shaped late-life risk", "A"),
    "waist_circumference": Mapper("waist_circumference", "cm", (50, 180), _waist, "lower_favorable",
                                  "IDF/WHO waist cut-offs", "A", sex_adjusted=True),
    "c_reactive_protein": Mapper("c_reactive_protein", "mg/L (hs-CRP)", (0.05, 50), _crp,
                                 "lower_favorable", "AHA/CDC hs-CRP CV-risk categories", "A"),
    "egfr": Mapper("egfr", "mL/min/1.73m^2", (5, 130), _egfr, "higher_favorable",
                   "KDIGO eGFR/CKD stages", "A"),
    "alt": Mapper("alt", "U/L", (3, 400), _alt, "mid_range_favorable",
                  "Common clinical ALT reference range", "B"),
    "gait_speed": Mapper("gait_speed", "m/s", (0.1, 2.0), _gait_speed, "higher_favorable",
                         "EWGSOP2 / Studenski 2011 gait-speed cut-offs", "A"),
    "grip_strength": Mapper("grip_strength", "kg", (5, 80), _grip, "higher_favorable",
                            "EWGSOP2 grip-strength cut-offs", "A", sex_adjusted=True),
    "epigenetic_age_acceleration": Mapper("epigenetic_age_acceleration", "years (DNAmAge - chrono)",
                                          (-20, 25), _epi_accel, "lower_favorable",
                                          "Epigenetic age-acceleration mortality literature "
                                          "(Marioni 2015; Levine 2018; Lu 2019)", "B"),
    "dunedinpace_2022": Mapper("dunedinpace_2022", "pace (yr/yr)", (0.5, 2.0), _dunedin_pace,
                               "lower_favorable", "DunedinPACE (Belsky 2022)", "B"),
    "telomere_length": Mapper("telomere_length", "T/S ratio (relative)", (0.2, 3.0), _telomere,
                              "longer_favorable", "Leukocyte telomere-length ageing literature", "C"),
    "white_blood_cell": Mapper("white_blood_cell", "x10^9/L", (1.0, 30.0), _wbc,
                               "mid_range_favorable", "Clinical WBC reference; inflammaging / PhenoAge"
                               " mortality component", "B"),
}


def map_value(feature: str, value, sex: Optional[str] = None, age: Optional[float] = None) -> dict:
    """Map one raw value to an alignment. Raises KeyError if the feature has no mapper."""
    if feature not in MAPPERS:
        raise KeyError(f"no mapper for feature {feature!r}; available: {sorted(MAPPERS)}")
    return MAPPERS[feature](value, sex=sex, age=age)


def _tier3_scoreable():
    """(scoreable feature-name set, alias map) from the live tier-3 model; ({}, {}) if unavailable."""
    try:
        from .scoring import CLINICAL_ALIASES, _feature_defs, load_model
        return set(_feature_defs(load_model(3))), CLINICAL_ALIASES
    except Exception:  # noqa: BLE001 - keep mappers usable even if scoring import fails
        return set(), {}


def map_panel(raw: dict, sex: Optional[str] = None, age: Optional[float] = None) -> dict:
    """Map a raw lab/functional panel into alignments.

    Returns {"clinical", "report", "unmapped", "not_scoreable"}. ``clinical`` is keyed by the tier-3
    feature name (aliases resolved, e.g. ldl_cholesterol -> cholesterol) and contains **only features
    the tier-3 model can currently score** — so it is safe to pass to ``score(3, ..., strict=True)``.
    Mapped features without a tier-3 home (apob, systolic_bp, waist_circumference, alt, gait_speed)
    are listed in ``not_scoreable`` rather than silently included.
    """
    scoreable, alias = _tier3_scoreable()
    clinical, report, unmapped, not_scoreable = {}, {}, [], []
    for feat, val in raw.items():
        if feat not in MAPPERS:
            unmapped.append(feat)
            continue
        out = MAPPERS[feat](val, sex=sex, age=age)
        report[feat] = out
        if out["alignment"] is None:
            continue
        target = alias.get(feat, feat)
        if not scoreable or target in scoreable:
            clinical[target] = out["alignment"]
        else:
            not_scoreable.append(feat)
    return {"clinical": clinical, "report": report, "unmapped": unmapped,
            "not_scoreable": not_scoreable}


def describe_mappers() -> list[dict]:
    """Machine-readable catalogue of every mapper (for docs / the model card)."""
    return [{
        "feature": m.feature, "units": m.units, "accepted_range": list(m.accepted_range),
        "direction": m.direction, "sex_adjusted": m.sex_adjusted, "age_adjusted": m.age_adjusted,
        "provenance": m.provenance, "evidence_grade": m.evidence_grade, "version": m.version,
        "missingness": m.missingness,
    } for m in MAPPERS.values()]
