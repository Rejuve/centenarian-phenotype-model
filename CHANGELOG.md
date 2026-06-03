# Changelog

All notable changes to the deployable model package and its evidence/validation are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versions are the package version
(`centenarian_phenotype.__version__`). Model artifacts are versioned independently (per-tier `version`
fields, stamped into every result's `model_version`) and checksummed in
`centenarian_phenotype/models/MANIFEST.sha256`.

## [0.2.0] — 2026-06-03

Scientific framing, validation, and packaging overhaul. **Headline score math unchanged** (Layer-1
range 25.9–97.5%); 88 tests (from 20); CI matrix + lint + wheel + deterministic-artifact + secret scan.

### Added
- **Naive Bayes posterior layer** (`naive_bayes.py`): four-class posterior (general / nonagenarian /
  centenarian / supercentenarian), exposed as `class_posteriors` — derived, `calibration: heuristic_pending`.
- **Strict validation** (`validation.py`): `strict=True` default; structured 422s; warn mode.
- **Completeness split**: `model_depth_pct` / `response_completeness_pct` / `evidence_confidence_pct` /
  `usable_score` / `missing_high_value_inputs` / `next_best_data_action` (back-compat aliases kept).
- **Tier-3 raw-value → alignment mappers** (`mappers.py`) using referenced public cut-offs
  (NCEP/ADA/WHO/ACC-AHA/AHA-CDC/EWGSOP2/KDIGO); **biological-age clock registry** (`clocks.py`).
- **Phenotype decomposition** (`domains.py`) and the full product-output bundle.
- **Relative-longevity context** (`longevity.py` + Step G): validated HMD survival baselines by
  country × sex (`longevity_baselines.yaml`), and a **held-out NHANES 1999–2016 10-year mortality
  calibration** (`survival_calibration.yaml`) feeding `longevity_context.calibrated_mortality`.
- **Validation harness** (`scripts/validation/`): metric engine, NHANES Linked-Mortality-File parser,
  multi-cycle cohort builder, ablation by feature class, FETCH guides.
- **Tier 2 → 32 questions**: added subjective-loneliness item (`q_loneliness`) with `meta_analytic`
  basis; social_connectedness becomes the top Tier-2 domain (evidence-corroborated).
- **Docs**: `MODEL_CARD.md`, `VALIDATION_PLAN.md`, `AUDIT_FIXES.md`, `docs/SOURCE_REGISTRY.md`,
  `docs/DATA_STRATEGY.md` (incl. AI/LLM-use access screen), `docs/EVIDENCE_LONGEVITY_FACTORS.md`;
  `Makefile`, `scripts/make_manifest.py`, `CHANGELOG.md`, `CITATION.cff`, `examples/quickstart.ipynb`.

### Changed
- README reframed: evidence-weighted alignment (not a supervised-training artifact); NB posterior is
  derived/calibration-pending. METHODS §3.1 reconciled. Tier-3 panel widened (glucose, HbA1c, eGFR).
- API: `strict`/`context`/`posterior_kwargs` params; `ValidationError`→422; L2/L3 CORS no longer
  defaults to wildcard.

### Removed
- Stale point-in-time docs superseded by the above: `docs/model_card_stub.md`, `docs/audit_report.md`,
  `docs/documentation_gaps.md`.

### Claim boundary (what this release is / is not)
- **Is:** an *evidence-weighted centenarian-phenotype similarity* model with derived,
  calibration-pending Naive Bayes class posteriors, versioned Tier-3 mappers/clocks, and a
  **preliminary** mortality signal — the untrained score is associated with lower all-cause mortality
  in pooled NHANES 1999–2016 (age/sex-adjusted; held-out 10-yr calibration AUC 0.896, ECE 0.020).
- **Is not:** a validated centenarian-*prediction* model; not trained on outcomes; all-cause mortality
  is a survival *proxy*, not centenarian attainment; single US cohort, not externally replicated; not
  medical advice. See `MODEL_CARD.md` §3, §10 and `VALIDATION_PLAN.md`.

## [0.1.0]
- Initial three-tier evidence-weighted scoring package and research pipeline (pre-audit baseline).
