"""
Centenarian Longevity Phenotype Model — scoring engine.

Deployable, dependency-light core (pyyaml only). The three tier models are bundled as
package data, so this module has NO dependency on the research pipeline or the data/ tree.

Public API:
    from centenarian_phenotype import score, load_model, MODEL_VERSIONS

    # Layer 1 (teaser quiz) — answers map question_id -> chosen option index
    score(1, {"q_physical_activity": 0, "q_diet": 1, ...})

    # Layer 2 (app survey) — tier-2 question ids
    score(2, {"q_pa_frequency": 0, "q_diabetes": 0, ...})

    # Layer 3 — tier-2 answers + measured clinical/genomic/epigenetic alignments (0..1)
    score(3, l2_answers, clinical={"hdl_cholesterol": 0.9, "grimage_2019": 0.85, "rs2069837": 1.0})

Each result is a dict (JSON-serializable): score_pct, ci_lower_pct, ci_upper_pct,
completeness_pct, narrative, subscores, pulling_up, pulling_down, evidence_basis_pct,
gwas_corroborated_weight_share_pct, superseded_by_l3, answered, layers_included, model_version.
"""
from __future__ import annotations

import math
from importlib import resources

import yaml

# Layer-2 self-report question -> the Layer-3 measured feature(s) for the SAME construct.
# When the deeper measured feature is supplied, the coarse self-report is dropped (deepest wins).
CONSTRUCT_MAP = {
    "q_diabetes": {"diabetes"},
    "q_hypertension": {"hypertension", "blood_pressure"},
    "q_body_mass_index": {"body_mass_index"},
    "q_waist_circumference": {"waist_circumference"},
    "q_cardiovascular_event": {"cardiovascular_disease", "myocardial_infarction", "stroke", "coronary_heart_disease"},
    "q_cancer_history": {"breast_cancer", "skin_cancer"},
    "q_functional_mobility": {"grip_strength", "frailty", "activities_of_daily_living", "muscle_strength"},
    "q_cholesterol": {"cholesterol", "hdl_cholesterol", "triglycerides"},
    "q_disease_burden": {"multimorbidity", "comorbidity"},
    "q_bone_health": {"osteoporosis"},
}

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
    defs = {}
    for grp in ("clinical_biomarkers", "clinical_disease_flags"):
        for f in spec.get(grp, []):
            defs[f["feature"]] = dict(weight=f["weight"], basis=f.get("basis"),
                                      gwas=bool(f.get("gwas_corroborated")))
    for v in spec.get("genomic_variants", []):
        defs[v["variant"]] = dict(weight=v["weight"], basis=v.get("basis", "genomic"), gwas=True)
    for c in spec.get("epigenetic_methylation", []):
        defs[c["clock"]] = dict(weight=c["weight"], basis=c.get("basis", "epigenetic"),
                                gwas=bool(c.get("gwas_corroborated")))
    items = []
    for feat, al in alignments.items():
        d = defs.get(feat)
        if not d:
            continue
        items.append(dict(feature=feat, domain="clinical_biomarker", weight=d["weight"],
                          alignment=float(al), basis=d["basis"], gwas=d["gwas"], layer=3))
    return items


def _score_profile(layer_models, quiz_answers=None, tier3_spec=None, clinical_alignments=None):
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

    contrib = sorted(items, key=lambda it: it["alignment"], reverse=True)
    layers = sorted({it["layer"] for it in items})
    template = (deepest or layer_models[0])["narrative_template"]
    return dict(
        score_pct=round(100 * score, 1),
        ci_lower_pct=round(100 * lo, 1), ci_upper_pct=round(100 * hi, 1),
        # completeness_pct IS the model's confidence in the similarity estimate: the layers
        # measure the SAME similarity construct, each at higher confidence (L1 30 -> L2 50 -> L3 80).
        completeness_pct=completeness, confidence_pct=completeness, layers_included=layers,
        narrative=template.format(score=round(100 * score, 1)),
        subscores={it["feature"].removeprefix("q_"): round(100 * it["alignment"]) for it in items},
        pulling_up=[(it["feature"].removeprefix("q_"), round(100 * it["alignment"])) for it in contrib if it["alignment"] >= score][:5],
        pulling_down=[(it["feature"].removeprefix("q_"), round(100 * it["alignment"])) for it in contrib if it["alignment"] < score][-5:],
        evidence_basis_pct=basis_mix,
        gwas_corroborated_weight_share_pct=gwas_share,
        superseded_by_l3=deduped,
        answered=len(items),
    )


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


def score(layer: int, answers: dict, clinical: dict | None = None) -> dict:
    """Score a profile at the given layer. See module docstring for the contract.

    layer 1 -> tier-1 teaser answers; layer 2 -> tier-2 app-survey answers;
    layer 3 -> tier-2 answers + `clinical` map of measured feature -> alignment(0..1).
    """
    if layer == 1:
        result = _score_profile([load_model(1)], answers)
    elif layer == 2:
        result = _score_profile([load_model(2)], answers)
    elif layer == 3:
        result = _score_profile([load_model(2)], answers, tier3_spec=load_model(3),
                                clinical_alignments=clinical or {})
    else:
        raise ValueError(f"layer must be 1, 2 or 3 (got {layer!r})")
    result["model_version"] = {f"tier{layer if layer < 3 else 2}": MODEL_VERSIONS[2 if layer >= 2 else 1]}
    if layer == 3:
        result["model_version"]["tier3"] = MODEL_VERSIONS[3]
    return result
