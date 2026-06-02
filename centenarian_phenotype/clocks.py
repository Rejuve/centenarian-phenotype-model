"""Extensible biological-age / clock interface.

The phenotype model is meant to be a *panel* of biological-age instruments, not a single clock.
This module is the registry + adapter layer:

* Each clock declares its **kind** (dna_methylation / clinical_chemistry / mortality_risk /
  pace_of_aging / telomere / frailty_functional / proteomic / metabolomic / microbiome), its
  **output_type** (biological_age / age_acceleration / pace / length / index / risk_score), the
  **tissue/sample** it needs, the **platform/assay** it requires, whether the implementation is
  **free_open / requires_coefficients / restricted**, an **evidence_grade**, and its **limitations**.
* `compute_clock()` turns a raw reading into a panel entry that **distinguishes raw biological age,
  age-acceleration delta, and pace**, and attaches an alignment computed by the versioned
  `mappers.py` (so cut-offs are never invented here either).
* Clocks are **not silently mixed into the score.** `to_clinical_alignments()` only emits clocks
  marked `scoreable=True` (those wired into a tier model with versioned weighting); pass
  `include_uncalibrated=True` to override for research, which stamps a warning.

A clock panel entry: clock_name, kind, output_type, raw_value, age_adjusted_delta, alignment,
evidence_grade, limitations, availability, scoreable, version.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .mappers import MAPPERS

CLOCK_PANEL_VERSION = "1.0"


@dataclass
class Clock:
    name: str
    kind: str
    output_type: str
    tissue: str
    platform: str
    availability: str           # free_open | requires_coefficients | restricted
    evidence_grade: str         # A | B | C
    limitations: str
    version: str = "1.0"
    scoreable: bool = False     # wired into a tier model with versioned weighting + validation
    score_feature: Optional[str] = None   # tier-model feature key this clock feeds
    mapper: Optional[str] = None           # mappers.py feature used to compute alignment
    status: str = "available"   # available | pending


# Standard instruments. DNAm age clocks output a biological age the caller compares to chronological
# age (delta = bio - chrono); pace/length/index clocks output their native quantity directly.
CLOCKS: dict[str, Clock] = {
    "horvath_2013": Clock(
        "horvath_2013", "dna_methylation", "biological_age", "pan_tissue",
        "Illumina 27K/450K/EPIC methylation array", "requires_coefficients", "B",
        "Multi-tissue; calibrated to chronological age, weaker mortality signal than GrimAge.",
        scoreable=True, score_feature="horvath_2013", mapper="epigenetic_age_acceleration"),
    "hannum_2013": Clock(
        "hannum_2013", "dna_methylation", "biological_age", "blood",
        "Illumina 450K methylation array", "requires_coefficients", "B",
        "Blood-only; trained on adults, extrapolation at extreme age uncertain.",
        scoreable=True, score_feature="hannum_2013", mapper="epigenetic_age_acceleration"),
    "skinblood_2018": Clock(
        "skinblood_2018", "dna_methylation", "biological_age", "skin_blood",
        "Illumina EPIC methylation array", "requires_coefficients", "B",
        "Skin/blood; not a tier-model feature yet (no reference distribution wired in).",
        scoreable=False, mapper="epigenetic_age_acceleration"),
    "phenoage_2018": Clock(
        "phenoage_2018", "dna_methylation", "age_acceleration", "blood",
        "Illumina methylation array (DNAm PhenoAge)", "requires_coefficients", "B",
        "Strong mortality predictor (Levine 2018); array-derived.",
        scoreable=True, score_feature="phenoage_2018", mapper="epigenetic_age_acceleration"),
    "grimage_2019": Clock(
        "grimage_2019", "mortality_risk", "age_acceleration", "blood",
        "Illumina methylation array (DNAm GrimAge)", "restricted", "B",
        "Strongest single mortality/lifespan clock (Lu 2019); coefficients access-restricted.",
        scoreable=True, score_feature="grimage_2019", mapper="epigenetic_age_acceleration"),
    "dunedinpace_2022": Clock(
        "dunedinpace_2022", "pace_of_aging", "pace", "blood",
        "Illumina methylation array (DunedinPACE)", "free_open", "B",
        "Pace of ageing (yr/yr); <1.0 favourable (Belsky 2022).",
        scoreable=True, score_feature="dunedinpace_2022", mapper="dunedinpace_2022"),
    "clinical_phenoage": Clock(
        "clinical_phenoage", "clinical_chemistry", "biological_age", "blood",
        "9 routine clinical-chemistry analytes + age (Levine 2018 clinical PhenoAge)", "free_open",
        "B", "Computable from a standard panel; not yet a tier-model feature.",
        scoreable=False, mapper="epigenetic_age_acceleration"),
    "telomere_length": Clock(
        "telomere_length", "telomere", "length", "blood (leukocyte)",
        "qPCR T/S ratio or Southern blot", "free_open", "C",
        "High measurement variability across assays; population-relative, not absolute.",
        scoreable=True, score_feature="telomere_length", mapper="telomere_length"),
    "frailty_index": Clock(
        "frailty_index", "frailty_functional", "index", "clinical_assessment",
        "Deficit-accumulation frailty index (0..1)", "free_open", "B",
        "Index in [0,1]; lower favourable. Assessment-dependent.",
        scoreable=False, mapper=None),
    # Registered but pending: no validated reference distribution wired in yet.
    "proteomic_aging_clock": Clock(
        "proteomic_aging_clock", "proteomic", "biological_age", "plasma",
        "Olink / SomaScan proteomics", "restricted", "C",
        "Pending: no reference distribution; platform-specific coefficients.",
        scoreable=False, status="pending"),
    "metabolomic_aging_clock": Clock(
        "metabolomic_aging_clock", "metabolomic", "biological_age", "plasma/serum",
        "NMR / MS metabolomics", "restricted", "C",
        "Pending: no reference distribution wired in.", scoreable=False, status="pending"),
    "microbiome_aging_clock": Clock(
        "microbiome_aging_clock", "microbiome", "biological_age", "stool",
        "16S / shotgun metagenomics", "free_open", "C",
        "Pending: centenarian microbiome data acquired, no validated clock wired in.",
        scoreable=False, status="pending"),
}


def compute_clock(name: str, value=None, chronological_age=None, sex=None) -> dict:
    """Turn a raw clock reading into a panel entry.

    For biological-age clocks pass ``value`` = predicted biological age and ``chronological_age``;
    the age-acceleration delta is ``value - chronological_age`` and drives the alignment. For
    pace/length/index clocks pass the native ``value`` directly.
    """
    if name not in CLOCKS:
        raise KeyError(f"unknown clock {name!r}; available: {sorted(CLOCKS)}")
    c = CLOCKS[name]
    entry = {
        "clock_name": c.name, "kind": c.kind, "output_type": c.output_type,
        "tissue": c.tissue, "platform": c.platform, "availability": c.availability,
        "evidence_grade": c.evidence_grade, "limitations": c.limitations,
        "scoreable": c.scoreable, "version": c.version, "status": c.status,
        "raw_value": value, "age_adjusted_delta": None, "alignment": None, "warnings": [],
    }
    if c.status == "pending":
        entry["warnings"].append("clock pending — no validated reference distribution")
        return entry
    if value is None:
        entry["warnings"].append("missing")
        return entry

    if c.output_type == "biological_age":
        if chronological_age is None:
            entry["warnings"].append("biological-age clock needs chronological_age to compute delta")
            return entry
        delta = float(value) - float(chronological_age)
        entry["age_adjusted_delta"] = round(delta, 2)
        mapped = MAPPERS[c.mapper](delta, sex=sex)
    elif c.output_type == "age_acceleration":
        entry["age_adjusted_delta"] = round(float(value), 2)
        mapped = MAPPERS[c.mapper](float(value), sex=sex)
    elif c.output_type == "index":
        # frailty index 0..1, lower favourable; no external mapper needed.
        v = min(max(float(value), 0.0), 1.0)
        mapped = {"alignment": round(1.0 - v, 4), "warnings": []}
    elif c.mapper:
        mapped = MAPPERS[c.mapper](float(value), sex=sex)
    else:
        entry["warnings"].append("no alignment mapper for this clock output")
        return entry

    entry["alignment"] = mapped["alignment"]
    entry["warnings"] += mapped.get("warnings", [])
    return entry


def compute_panel(readings: dict, chronological_age=None, sex=None) -> list[dict]:
    """Compute a clock panel from {clock_name: value} or {clock_name: {value, chronological_age}}."""
    panel = []
    for name, reading in readings.items():
        if isinstance(reading, dict):
            kw = {"chronological_age": chronological_age, "sex": sex, **reading}  # per-reading wins
            panel.append(compute_clock(name, **kw))
        else:
            panel.append(compute_clock(name, value=reading, chronological_age=chronological_age, sex=sex))
    return panel


def to_clinical_alignments(panel: list[dict], include_uncalibrated: bool = False) -> dict:
    """Extract {tier-model feature: alignment} from a panel, scoreable clocks only by default."""
    out = {}
    for e in panel:
        if e["alignment"] is None:
            continue
        clock = CLOCKS[e["clock_name"]]
        if clock.scoreable and clock.score_feature:
            out[clock.score_feature] = e["alignment"]
        elif include_uncalibrated and clock.score_feature:
            out[clock.score_feature] = e["alignment"]
    return out


def describe_clocks() -> list[dict]:
    """Machine-readable catalogue of every registered clock (for docs / the model card)."""
    return [{
        "name": c.name, "kind": c.kind, "output_type": c.output_type, "tissue": c.tissue,
        "platform": c.platform, "availability": c.availability, "evidence_grade": c.evidence_grade,
        "scoreable": c.scoreable, "status": c.status, "version": c.version,
        "limitations": c.limitations,
    } for c in CLOCKS.values()]
