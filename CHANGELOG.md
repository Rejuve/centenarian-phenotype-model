# Changelog

All notable changes to the deployable model package and its evidence/validation are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versions are the package version
(`centenarian_phenotype.__version__`). Model artifacts are versioned independently (per-tier `version`
fields, stamped into every result's `model_version`) and checksummed in
`centenarian_phenotype/models/MANIFEST.sha256`.

## [0.2.5] — 2026-06-05

### Added
- **Thyroid (serum TSH) and testosterone as validated Tier-3 lab biomarkers.** TSH uses a
  longevity-shifted mapper (high-normal / mildly-elevated favourable — the thyroid paradox of
  longevity, Atzmon 2009), not a plain "normal" cut-off. Both were wired into the NHANES cohort
  builder (TSH 2007–2012 `THYROD`/`LBXTSH1`; testosterone 2011–2016 `TST`/`LBXTST`) and validated:
  TSH age/sex-adjusted coef −0.080 (−0.099 in the 65+ stratum, landmark-robust — paradox confirmed);
  testosterone −0.040 (weakly protective, confounded → conservative 0.40 weight).
- **`validation_status` on every Tier-3 biomarker** (`validated_nhanes` | `literature_only`), so each
  feature is either cohort-validated or honestly evidence-tagged — none silently in between.
- **Whole-endpoint (ELC) validation** (`scripts/validation/endpoint_validation.py`,
  `scripts/analysis/function_threshold_test.py`, docs §7): the score validated against the endpoint's two
  observable faces — survival (AUC 0.71 raw / 0.88 age-sex-adj, ECE 0.012, n=24,678) and a concurrent
  healthspan composite (objective-only AUC 0.63, non-circular; full 0.75 partly circular). Compounding
  tiers confirmed (full 0.707 > self-report 0.688 > labs 0.658). Functional bar made **graded** (full /
  minimal-assistance / dependent) from the self-rated-health gap test; depression kept as a separate
  control axis (Keyes). Documents the circular-vs-non-circular and correlate-vs-driver logic.
- **Empirical epigenetic oldest-old anchor** (`scripts/validation/epi_oldest_old_anchor.py`,
  `epigenetic_population_anchor` in tier3): the centenarian-favourable clock direction is now MEASURED on
  AI-permissible public methylomes with verified 89–103-year-olds (GEO GSE30870 + GSE40279, biolearn
  clocks), not declared. Mean epigenetic age acceleration deepens monotonically with survival
  (<60 +1.1 yr → 90–99 −10.1 → 100+ −13.7); all 29 individuals aged 90+ are biologically younger than
  chronological. Replaces the previously-deferred centenarian-vs-population delta.

### Changed
- tier3 v1.4 → v1.5; package 0.2.4 → 0.2.5.
- Renamed the vague `euthyroid` feature to `thyroid_tsh` with the corrected longevity direction.
- Genomic catalogue described honestly: the live panel is **21 inlined variants + 2 polygenic
  scores**; the 80-variant curated set is a **direction-resolved reserve** (`scored_by_engine: false`),
  not part of the live feature count.

### Removed
- `hypertriglyceridemia` (redundant with the `triglycerides` feature).

## [0.2.4] — 2026-06-05

### Added
- **Open longevity polygenic scores (Tier 3, `access: genomic`)** — `pgs_longevity` (PGS Catalog
  PGS000906) and `pgs_parental_lifespan` (Timmers 2019), drawn from the PGS Catalog longevity trait
  (EFO:0004300). Open coefficient files, applied when a user's genotype yields the score; same
  literature-grounded evidence class as the single variants, with cohort validation awaiting a
  genotyped, outcome-linked dataset (UK Biobank / dbGaP).
- **Validated folding the DNA-methylation clocks into the composite Tier-3 score** on the 1999–2002
  DNAm subsample (`composite_with_clocks.py`): age/sex-adjusted signal strengthens −0.50 → −0.65.
- **README "Validation (preliminary)" section** with the current NHANES + PhenoAge readouts.

### Changed
- tier3 v1.3 → v1.4; package 0.2.3 → 0.2.4.

## [0.2.3] — 2026-06-04

Enabled the gut-microbiome layer (literature-grounded), tightened the Naïve Bayes posterior, and
addressed audit findings.

### Added
- **Gut microbiome (Tier 3, `access: microbiome`)** — replaced the pending block with two scoreable,
  literature-grounded features: alpha-diversity and centenarian-associated-taxa enrichment (Akkermansia
  muciniphila, Christensenellaceae, Bifidobacterium, SCFA-producers). Cited (Gut Microbes 2024
  PMC11364081; Biagi; Hainan cohort). Literature-grounded; **not validated on any cohort** (NHANES has
  no microbiome) — plan to derive a centenarian-vs-control reference from open data is documented.

### Changed
- **Demoted the four-class Naïve Bayes posterior to experimental/research-only.** It is heuristic with
  no 90–99 data and declared (not learned) centroids. It is now **suppressed for sparse inputs**
  (`< 4` scored features, so a near-empty profile no longer shows class mass) and **hidden from the
  public HTTP API** (Python `score()` retains it for research). README/MODEL_CARD reframed so the
  evidence-weighted similarity score (the validated core) leads, not the posterior.
- tier3 v1.2 → v1.3; package 0.2.2 → 0.2.3.

### Fixed (audit)
- A profile with **no scoreable inputs now raises `ValidationError` even in non-strict mode** (was
  returning a hollow score with a degenerate CI).
- `requirements.txt` Python-version comment corrected (tested on 3.10+, not "3.14").
- Tidied a split string in the `white_blood_cell` mapper definition.
- Documented the `ldl_cholesterol → cholesterol` Tier-3 alias and the rationale for the news corpus.

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
