# Changelog

All notable changes to the deployable model package and its evidence/validation are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versions are the package version
(`centenarian_phenotype.__version__`). Model artifacts are versioned independently (per-tier `version`
fields, stamped into every result's `model_version`) and checksummed in
`centenarian_phenotype/models/MANIFEST.sha256`.

## [0.2.3] — 2026-06-04

Enabled the gut-microbiome layer and added an education/SES feature.

### Added
- **Gut microbiome (Tier 3, `access: microbiome`)** — replaced the pending block with two scoreable,
  literature-grounded features: alpha-diversity and centenarian-associated-taxa enrichment (Akkermansia
  muciniphila, Christensenellaceae, Bifidobacterium, SCFA-producers). Cited (Gut Microbes 2024
  PMC11364081; Biagi; Hainan cohort). Literature-grounded; not validated on our mortality cohort
  (NHANES has no microbiome).
- **Education / SES (Tier 2, `q_education`)** — NHANES age/sex-adjusted mortality association is strong
  and landmark-robust (std coef −0.25, n=49,315; top unmodelled candidate from the data-first
  re-check). Scored from external evidence (population SES gradient; cohort/era nuance documented).

### Changed
- tier2 v1.1 → v1.2 (33 items); tier3 v1.2 → v1.3; package 0.2.2 → 0.2.3.

## [0.2.2] — 2026-06-04

Tier-boundary clarification, expanded measured panel with validation, and an aging-biology corpus
backbone — toward publication-grade evidence.

### Changed
- **Tier boundary is now the necessity of a biospecimen/assay**, encoded per feature as an `access`
  tag (`self_report | anthropometric | lab | genomic | epigenetic`). Tier 2 = self-report +
  `anthropometric` (non-invasive, free/consumer-obtainable, assumed true for insights); Tier 3 =
  Tier 2 + `lab|genomic|epigenetic`. `grip_strength`, `muscle_strength`, `calf_circumference`,
  `body_mass_index` are now Tier 2; the 14 lab biomarkers + genomics + clocks are Tier 3.
- **Disease diagnoses are Tier-2 self-report only.** Removed the `clinical_disease_flags` block from
  `tier3_model.yaml` (the escaper/delayer phenotype is carried by Tier-2 self-report and the
  `disease_escape_similarity` decomposition); pruned `CONSTRUCT_MAP`/`CORE_L3_PANEL` accordingly.
- Tier-3 model artifact **v1.0 → v1.2**; package **0.2.1 → 0.2.2**.

### Added
- **Measured features WBC, grip strength, telomere length** pulled into the validation cohort
  (NHANES CBC / MGX 2011–2014 / TELO 1999–2002) with a `white_blood_cell` mapper; all three validate
  (age/sex-adjusted, landmark-robust).
- **DNA-methylation clock validation** — fetched the public NHANES DNAm file (`build_epi_cohort.py`);
  GrimAge/DunedinPACE/PhenoAge clocks are the strongest mortality signals in the set.
- **`docs/TIER2_TIER3_EVALUATION.md`** — compounding tier spec, NHANES-testability matrix, per-feature
  + tiered mortality association, PhenoAge benchmark, and the Tier-3 trajectory/efficacy-instrument use.
- **Aging-biology corpus backbone** — foundational queries (hallmarks of aging, geroscience,
  compression-of-morbidity, etc.) added to the academic scraper.

### Note
- Product/paywall gating is intentionally **not** represented in the open model (a separate app
  concern); the open artifacts carry only the scientific `access` taxonomy.

## [0.2.1] — 2026-06-03

Release-quality fixes from a follow-up review, plus the per-feature mortality analysis.

### Fixed
- **Mapper ↔ Tier-3 key alignment:** `ldl_cholesterol` now aliases to the Tier-3 `cholesterol`
  feature (accepted in strict mode); `map_panel()` resolves aliases and returns only
  tier-3-scoreable features in `clinical`, listing the rest (apob, systolic_bp, waist_circumference,
  alt, gait_speed) under `not_scoreable` — so its output is safe for `score(3, strict=True)`.
- **Security:** `posterior_kwargs` (Naive Bayes prior/likelihood overrides) removed from the public
  HTTP API to prevent client-side posterior manipulation; still available in the Python `score()`.
- **Doc consistency:** AUDIT_FIXES "Validated now" reconciled (preliminary NHANES signal, 88 tests);
  README test count (88) and validation-plan blurb; MODEL_CARD artifact version (tier2 v1.1).

### Added
- **Per-feature mortality association** (`scripts/validation/feature_association.py`): age/sex-adjusted
  per-feature association with all-cause mortality + a **landmark/lag** sensitivity (drops early
  deaths) as a reverse-causation guard. Cohort builder now emits `f_<feature>` alignment columns.

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
