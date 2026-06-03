# AUDIT_FIXES.md

What changed in response to the audit, what was deferred, and an honest statement of model status.
This PR targets the audit's **Priority 1** in full plus the high-value Priority 2/3 items that fix
production-safety and contradiction risks; remaining Priority 2/3 work is scoped as *planned* below
rather than stubbed.

Package version bumped **0.1.0 → 0.2.0**. Test suite **20 → 81 tests, all passing**. The headline
score math is unchanged (Layer-1 range still 25.9–97.5%), so existing integrations are unaffected.

---

## Per-finding status

| # | Finding | Status | What changed |
|---|---|---|---|
| 1 | Reconcile Naive Bayes vs evidence-weighted scoring | **Done** | `naive_bayes.py`: a genuine 4-class NB posterior (`P(class\|evidence) ∝ prior·∏ L^weight`) computed on top of the evidence-weighted score. Exposes `class_posteriors`, `centenarian_posterior`, `supercentenarian_posterior`, `evidence_weighted_similarity`, `total_similarity_score`. Likelihoods are explicitly flagged `calibration: heuristic_pending` (no labelled multi-class data — nonagenarian floor). Docs reconciled to "v1 = evidence-weighted alignment; calibrated NB = planned v2." Tests prove NB is used and responds to priors/likelihoods/evidence. |
| 2 | Completeness vs confidence | **Done** | Split into `model_depth_pct` (tier depth 30/50/80), `response_completeness_pct` (answered ÷ expected), `evidence_confidence_pct` (depth × completeness × provenance quality), `usable_score` (bool), `missing_high_value_inputs` (ranked). `completeness_pct`/`confidence_pct` retained as back-compat aliases. Docs + tests updated. |
| 3 | Strict validation | **Done** | `validation.py` + `strict=True` default. Unknown question IDs, unknown clinical features, out-of-range option indices, non-integer indices, clinical alignment outside `[0,1]`, and empty answers all raise `ValidationError` → **HTTP 422** with a structured report (`unknown_inputs`/`ignored_inputs`/`invalid_inputs`/`missing_required_inputs`/`out_of_range_values`). `strict=False` downgrades to `warnings`. |
| 4 | Raw-value → alignment mappers (Tier 3) | **Done (initial set)** | `mappers.py`: versioned, self-describing mappers for HDL, LDL, ApoB, triglycerides, glucose, HbA1c, systolic BP, BMI (U-shaped), waist, hs-CRP, eGFR, ALT, gait speed, grip strength, epigenetic age acceleration, DunedinPACE, telomere. Each carries units / accepted range / sex-age adjustment / provenance (NCEP/ADA/WHO/ACC-AHA/AHA-CDC/EWGSOP2/KDIGO) / evidence grade / version / missingness + warning behaviour. `map_panel()` round-trips into `score(3, ...)`. No invented cut-offs. |
| 6 | Clocks / biological-age modules | **Done** | `clocks.py`: extensible registry across all requested kinds (dna_methylation, clinical_chemistry, mortality_risk, pace_of_aging, telomere, frailty_functional, + pending proteomic/metabolomic/microbiome). Each clock declares tissue/sample, platform/assay, availability (free_open / requires_coefficients / restricted), evidence grade, limitations, version. `compute_panel()` distinguishes raw biological age / age-acceleration delta / pace and emits the panel (clock_name, raw_value, age_adjusted_delta, alignment, evidence_grade, limitations). `to_clinical_alignments()` feeds **only scoreable clocks** into the score (no silent mixing). |
| 7 | Phenotype decomposition | **Done** | `domains.py` emits `domain_scores`: cardiovascular, metabolic, inflammatory, functional, cognitive, survival-resilience, social-environmental, disease-escape, genetic, epigenetic. Primary endpoint unchanged (test asserts the headline number is unmoved). |
| 8 | Product output | **Done** | Added `total_similarity_score`, `class_posteriors`, `domain_scores`, `top_positive_drivers`, `top_negative_drivers`, `modifiable_drivers`, `non_modifiable_context`, `missing_high_value_inputs`, `evidence_confidence_pct`, `next_best_data_action`, `pro_unlock_opportunities`. README + MODEL_CARD carry the "similarity not prediction / higher confidence needs deeper data / result can change / not medical advice" language. |
| 9 | Model card + validation report | **Done** | New root [`MODEL_CARD.md`](MODEL_CARD.md) (intended/non-intended use, endpoint, evidence grades, bias, **known failure modes**, regulatory disclaimer, versioning/update policy, validation status) replaces the stub (now a pointer). New [`VALIDATION_PLAN.md`](VALIDATION_PLAN.md) with cohorts, metrics, acceptance gates, sequencing. |
| 10 | Doc contradictions | **Done** | METHODS §3.1/§3.7/§4, README, model-card stub, and scoring_api all reconciled: deployed = evidence-weighted alignment; NB posterior = derived/calibration-pending; calibrated NB + validation = planned. No remaining "trained/validated ML model" claims. |
| 11 | Tests & CI | **Tests done; CI partial** | 81 tests (from 20) across NB, strict validation, mappers, clocks, domains, longevity, the validation harness, and API 422. CI matrix/lint/type/schema/wheel/deterministic-artifact additions are **planned** (existing CI + secret scan retained). |
| 12 | API / deployment hardening | **Done** | L2/L3 no longer default to wildcard CORS (deny + warn unless `CENTENARIAN_CORS_ORIGINS`/`cors_origins` set); L1 widget may stay permissive. Quiz endpoints already never expose internal weights/alignments; score endpoints now return `warnings` + provenance. Routes already versioned (`/v1`) and per-layer isolated. Auth for L3 is **planned** (deployment concern). |
| 5 | Expand public sources | **Advanced (registry + prioritized candidates done; acquisition pending)** | New tracked [`docs/SOURCE_REGISTRY.md`](docs/SOURCE_REGISTRY.md) defines the enriched schema (license/access, raw location, processed artifact, population, age range, cent relevance, train/validate/contextual, bias), documents current sources against it, and lists **prioritized freely-available candidates ordered by validation ROI** — NHANES mortality linkage (P1), HRS / Gateway-to-Global-Aging to close the nonagenarian gap (P1), more GWAS + GEO methylation (P2), IDL/GRG external validation (P2). Actual acquisition/ingestion is the next step. |
| 13 | Reproducibility pipeline | **Planned** | Makefile/nox rebuild, checksums/manifests, artifact-generation script, and release process are scoped; pipeline steps D–F remain placeholders (already disclosed in README). |

## Files added/changed

- **Added:** `centenarian_phenotype/naive_bayes.py`, `validation.py`, `mappers.py`, `domains.py`,
  `clocks.py`; `MODEL_CARD.md`, `VALIDATION_PLAN.md`, `AUDIT_FIXES.md`, `docs/SOURCE_REGISTRY.md`;
  `tests/test_naive_bayes.py`, `tests/test_validation.py`, `tests/test_mappers.py`,
  `tests/test_clocks.py`.
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
- Extensible biological-age clock interface (`clocks.py`) with a panel output and scoreable-only feed.
- **Relative-longevity context (`longevity.py` + Step G):** validated HMD population survival
  baselines by country × sex (123 rows bundled), with a calibration-pending phenotype trajectory band
  kept strictly separate. Threaded into `score(..., context=...)` without changing the similarity number.
- **Validation/calibration harness (`scripts/validation/`) — with a first real result.** Pure-Python
  metric engine (AUC, reliability/ECE/Brier, fitted score→mortality calibration, subgroup AUC) + an
  NHANES Linked-Mortality-File parser (NCHS layout) and two cohort builders (2017–2018 CSVs; and
  `build_cohort_from_xpt.py` which auto-downloads & POOLS any earlier cycles' XPT + LMF, with ablation
  by feature class). **First powered run (pooled NHANES 2005–2010, N=18,290, 3,014 deaths): the
  untrained phenotype score is associated with lower all-cause mortality independent of age and in
  both sexes** (adj. weight −0.34; protective in every age band). Ablation: behavioral/self-report
  block strongest (−0.41), 5-marker lab panel weaker (−0.20). Survival proxy, single cohort, not
  centenarian attainment — see VALIDATION_PLAN §3b.
- Tracked enriched source registry + prioritized freely-available candidate sources toward validation.
- Phenotype decomposition (`domain_scores`) and the full product output bundle.
- L2/L3 CORS hardening; per-layer route isolation; versioned `/v1` routes.
- Complete model card + validation plan; reconciled docs.

### Validated now
- **Nothing is externally validated.** Behaviour is guarded by 57 unit tests (ranges, invariants,
  NB responsiveness, validation, mappers, decomposition). No retrospective/calibration/subgroup/
  ablation/missingness/temporal/external validation has been run.

### Planned next
- **Acquire the P1 sources** in `docs/SOURCE_REGISTRY.md` (NHANES mortality linkage; HRS /
  Gateway-to-Global-Aging) to close the nonagenarian-class gap, then **calibrate the NB likelihoods**
  → flip `calibration` from `heuristic_pending` to `calibrated`.
- Wire the clinical/proteomic/metabolomic/microbiome clocks in `clocks.py` from `pending` to
  scoreable as reference distributions are sourced; expand biomarker/GWAS coverage.
- Reproducibility pipeline (Makefile/nox + manifests + artifact generator) and a release process.
- CI matrix / lint / type / schema-validation / wheel-build / deterministic-artifact checks; L3 auth.
- Execute `VALIDATION_PLAN.md` and promote results into `MODEL_CARD.md` §10.

### Not safe to claim yet
- That the model is "trained," "validated," or "clinically validated."
- That `class_posteriors` are **calibrated probabilities** of being in a class (they are uncalibrated
  ordinal resemblance posteriors and saturate with many features).
- Any **lifespan / age-at-death prediction**, diagnosis, or individual medical guidance.
- Subgroup fairness across sex/ancestry/geography (unmeasured).
