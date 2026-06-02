# AUDIT_FIXES.md

What changed in response to the audit, what was deferred, and an honest statement of model status.
This PR targets the audit's **Priority 1** in full plus the high-value Priority 2/3 items that fix
production-safety and contradiction risks; remaining Priority 2/3 work is scoped as *planned* below
rather than stubbed.

Package version bumped **0.1.0 → 0.2.0**. Test suite **20 → 57 tests, all passing**. The headline
score math is unchanged (Layer-1 range still 25.9–97.5%), so existing integrations are unaffected.

---

## Per-finding status

| # | Finding | Status | What changed |
|---|---|---|---|
| 1 | Reconcile Naive Bayes vs evidence-weighted scoring | **Done** | `naive_bayes.py`: a genuine 4-class NB posterior (`P(class\|evidence) ∝ prior·∏ L^weight`) computed on top of the evidence-weighted score. Exposes `class_posteriors`, `centenarian_posterior`, `supercentenarian_posterior`, `evidence_weighted_similarity`, `total_similarity_score`. Likelihoods are explicitly flagged `calibration: heuristic_pending` (no labelled multi-class data — nonagenarian floor). Docs reconciled to "v1 = evidence-weighted alignment; calibrated NB = planned v2." Tests prove NB is used and responds to priors/likelihoods/evidence. |
| 2 | Completeness vs confidence | **Done** | Split into `model_depth_pct` (tier depth 30/50/80), `response_completeness_pct` (answered ÷ expected), `evidence_confidence_pct` (depth × completeness × provenance quality), `usable_score` (bool), `missing_high_value_inputs` (ranked). `completeness_pct`/`confidence_pct` retained as back-compat aliases. Docs + tests updated. |
| 3 | Strict validation | **Done** | `validation.py` + `strict=True` default. Unknown question IDs, unknown clinical features, out-of-range option indices, non-integer indices, clinical alignment outside `[0,1]`, and empty answers all raise `ValidationError` → **HTTP 422** with a structured report (`unknown_inputs`/`ignored_inputs`/`invalid_inputs`/`missing_required_inputs`/`out_of_range_values`). `strict=False` downgrades to `warnings`. |
| 4 | Raw-value → alignment mappers (Tier 3) | **Done (initial set)** | `mappers.py`: versioned, self-describing mappers for HDL, LDL, ApoB, triglycerides, glucose, HbA1c, systolic BP, BMI (U-shaped), waist, hs-CRP, eGFR, ALT, gait speed, grip strength, epigenetic age acceleration, DunedinPACE, telomere. Each carries units / accepted range / sex-age adjustment / provenance (NCEP/ADA/WHO/ACC-AHA/AHA-CDC/EWGSOP2/KDIGO) / evidence grade / version / missingness + warning behaviour. `map_panel()` round-trips into `score(3, ...)`. No invented cut-offs. |
| 6 | Clocks / biological-age modules | **Partial** | Epigenetic age-acceleration, DunedinPACE (pace) and telomere mappers added with raw/delta/pace distinction and limitations. A dedicated extensible `clocks/` interface (panel object: clock_name/raw/age_adjusted_delta/alignment/grade/limitations) is **planned**. |
| 7 | Phenotype decomposition | **Done** | `domains.py` emits `domain_scores`: cardiovascular, metabolic, inflammatory, functional, cognitive, survival-resilience, social-environmental, disease-escape, genetic, epigenetic. Primary endpoint unchanged (test asserts the headline number is unmoved). |
| 8 | Product output | **Done** | Added `total_similarity_score`, `class_posteriors`, `domain_scores`, `top_positive_drivers`, `top_negative_drivers`, `modifiable_drivers`, `non_modifiable_context`, `missing_high_value_inputs`, `evidence_confidence_pct`, `next_best_data_action`, `pro_unlock_opportunities`. README + MODEL_CARD carry the "similarity not prediction / higher confidence needs deeper data / result can change / not medical advice" language. |
| 9 | Model card + validation report | **Done** | New root [`MODEL_CARD.md`](MODEL_CARD.md) (intended/non-intended use, endpoint, evidence grades, bias, **known failure modes**, regulatory disclaimer, versioning/update policy, validation status) replaces the stub (now a pointer). New [`VALIDATION_PLAN.md`](VALIDATION_PLAN.md) with cohorts, metrics, acceptance gates, sequencing. |
| 10 | Doc contradictions | **Done** | METHODS §3.1/§3.7/§4, README, model-card stub, and scoring_api all reconciled: deployed = evidence-weighted alignment; NB posterior = derived/calibration-pending; calibrated NB + validation = planned. No remaining "trained/validated ML model" claims. |
| 11 | Tests & CI | **Tests done; CI partial** | +37 tests across NB, strict validation, mappers, completeness split, domains, API 422. CI matrix/lint/type/schema/wheel/deterministic-artifact additions are **planned** (existing CI + secret scan retained). |
| 12 | API / deployment hardening | **Done** | L2/L3 no longer default to wildcard CORS (deny + warn unless `CENTENARIAN_CORS_ORIGINS`/`cors_origins` set); L1 widget may stay permissive. Quiz endpoints already never expose internal weights/alignments; score endpoints now return `warnings` + provenance. Routes already versioned (`/v1`) and per-layer isolated. Auth for L3 is **planned** (deployment concern). |
| 5 | Expand public sources | **Planned** | Source-registry schema already exists (`data/processed/source_registry.csv`); the expansion (HRS/ELSA/SHARE/UKB/methylation/proteomic + nonagenarian set) and the enriched per-source metadata columns are scoped in `VALIDATION_PLAN.md` §1. |
| 13 | Reproducibility pipeline | **Planned** | Makefile/nox rebuild, checksums/manifests, artifact-generation script, and release process are scoped; pipeline steps D–F remain placeholders (already disclosed in README). |

## Files added/changed

- **Added:** `centenarian_phenotype/naive_bayes.py`, `validation.py`, `mappers.py`, `domains.py`;
  `MODEL_CARD.md`, `VALIDATION_PLAN.md`, `AUDIT_FIXES.md`;
  `tests/test_naive_bayes.py`, `tests/test_validation.py`, `tests/test_mappers.py`.
- **Changed:** `centenarian_phenotype/scoring.py`, `api.py`, `__init__.py`;
  `README.md`, `METHODS.md`, `docs/scoring_api.md`, `docs/model_card_stub.md`;
  `tests/test_scoring.py`, `tests/test_api.py`.

---

## Model status (required statement)

### Implemented now
- Evidence-weighted alignment scorer (the user-facing similarity number), Layers 1–3, unchanged math.
- Genuine four-class Naive Bayes **posterior computation** exposed as a derived output.
- Strict input validation with structured 422s; `strict=False` warn mode.
- Completeness split (model depth vs response completeness vs evidence confidence) + usability flag.
- Versioned, referenced raw-value → alignment mappers for the core Tier-3 panel.
- Phenotype decomposition (`domain_scores`) and the full product output bundle.
- L2/L3 CORS hardening; per-layer route isolation; versioned `/v1` routes.
- Complete model card + validation plan; reconciled docs.

### Validated now
- **Nothing is externally validated.** Behaviour is guarded by 57 unit tests (ranges, invariants,
  NB responsiveness, validation, mappers, decomposition). No retrospective/calibration/subgroup/
  ablation/missingness/temporal/external validation has been run.

### Planned next
- Calibrate the NB likelihoods against labelled multi-class feature distributions (close the
  nonagenarian-class gap) → flip `calibration` from `heuristic_pending` to `calibrated`.
- Dedicated extensible `clocks/` interface and expanded biomarker/source coverage.
- Reproducibility pipeline (Makefile/nox + manifests + artifact generator) and a release process.
- CI matrix / lint / type / schema-validation / wheel-build / deterministic-artifact checks; L3 auth.
- Execute `VALIDATION_PLAN.md` and promote results into `MODEL_CARD.md` §10.

### Not safe to claim yet
- That the model is "trained," "validated," or "clinically validated."
- That `class_posteriors` are **calibrated probabilities** of being in a class (they are uncalibrated
  ordinal resemblance posteriors and saturate with many features).
- Any **lifespan / age-at-death prediction**, diagnosis, or individual medical guidance.
- Subgroup fairness across sex/ancestry/geography (unmeasured).
