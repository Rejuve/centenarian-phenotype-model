"""
Centenarian Longevity Phenotype Model — scoring engine.

Deployable, dependency-light core (pyyaml only). The three tier models are bundled as
package data, so this module has NO dependency on the research pipeline or the data/ tree.

The **primary endpoint** is similarity to *verified* centenarians (people who actually reached
100+). The deployed v1 score is an **evidence-weighted alignment** of per-feature signal
(`evidence_weighted_similarity`, surfaced as `score_pct` / `total_similarity_score`). On top of it
the engine also returns a **four-class Naive Bayes posterior** (`class_posteriors`, planned-v2
probabilistic layer — see `naive_bayes.py`), interpretive `domain_scores`, and product fields. The
posterior layer's likelihoods are heuristic/calibration-pending; the user-facing number stays the
evidence-weighted similarity.

Public API:
    from centenarian_phenotype import score, load_model, MODEL_VERSIONS

    # Layer 1 (teaser quiz) — answers map question_id -> chosen option index
    score(1, {"q_physical_activity": 0, "q_diet": 1, ...})

    # Layer 2 (app survey) — tier-2 question ids
    score(2, {"q_pa_frequency": 0, "q_diabetes": 0, ...})

    # Layer 3 — tier-2 answers + measured clinical/genomic/epigenetic alignments (0..1)
    score(3, l2_answers, clinical={"hdl_cholesterol": 0.9, "grimage_2019": 0.85, "rs2069837": 1.0})

`score()` validates inputs strictly by default (unknown IDs / out-of-range values raise
ValidationError -> HTTP 422); pass strict=False for research/debug to downgrade to warnings.
"""
from __future__ import annotations

import math
from importlib import resources

import yaml

from .naive_bayes import posterior_summary
from .domains import compute_domains
from .longevity import relative_longevity
from .validation import (ValidationError, _empty_report, finalize, validate_clinical,
                         validate_quiz_answers)

# Layer-2 self-report question -> the Layer-3 MEASURED feature(s) for the SAME construct.
# When the deeper measured feature is supplied, the coarse self-report is dropped (deepest wins).
# Disease *diagnoses* are not re-scored at Layer 3 (they stay self-report), so only constructs with a
# genuinely measured Layer-3 counterpart appear here (body composition, strength, lipids).
CONSTRUCT_MAP = {
    "q_body_mass_index": {"body_mass_index"},
    "q_functional_mobility": {"grip_strength", "muscle_strength"},
    "q_cholesterol": {"cholesterol", "hdl_cholesterol", "triglycerides"},
}

# Highest-value clinical inputs expected at Layer 3 (strongest mortality / longevity signals that
# are freely measurable). Used for response_completeness and missing_high_value_inputs ranking.
# Tier-3 (access: lab/genomic/epigenetic) high-value inputs — the biospecimen/molecular panel.
# Anthropometric measures (grip, BMI, ...) are Tier 2 (access: anthropometric) and are not listed here.
CORE_L3_PANEL = [
    "grimage_2019", "phenoage_2018", "dunedinpace_2022", "c_reactive_protein", "hdl_cholesterol",
    "cholesterol", "triglycerides", "glucose", "hba1c", "egfr", "telomere_length",
    "rs429358", "rs2802295",
]

# Provenance quality (0..1) — feeds evidence_confidence_pct. Measured/genomic/epigenetic gold
# outrank reasoned/neutral authoring judgement.
_BASIS_QUALITY = {
    "measured": 1.0, "measured_clinical": 0.9, "genomic": 0.95, "epigenetic": 0.9,
    "heritability": 0.85, "clinical_literature": 0.8, "disease_escape": 0.8,
    "academic_corroborated": 0.75, "documented_positive": 0.7, "external_evidence": 0.6,
    "meta_analytic": 0.85, "reasoned_gradient": 0.5, "neutral_context": 0.45,
    "pending": 0.0, "unspecified": 0.5,
}

_MODIFIABLE_DOMAINS = {
    "physical_activity", "diet", "sleep", "substance_use", "social_connectedness",
    "purpose_meaning", "psychological_resilience", "cognitive_engagement", "faith_religion",
    "functional_independence", "functional_capacity", "body_composition", "self_rated_health",
    "mental_health",
}
_MODIFIABLE_FEATURES = {
    "hdl_cholesterol", "ldl_cholesterol", "cholesterol", "triglycerides", "hypertriglyceridemia",
    "c_reactive_protein", "glucose", "hba1c", "systolic_bp", "body_mass_index",
    "waist_circumference", "grip_strength", "muscle_strength", "gait_speed",
}

# Mapper canonical name -> tier-3 feature name. Lets a supplied/mapped `ldl_cholesterol` resolve to
# the tier-3 `cholesterol` feature (which is LDL-directional) so strict mode does not reject it.
CLINICAL_ALIASES = {"ldl_cholesterol": "cholesterol"}

_MODEL_FILES = {1: "tier1_model.yaml", 2: "tier2_model.yaml", 3: "tier3_model.yaml"}
_CACHE: dict[int, dict] = {}


def load_model(layer: int) -> dict:
    """Load a bundled tier model (1, 2, or 3) from package data, cached."""
    if layer not in _MODEL_FILES:
        raise ValueError(f"layer must be 1, 2 or 3 (got {layer!r})")
    if layer not in _CACHE:
        text = resources.files(__package__).joinpath("models", _MODEL_FILES[layer]).read_text(encoding="utf-8")
        _CACHE[layer] = yaml.safe_load(text)
    return _CACHE[layer]


MODEL_VERSIONS = {layer: load_model(layer).get("version", "0") for layer in _MODEL_FILES}


def _feature_defs(spec) -> dict:
    """Map every scoreable Layer-3 feature name -> its weight/basis/gwas def."""
    defs = {}
    for f in spec.get("clinical_biomarkers", []):
        defs[f["feature"]] = dict(weight=f["weight"], basis=f.get("basis"),
                                  gwas=bool(f.get("gwas_corroborated")), domain="clinical_biomarker")
    for v in spec.get("genomic_variants", []):
        defs[v["variant"]] = dict(weight=v["weight"], basis=v.get("basis", "genomic"), gwas=True,
                                  domain="genomic")
    for c in spec.get("epigenetic_methylation", []):
        defs[c["clock"]] = dict(weight=c["weight"], basis=c.get("basis", "epigenetic"),
                                gwas=bool(c.get("gwas_corroborated")), domain="epigenetic")
    # accept canonical mapper aliases (e.g. ldl_cholesterol -> cholesterol) in strict validation
    for src, dst in CLINICAL_ALIASES.items():
        if dst in defs and src not in defs:
            defs[src] = defs[dst]
    return defs


def _quiz_items(model, answers):
    qs = {q["id"]: q for q in model["questions"]}
    items = []
    for qid, oi in answers.items():
        if qid not in qs:
            continue
        q = qs[qid]
        opt = q["options"][oi]
        items.append(dict(feature=qid, domain=q["domain"], weight=q["weight"],
                          alignment=opt["alignment"], basis=opt.get("basis", "unspecified"),
                          gwas=False, layer=model["layer"]))
    return items


def _clinical_items(spec, alignments):
    defs = _feature_defs(spec)
    items = []
    for feat, al in alignments.items():
        d = defs.get(feat)
        if not d:
            continue
        items.append(dict(feature=feat, domain=d.get("domain", "clinical_biomarker"),
                          weight=d["weight"], alignment=float(al), basis=d["basis"],
                          gwas=d["gwas"], layer=3))
    return items


def _classify(it):
    if it.get("basis") in ("genomic", "heritability") or it["domain"] == "genetic_family_history":
        return "non_modifiable"
    if it["domain"] in _MODIFIABLE_DOMAINS or it["feature"] in _MODIFIABLE_FEATURES:
        return "modifiable"
    return "context"


def _label(it):
    return it["feature"].removeprefix("q_")


def _missing_high_value(layer, answered_ids, supplied_clinical, t2_model, tier3_spec):
    """Ranked inputs that would most raise confidence if supplied."""
    missing = []
    quiz_model = t2_model if layer >= 2 else load_model(1)
    for q in quiz_model["questions"]:
        if q["id"] not in answered_ids:
            missing.append({"input": q["id"], "kind": "question", "weight": q["weight"],
                            "why": f"{q['domain']} (unanswered)"})
    if layer == 3 and tier3_spec is not None:
        defs = _feature_defs(tier3_spec)
        for feat in CORE_L3_PANEL:
            if feat not in supplied_clinical and feat in defs:
                missing.append({"input": feat, "kind": "clinical", "weight": defs[feat]["weight"],
                                "why": f"high-value {defs[feat]['basis']} marker (not supplied)"})
    missing.sort(key=lambda m: m["weight"], reverse=True)
    return missing[:6]


def _score_profile(layer_models, quiz_answers=None, tier3_spec=None, clinical_alignments=None,
                   posterior_kwargs=None):
    quiz_answers = quiz_answers or {}
    layer_models = [m for m in layer_models if "questions" in m]
    items = []
    for m in layer_models:
        items += _quiz_items(m, quiz_answers)
    deepest = max(layer_models, key=lambda m: m["layer"]) if layer_models else None
    completeness = deepest["scoring"]["completeness_pct"] if deepest else 0
    gwas_bonus = (deepest or {}).get("scoring", {}).get("gwas_corroborated_weight", 0.0)

    deduped = []
    if tier3_spec is not None and clinical_alignments:
        provided = set(clinical_alignments)
        for it in items:
            covered = CONSTRUCT_MAP.get(it["feature"], set()) & provided
            if covered:
                deduped.append(it["feature"])
        items = [it for it in items if not (CONSTRUCT_MAP.get(it["feature"], set()) & provided)]
        items += _clinical_items(tier3_spec, clinical_alignments)
        completeness = tier3_spec["scoring"]["completeness_pct"]
        gwas_bonus = tier3_spec["scoring"]["gwas_corroborated_weight"]

    for it in items:
        it["eff_weight"] = it["weight"] * (1.0 + (gwas_bonus if it["gwas"] else 0.0))
    W = sum(it["eff_weight"] for it in items)
    score = sum(it["eff_weight"] * it["alignment"] for it in items) / W if W else 0.0
    var = sum(it["eff_weight"] * (it["alignment"] - score) ** 2 for it in items) / W if W else 0.0
    se = math.sqrt(var / max(len(items), 1))
    lo, hi = max(0.0, score - 1.96 * se), min(1.0, score + 1.96 * se)

    basis_mix = {}
    for it in items:
        basis_mix[it["basis"]] = basis_mix.get(it["basis"], 0.0) + it["eff_weight"]
    basis_mix = {b: round(100 * w / W, 1) for b, w in sorted(basis_mix.items(), key=lambda kv: -kv[1])} if W else {}
    gwas_share = round(100 * sum(it["eff_weight"] for it in items if it["gwas"]) / W, 1) if W else 0.0

    # --- evidence_confidence: model depth scaled by response completeness & provenance quality ---
    basis_quality = (sum(it["eff_weight"] * _BASIS_QUALITY.get(it["basis"], 0.5) for it in items) / W
                     if W else 0.0)

    contrib = sorted(items, key=lambda it: it["alignment"], reverse=True)
    layers = sorted({it["layer"] for it in items})
    template = (deepest or layer_models[0])["narrative_template"]

    # --- drivers (signed contribution = (alignment - mean) * eff_weight) ---
    for it in items:
        it["signed"] = (it["alignment"] - score) * it["eff_weight"]
    by_signed = sorted(items, key=lambda it: it["signed"], reverse=True)
    top_pos = [[_label(it), round(100 * it["alignment"])] for it in by_signed if it["signed"] > 0][:5]
    top_neg = [[_label(it), round(100 * it["alignment"])] for it in reversed(by_signed) if it["signed"] < 0][:5]
    modifiable = [[_label(it), round(100 * it["alignment"])]
                  for it in sorted(items, key=lambda it: it["signed"])
                  if _classify(it) == "modifiable" and it["alignment"] < score][:5]
    non_mod = [[_label(it), round(100 * it["alignment"])]
               for it in items if _classify(it) == "non_modifiable"][:5]

    result = dict(
        score_pct=round(100 * score, 1),
        total_similarity_score=round(100 * score, 1),
        evidence_weighted_similarity=round(100 * score, 1),
        ci_lower_pct=round(100 * lo, 1), ci_upper_pct=round(100 * hi, 1),
        # completeness_pct/confidence_pct are RETAINED for back-compat and equal model_depth_pct
        # (tier-based depth). Use response_completeness_pct + evidence_confidence_pct for the
        # "did the user actually answer enough, and how good is the evidence" question.
        completeness_pct=completeness, confidence_pct=completeness,
        model_depth_pct=completeness,
        layers_included=layers,
        narrative=template.format(score=round(100 * score, 1)),
        subscores={_label(it): round(100 * it["alignment"]) for it in items},
        pulling_up=[(_label(it), round(100 * it["alignment"])) for it in contrib if it["alignment"] >= score][:5],
        pulling_down=[(_label(it), round(100 * it["alignment"])) for it in contrib if it["alignment"] < score][-5:],
        top_positive_drivers=top_pos,
        top_negative_drivers=top_neg,
        modifiable_drivers=modifiable,
        non_modifiable_context=non_mod,
        evidence_basis_pct=basis_mix,
        gwas_corroborated_weight_share_pct=gwas_share,
        superseded_by_l3=deduped,
        answered=len(items),
        domain_scores=compute_domains(items, W),
        _basis_quality=basis_quality,  # internal; consumed by score() to build evidence_confidence
    )
    result.update(posterior_summary(items, **(posterior_kwargs or {})))
    return result


def get_quiz(layer: int) -> dict:
    """Public, frontend-safe question set for a quiz layer (1 or 2).

    Returns question ids, text, and option labels+indices ONLY — never the internal
    alignment/basis/weight values used for scoring. The HTML widget (L1) and Flutter app (L2)
    render from this so they never hard-code or drift from the model.
    """
    if layer not in (1, 2):
        raise ValueError("a renderable quiz exists only for layers 1 and 2 (layer 3 is a lab/genome spec)")
    m = load_model(layer)
    return {
        "layer": layer,
        "model_version": m.get("version"),
        "narrative_template": m.get("narrative_template"),
        "questions": [
            {
                "id": q["id"],
                "domain": q["domain"],
                "text": q["text"],
                "options": [{"index": j, "label": o["label"]} for j, o in enumerate(q["options"])],
            }
            for q in m["questions"]
        ],
    }


def score(layer: int, answers: dict, clinical: dict | None = None, strict: bool = True,
          posterior_kwargs: dict | None = None, context: dict | None = None) -> dict:
    """Score a profile at the given layer. See module docstring for the contract.

    layer 1 -> tier-1 teaser answers; layer 2 -> tier-2 app-survey answers;
    layer 3 -> tier-2 answers + `clinical` map of measured feature -> alignment(0..1).

    strict=True (default, for production/API): unknown question IDs, unknown clinical features,
    out-of-range option indices, and alignments outside [0,1] raise ValidationError (-> 422).
    strict=False (research/debug): the same issues are downgraded to a structured `warnings` block
    and the bad inputs are dropped.

    context (optional): {country, sex, age, bio_age_delta, allow_uncalibrated_odds}. When supplied,
    attaches a `longevity_context` block — the *validated* population survival baseline for that
    country x sex (HMD life tables) plus a *calibration-pending* phenotype trajectory band. Does NOT
    change the similarity score.
    """
    if layer not in (1, 2, 3):
        raise ValueError(f"layer must be 1, 2 or 3 (got {layer!r})")

    report = _empty_report()
    quiz_model = load_model(2) if layer >= 2 else load_model(1)
    q_index = {q["id"]: q for q in quiz_model["questions"]}
    clean_answers = validate_quiz_answers(answers, q_index, report)

    tier3_spec = load_model(3) if layer == 3 else None
    clean_clinical = {}
    if layer == 3:
        clean_clinical = validate_clinical(clinical, _feature_defs(tier3_spec), report)
    elif clinical:
        # clinical supplied to a non-L3 layer: not scoreable here
        for feat in clinical:
            report["unknown_inputs"].append(feat)
            report["ignored_inputs"].append(feat)

    scored_count = len(clean_answers) + len(clean_clinical)
    finalize(report, scored_count, strict, min_items=1)

    if layer == 1:
        result = _score_profile([load_model(1)], clean_answers, posterior_kwargs=posterior_kwargs)
    elif layer == 2:
        result = _score_profile([load_model(2)], clean_answers, posterior_kwargs=posterior_kwargs)
    else:
        result = _score_profile([load_model(2)], clean_answers, tier3_spec=tier3_spec,
                                clinical_alignments=clean_clinical, posterior_kwargs=posterior_kwargs)

    # --- completeness split -----------------------------------------------------
    if layer == 3:
        expected = len(load_model(2)["questions"]) + len(CORE_L3_PANEL)
    else:
        expected = len(quiz_model["questions"])
    resp_frac = min(1.0, scored_count / expected) if expected else 0.0
    basis_quality = result.pop("_basis_quality", 0.5)
    result["response_completeness_pct"] = round(100 * resp_frac, 1)
    result["evidence_confidence_pct"] = round(result["model_depth_pct"] * resp_frac * basis_quality, 1)
    result["usable_score"] = bool(resp_frac >= 0.5 and scored_count >= 3)

    result["missing_high_value_inputs"] = _missing_high_value(
        layer, set(clean_answers), set(clean_clinical), load_model(2), tier3_spec)

    # --- next-best action + pro unlock -----------------------------------------
    if result["missing_high_value_inputs"]:
        nb = result["missing_high_value_inputs"][0]
        verb = "Answer" if nb["kind"] == "question" else "Add your"
        result["next_best_data_action"] = f"{verb} {nb['input']} — {nb['why']} — to raise confidence."
    else:
        result["next_best_data_action"] = None
    if layer < 3:
        result["pro_unlock_opportunities"] = [
            "Tier 3 (Pro): add blood biomarkers (HDL/LDL/triglycerides/hs-CRP), genomic variants, "
            "DNA-methylation clocks and telomere length to move confidence toward ~80%."]
    else:
        result["pro_unlock_opportunities"] = []

    # --- relative-longevity context (validated demography + calibration-pending phenotype band) ---
    if context:
        result["longevity_context"] = relative_longevity(
            result["score_pct"], country=context.get("country"), sex=context.get("sex"),
            age=context.get("age", 65), bio_age_delta=context.get("bio_age_delta"),
            allow_uncalibrated_odds=bool(context.get("allow_uncalibrated_odds", False)))

    result["warnings"] = report
    result["model_version"] = {f"tier{layer if layer < 3 else 2}": MODEL_VERSIONS[2 if layer >= 2 else 1]}
    if layer == 3:
        result["model_version"]["tier3"] = MODEL_VERSIONS[3]
    return result


__all__ = ["score", "get_quiz", "load_model", "MODEL_VERSIONS", "CONSTRUCT_MAP", "ValidationError"]
