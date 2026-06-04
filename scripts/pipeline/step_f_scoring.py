"""
Step F — scoring engine for the Centenarian Longevity Phenotype Model.

Reads a tier model YAML + a user's answers and returns the percentage similarity
to verified centenarians, with per-domain subscores, a 95% interval, and the
factors pulling the score up/down.

Layer 1 (this file's primary use): behavioral quiz, gwas weight 0.00.
Layer 3 (when built) reintroduces gwas_corroborated with weight — see
MODEL_CARD.md "Evidence accumulation / completeness".

Usage:
  python scripts/pipeline/step_f_scoring.py --print            # show the quiz
  python scripts/pipeline/step_f_scoring.py --answers ans.json # score answers
  (or import score_quiz / score_answers programmatically)
"""
import argparse
import json
import math

import yaml

TIER1 = "models/tier1_model.yaml"

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


def load_model(path=TIER1):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def score_answers(model, answers):
    """answers: {question_id: option_index}. Returns a result dict."""
    qs = {q["id"]: q for q in model["questions"]}
    per = []
    for qid, oi in answers.items():
        q = qs[qid]
        opt = q["options"][oi]
        per.append(dict(question=qid, domain=q["domain"], weight=q["weight"],
                        alignment=opt["alignment"], answer=opt["label"],
                        basis=opt.get("basis", "unspecified"),
                        trait_tags=opt.get("trait_tags", [])))
    W = sum(p["weight"] for p in per)
    score = sum(p["weight"] * p["alignment"] for p in per) / W if W else 0.0
    # weighted variance of alignments -> SE -> 95% interval (toy CI)
    var = sum(p["weight"] * (p["alignment"] - score) ** 2 for p in per) / W if W else 0.0
    se = math.sqrt(var / max(len(per), 1))
    lo, hi = max(0.0, score - 1.96 * se), min(1.0, score + 1.96 * se)
    # domain contributions vs the mean (what pulls the score up / down)
    contrib = sorted(per, key=lambda p: p["alignment"], reverse=True)
    # provenance: share of the answered weight resting on each evidence basis
    basis_mix = {}
    for p in per:
        basis_mix[p["basis"]] = basis_mix.get(p["basis"], 0.0) + p["weight"]
    basis_mix = {b: round(100 * w / W, 1) for b, w in sorted(basis_mix.items(), key=lambda kv: -kv[1])} if W else {}
    return dict(
        score_pct=round(100 * score, 1),
        ci_lower_pct=round(100 * lo, 1), ci_upper_pct=round(100 * hi, 1),
        completeness_pct=model["scoring"]["completeness_pct"],
        narrative=model["narrative_template"].format(score=round(100 * score, 1)),
        subscores={p["question"].removeprefix("q_"): round(100 * p["alignment"], 0) for p in per},
        pulling_up=[(p["domain"], round(100 * p["alignment"])) for p in contrib if p["alignment"] >= score][:4],
        pulling_down=[(p["domain"], round(100 * p["alignment"])) for p in contrib if p["alignment"] < score][-4:],
        evidence_basis_pct=basis_mix,
        answered=len(per), n_questions=len(model["questions"]),
    )


def _quiz_items(model, answers):
    """Turn {qid: option_index} into scoring items for one quiz model (Layer 1 or 2)."""
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
    """Turn {feature: alignment 0-1} into scoring items for the Layer-3 clinical spec.

    The app/clinical layer is responsible for mapping a raw lab value or genotype to an
    alignment in [0,1] against the feature's reference; this engine only weights them.
    """
    defs = {}
    for f in spec.get("clinical_biomarkers", []):
        defs[f["feature"]] = dict(weight=f["weight"], basis=f.get("basis"),
                                  gwas=bool(f.get("gwas_corroborated")))
    for v in spec.get("genomic_variants", []):
        defs[v["variant"]] = dict(weight=v["weight"], basis=v.get("basis", "genomic"), gwas=True)
    for c in spec.get("epigenetic_methylation", []):
        defs[c["clock"]] = dict(weight=c["weight"], basis=c.get("basis", "epigenetic"),
                                gwas=bool(c.get("gwas_corroborated")))
    for m in spec.get("microbiome", []):
        if m.get("weight", 0) and m.get("basis") != "pending":
            defs[m["feature"]] = dict(weight=m["weight"], basis=m.get("basis", "microbiome_literature"),
                                      gwas=bool(m.get("gwas_corroborated")))
    items = []
    for feat, al in alignments.items():
        d = defs.get(feat)
        if not d:
            continue
        items.append(dict(feature=feat, domain="clinical_biomarker", weight=d["weight"],
                          alignment=float(al), basis=d["basis"], gwas=d["gwas"], layer=3))
    return items


def score_profile(layer_models, quiz_answers=None, tier3_spec=None, clinical_alignments=None):
    """Combine any subset of layers into one evidence-weighted similarity score.

    layer_models: list of loaded quiz models (Tier 1 [, Tier 2]).
    quiz_answers: {qid: option_index} spanning those models.
    tier3_spec + clinical_alignments: optional Layer-3 inputs.
    gwas_corroborated_weight (from the DEEPEST model present) is applied as an additive
    confidence bonus to gwas-corroborated features — 0.00 at Layers 1-2, >0 at Layer 3.
    """
    quiz_answers = quiz_answers or {}
    layer_models = [m for m in layer_models if "questions" in m]  # tier3 spec is not a quiz
    items = []
    for m in layer_models:
        items += _quiz_items(m, quiz_answers)
    deepest = max(layer_models, key=lambda m: m["layer"]) if layer_models else None
    completeness = deepest["scoring"]["completeness_pct"] if deepest else 0
    gwas_bonus = (deepest or {}).get("scoring", {}).get("gwas_corroborated_weight", 0.0)
    deduped = []
    if tier3_spec is not None and clinical_alignments:
        provided = set(clinical_alignments)
        # deepest layer wins: drop L2 self-report items whose construct is measured at L3
        for it in items:
            covered = CONSTRUCT_MAP.get(it["feature"], set()) & provided
            if covered:
                deduped.append((it["feature"], sorted(covered)))
                continue
            # keep
        items = [it for it in items if not (CONSTRUCT_MAP.get(it["feature"], set()) & provided)]
        items += _clinical_items(tier3_spec, clinical_alignments)
        completeness = tier3_spec["scoring"]["completeness_pct"]
        gwas_bonus = tier3_spec["scoring"]["gwas_corroborated_weight"]

    # effective weight = base weight, plus the gwas bonus for corroborated features (Layer 3)
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
        completeness_pct=completeness, layers_included=layers,
        narrative=template.format(score=round(100 * score, 1)),
        subscores={it["feature"].removeprefix("q_"): round(100 * it["alignment"]) for it in items},
        pulling_up=[(it["feature"].removeprefix("q_"), round(100 * it["alignment"])) for it in contrib if it["alignment"] >= score][:5],
        pulling_down=[(it["feature"].removeprefix("q_"), round(100 * it["alignment"])) for it in contrib if it["alignment"] < score][-5:],
        evidence_basis_pct=basis_mix,
        gwas_corroborated_weight_share_pct=gwas_share,
        superseded_by_l3=[d[0] for d in deduped],
        answered=len(items),
    )


def print_quiz(model):
    print(f"# {model['model']}  (Layer {model['layer']}, {len(model['questions'])} questions)\n")
    for i, q in enumerate(model["questions"], 1):
        print(f"Q{i}. [{q['domain']}]  {q['text']}")
        for j, o in enumerate(q["options"]):
            tags = ", ".join(o["trait_tags"]) or "(no trait)"
            print(f"    {chr(97+j)}) {o['label']}")
            print(f"       -> tags: {tags}  | alignment {o['alignment']}")
        if q.get("finding_context"):
            print(f"    * context: {q['finding_context'].strip()}")
        print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=TIER1)
    ap.add_argument("--print", action="store_true")
    ap.add_argument("--answers", help="JSON file: {question_id: option_index}")
    a = ap.parse_args()
    model = load_model(a.model)
    if a.print or not a.answers:
        print_quiz(model)
        return
    with open(a.answers, encoding="utf-8") as f:
        ans = json.load(f)
    res = score_answers(model, ans)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
