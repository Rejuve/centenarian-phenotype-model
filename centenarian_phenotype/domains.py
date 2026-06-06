"""Phenotype decomposition — secondary interpretive domains.

These explain *why* a profile resembles verified centenarians; they do NOT redefine the endpoint.
The primary endpoint stays "verified 100+ survival similarity" (the evidence-weighted score). Each
domain below is just the evidence-weighted mean alignment of the scored features that bear on it,
expressed 0–100, and is only emitted when at least one contributing feature was actually scored.

A feature can contribute to more than one domain (e.g. HDL informs both cardiovascular and
metabolic). Domains with no contributing features in a given profile are omitted rather than
reported as a misleading 0.
"""
from __future__ import annotations

# Feature/domain membership. A rule matches an item if its `feature` OR model `domain` is listed,
# or its `basis`/`gwas` matches the special predicates handled in compute_domains().
_FEATURES = {
    "cardiovascular_longevity_similarity": {
        "features": {"hdl_cholesterol", "ldl_cholesterol", "cholesterol", "triglycerides",
                     "blood_pressure", "systolic_bp", "cardiovascular_disease",
                     "coronary_heart_disease", "myocardial_infarction", "stroke"},
        "domains": {"hypertension", "cardiovascular_disease", "cholesterol"},
    },
    "metabolic_health_similarity": {
        "features": {"diabetes", "glucose", "hba1c", "insulin", "body_mass_index",
                     "waist_circumference"},
        "domains": {"diabetes", "body_composition"},
    },
    "inflammatory_resilience_similarity": {
        "features": {"c_reactive_protein", "interleukin_6", "white_blood_cell"},
        "domains": set(),
    },
    "functional_preservation_similarity": {
        "features": {"grip_strength", "muscle_strength", "calf_circumference", "gait_speed",
                     "frailty", "activities_of_daily_living"},
        "domains": {"functional_independence", "functional_capacity"},
    },
    "cognitive_preservation_similarity": {
        "features": {"dementia", "alzheimer_disease"},
        "domains": {"cognitive_engagement", "mental_health"},
    },
    "survival_resilience_similarity": {
        "features": set(),
        "domains": {"psychological_resilience", "self_rated_health", "purpose_meaning"},
    },
    "social_environmental_context": {
        "features": set(),
        "domains": {"social_connectedness", "family_bonds", "faith_religion"},
    },
}


def _wmean(items):
    w = sum(it["eff_weight"] for it in items)
    return (sum(it["eff_weight"] * it["alignment"] for it in items) / w) if w else 0.0, w


def compute_domains(items, total_weight):
    """Return {interpretive_domain: {score_pct, n_features, weight_share_pct}} for domains present."""
    out = {}

    def emit(name, members):
        if not members:
            return
        s, w = _wmean(members)
        out[name] = {
            "score_pct": round(100 * s, 1),
            "n_features": len(members),
            "weight_share_pct": round(100 * w / total_weight, 1) if total_weight else 0.0,
        }

    for name, rule in _FEATURES.items():
        members = [it for it in items
                   if it["feature"] in rule["features"] or it["domain"] in rule["domains"]]
        emit(name, members)

    # Escaper/delayer phenotype: disease-flag features (absence/late-onset favourable).
    emit("disease_escape_similarity",
         [it for it in items if it.get("basis") in ("disease_escape", "clinical_literature")
          and it["domain"] not in ("body_composition", "cholesterol")])

    # Genetic + epigenetic context (Layer 3).
    emit("genetic_longevity_context",
         [it for it in items if it.get("gwas") or it.get("basis") in ("genomic", "heritability")
          or it["domain"] == "genetic_family_history"])
    emit("epigenetic_youthfulness_slow_pace_context",
         [it for it in items if it.get("basis") == "epigenetic"])
    return out
