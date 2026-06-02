# Methods — Rejuve Centenarian Longevity Phenotype Model

A methods reference for the Centenarian Longevity Phenotype Model data pipeline and model. Written as a research methods appendix for the public repository.

---

## 1. Project statement

The Centenarian Longevity Phenotype Model is an open-source machine-learning model that scores how similar an individual's lifestyle, biomarker, and genetic profile is to people who have reached 100 years of age or more.

The model produces a **percentage similarity score** ("this profile is X% similar to verified centenarians"). It is **not** a lifespan predictor and does not estimate age at death.

The model ships in three tiers:

1. **Tier 1 (teaser quiz):** 12 behavioral questions across 11 domains, producing an instant similarity score. Free web / ad-funnel widget. (`models/tier1_model.yaml`)
2. **Tier 2 (application):** a **standalone 31-item mobile survey** — 18 NHANES-aligned behavioral questions (re-asked at greater depth than the teaser, mapped to the top-ranked centenarian features) plus 13 self-report clinical/health items. Free application tier; re-captures every variable fresh (no carry-over from Tier 1). (`tier2_model.yaml`)
3. **Tier 3 (premium):** Tier 2 plus blood biomarkers, 21 scored genomic variants (from a 508-variant curated catalogue), DNA-methylation clocks + telomere length, and microbiome (pending). Subscription tier. (`tier3_model.yaml`)

Scoring completeness rises across the tiers (~30% → ~50% → ~80%), grounded in longevity-heritability estimates (see `docs/model_card_stub.md`). The deployed v1 scorer is an **evidence-weighted alignment** model with per-feature provenance (§3.10); model outputs are designed to translate to PLN truth values (strength, confidence) for downstream integration with OpenCog Hyperon / AtomSpace / PLN, and a four-class Naive Bayes probabilistic version (§3.1) remains the target architecture.

---

## 2. Data sources

### Corpus

| source | records | description |
|---|---:|---|
| Academic papers | 10,105 | PubMed, Europe PMC, and Semantic Scholar abstracts and metadata. Abstract text only (no full text). |
| News / obituary / oral-history corpus | 2,788 | Scraped news, obituary, oral-history, and GDELT articles, tagged by `source_class`. |
| LongeviQuest atlas | 3,924 | Validated supercentenarian registry (110+), scraped from the public atlas. Complete gender. |
| LongeviQuest profiles | ~3,800 | Biographical profile blurbs, mined as `source_class = database_profile` (obituary-family records). |

### Reference datasets

| source | records | description |
|---|---:|---|
| Wikipedia supercentenarians | 219 | Supercentenarian records. |
| TidyTuesday centenarians | 124 | Oldest-people records (record-holder oriented; see limitations). |
| NHANES 2017–2018 | 9,254 | Demographics and biomarker panels, joined on `seqn`. |
| NHANES DNA methylation | 4,449 | Horvath, Hannum, SkinBlood, PhenoAge, GDF15Mort, B2MMort clocks. |
| GWAS Catalog (longevity) | 1,863 | Longevity / lifespan / aging / mortality associations. |
| WHO Global Health Observatory | 25,872 | Life expectancy at birth and HALE, by country × year × sex. |
| UN World Population Prospects 2024 | 44,857 | Demographic indicators (Estimates + Medium variant). |
| Human Mortality Database | 1,282,383 | Life tables for 41 countries × 3 sexes × ages × years, with per-country quality warnings. |
| Italian centenarian WGS | 158 MB | Whole-genome sequencing of semi-supercentenarians (metadata + sequences). |

A formal source registry is maintained at `data/processed/source_registry.csv`.

---

## 3. Methodology

### 3.1 Scoring approach

**What is deployed today (v1).** The shipped scorer (`centenarian_phenotype.score`) is an
**evidence-weighted alignment** model: each feature maps to an alignment in [0, 1], and the score is
the evidence-weighted mean, expressed as a percentage similarity to verified centenarians. It is
**not** a hand-built Bayesian network and **not** a deep-learning model. This evidence-weighted
similarity is the **user-facing number** (`score_pct` / `total_similarity_score` /
`evidence_weighted_similarity`).

**Four-class Naive Bayes posterior (derived output, calibration-pending).** On top of the v1 score
the engine also computes and returns a genuine **four-class Naive Bayes posterior**
(`centenarian_phenotype.naive_bayes`) over four reference classes — general population, nonagenarian
(90–99), centenarian (100–109), supercentenarian (110+) — via
`P(class | evidence) ∝ P(class) · ∏ L(alignmentᵢ | class)^{weightᵢ}`. It is exposed as
`class_posteriors`, `centenarian_posterior`, and `supercentenarian_posterior`, and is what maps to
PLN truth values. **The Naive Bayes *math* is implemented and tested; its *likelihoods* are not yet
data-calibrated** — each class is given an explicit, monotone alignment centroid rather than
likelihoods estimated from labelled per-class feature distributions, because the corpus has **no
cleanly-named 90–99 subjects** (subject age is floored at 100 — see *Nonagenarian floor* in §5). The
posterior layer is therefore flagged `calibration: "heuristic_pending"` and the headline number
remains the evidence-weighted similarity. A **fully calibrated four-class Naive Bayes is the planned
v2 endpoint**; reaching it requires labelled multi-class feature distributions (see
`VALIDATION_PLAN.md`).

Per-factor proximity is scored on a 0–100 scale and aggregated into an overall percentage similarity,
with per-feature subscores, interpretive `domain_scores`, and the class posteriors all exposed so
that contributing factors are visible.

**Relative-longevity baseline (wired in).** A validated demographic anchor is computed by Step G
(`scripts/pipeline/step_g_longevity_baselines.py`) from Human Mortality Database period life tables
and bundled as `centenarian_phenotype/models/longevity_baselines.yaml` (123 country × sex rows): life
expectancy at 60/65 and P(reach 90/100 | alive at 65/80). `centenarian_phenotype.longevity` exposes
this so a score can be framed *relative to the person's own country and sex* (e.g. ~7.6% of Japanese
women alive at 65 reach 100, 2024). The population baseline is **validated demography**; the mapping
from phenotype score → personal survival trajectory is **calibration-pending** and kept separate
(see `MODEL_CARD.md` §4, `VALIDATION_PLAN.md`). The remaining country exposomic adjustments
(centenarian-density prior, Blue Zone configuration, HMD quality-warning CI widening) are specified
but not yet wired in.

### 3.2 Feature discovery

Features are data-first, discovered from the academic and news corpus via the NLP pipeline. Keyword maps in the scrapers served only as seeds and are not the final feature list. Discovered phrases receive a tier label only when they map to a NHANES variable; all other phrases are surfaced as exploratory and reviewed before promotion.

The NLP pipeline (spaCy `en_core_web_sm` 3.8.0) applies a boilerplate filter to news text (academic abstracts pass through unchanged), performs named-entity recognition, and extracts five phrase types (noun phrase, verb phrase, attribution, attribution-place, attribution-product). PERSON entities are excluded from the feature vocabulary; GPE/LOC/FAC/ORG entities are retained because they carry exposomic signal. Per-feature aggregates include corpus lift, weighted score, distinct-individual count, country count, cross-cultural flag, NHANES mapping, and direction of association.

### 3.3 Deduplication

News articles are deduplicated by 7-word-shingle containment clustering. 1,117 of 2,788 news rows are syndicated duplicates across 220 clusters; these are recorded in `data/processed/news_dedup_report.csv` and excluded at NLP load time via a blacklist.

### 3.4 Biomarker reference extraction

Biomarker references are extracted data-first from centenarian-focused or biomarker-tagged academic abstracts. Each mention is tagged with a value and unit or an OR/HR/RR ratio, and with a subject class derived from the ages mentioned. Mentions are cross-validated against NHANES column names and GWAS longevity traits, and assigned an evidence grade.

Pooled effect estimates are produced by stratified DerSimonian-Laird random-effects meta-analysis, with one stratum per (biomarker × contrast type × subject class). A commensurability guardrail prevents pooling across incompatible effect measures (for example, odds ratios are never pooled with hazard ratios).

### 3.5 Biomarker naming schema

All four biomarker files use a single standardized name schema: `biomarker_name_raw` (the as-extracted original) and `biomarker_name` (a snake_case canonical term that serves as the universal join key). Per-mention and audit files carry both columns; aggregate files carry the canonical column only.

### 3.6 LongeviQuest gender integration

The LongeviQuest atlas is treated as the authoritative gender source for verified supercentenarians and is merged into `supercentenarians.csv` on name with birth and death dates. On conflict, LongeviQuest values take precedence; missing values are filled. The merge raised the known-gender female share to 89.3%, consistent with the established ~90% female reality for validated supercentenarians.

### 3.7 Stack

Python pipeline producing CSV/Parquet, spaCy NLP, a dependency-light scoring package (evidence-weighted alignment + a derived four-class Naive Bayes posterior layer; `pyyaml` only at runtime), FastAPI service, and Flutter application plus React widget. The bundled tier models (approximately 50 KB of YAML) ship with the application; end users do not run the scrapers. Note: the models are **curated evidence specifications**, not the output of a supervised training run — see §3.1 for the deployed-vs-planned scoring distinction.

### 3.8 Population baselines (Step D)

NHANES 2017–2018 (subjects aged 60+, survey-weighted with `WTMEC2YR`, Wilson confidence intervals) supplies population prevalence for behavioral and clinical features. Centenarian-vs-population association is computed two ways: **status_composition** (apples-to-apples within a documented domain — e.g. smoking never/former/current), which is methodologically valid and **gold-eligible**; and **mention_rate** (how often a trait is documented), which is documentation-biased and **never** confers gold. Only status_composition findings confer gold (smoking and the moderate-vs-no alcohol split). LongeviQuest is case data and is never used as a population baseline. Outputs: `step_d_population_baselines.csv`, `step_d_trait_associations.csv`.

### 3.9 Feature layer assignment and evidence scoring (Step E)

Each discovered feature receives a **composite evidence score** (inputs normalized 0–1 before weighting so no input dominates by scale: corroboration tier 0.35, individual count 0.25, academic paper count 0.25, prevalence ratio 0.15; `gwas_corroborated` as a 0/1 flag weighted 0.00 at Layers 1–2) and is assigned to Layer 1/2/3 by self-reportability and measurement requirement. Distinct behavioral domains (purpose, resilience, social, family) are deliberately **not** merged. Output: `step_e_feature_layer_assignments.csv` (L1 54 / L2 5 / L3 46).

**Corroboration tiers.** Bronze = individual news/profile evidence; silver = academic corroboration; **gold = a quantified centenarian-vs-population association from an independent population reference** (NHANES/WHO), computed at Step D. Mere presence in a dataset is not gold, and case data (LongeviQuest) is never a baseline.

### 3.10 Three-tier scoring model (Step F)

The deployed scorer (`scripts/pipeline/step_f_scoring.py`, `score_profile`) computes an **evidence-weighted alignment**:

> `score% = 100 × Σ(weight × alignment) / Σ(weight)`

with a 95% interval from the weighted variance. Each answer option / feature carries an `alignment` (0–1) and a **`basis` provenance tag** — one of `measured` (Step-D ratio), `academic_corroborated`, `documented_positive`, `reasoned_gradient`, `neutral_context`, `external_evidence`, `clinical_literature`, `heritability`, `disease_escape`, `epigenetic`, `genomic`. Every result reports **`evidence_basis_pct`**, the share of the score resting on each basis, so scores map to data reality rather than authoring judgment (a typical Layer-1 score is only ~8% hard `measured` gold). The three tier models are versioned YAML in `models/`.

Key rules: physical activity is scored on **regularity, not intensity** (the validated signal); diet is **near-flat** (context-dependent; only a mild plant-forward/moderation lean from the academic corpus); **`gwas_corroborated` weight is 0.00 at Layers 1–2 and reintroduced at Layer 3** (≈0.15; a known under-representation of genetics at the behavioral layers, not a finding); and **deepest layer wins** — Layer-2 self-report items are coarse versions of Layer-3 measured constructs, so a supplied measurement supersedes the self-report (construct-level dedup, reported via `superseded_by_l3`). The evidence-weighted alignment scorer is the deployed v1; the four-class Naive Bayes / PLN probabilistic framing (§3.1) is the planned upgrade (see `docs/ROADMAP.md`).

### 3.11 Genomic and epigenetic deepening

**Genomic.** `scripts/pipeline/step_e_genomic_panel.py` curates `gwas_longevity.csv` into a panel of genome-wide-significant (p < 5e-8) longevity-trait variants (`data/processed/genomic_panel_curated.csv`): 508 variants across 426 genes, 80 with interpretable effect direction (read from the catalog trait + OR/BETA, never invented), of which 21 are scored at Layer 3. Candidate corroboration against our own centenarian-vs-control WGS (`cent_WGS.txt`) matches only 2 variants by position — a **GRCh38 genome-build mismatch (a pipeline fix via liftover, not a scientific error)**; the 21 scored variants remain valid because their directions come from the GWAS Catalog independent of the WGS check.

**Epigenetic.** DNA-methylation clocks (Horvath, Hannum, SkinBlood, PhenoAge, GrimAge, DunedinPACE) and telomere length sit at Layer 3; `nhanes_methylation.csv` provides a population baseline making epigenetic age acceleration **gold-eligible** (the quantified centenarian delta is deferred, not invented). **Body composition** is U-shaped — obesity *and* late-life underweight/weight-loss are both adverse.

---

## 4. Key decisions

- The deployed v1 scorer is **evidence-weighted alignment**; a four-class Naive Bayes posterior is computed on top as a derived, calibration-pending output (a fully calibrated NB is the planned v2). Neither is a binary centenarian / non-centenarian frame.
- Features are data-first and receive tier labels only on NHANES mapping.
- Country-level exposomic context is applied at scoring time and sits outside the scoring core (specified, not yet wired into the package).
- The Blue Zone adjustment is an explicit, auditable exception to the data-first rule.
- Centenarian-class biomarker distributions are sourced from the literature and curation rather than NHANES, which has too few subjects aged 95 and over.
- Attribution (centenarian-voice quotation) is not used as a feature class; the signal did not survive deduplication. Tier-1 lifestyle scoring uses noun/verb-phrase and NHANES-mapped predictors.
- LongeviQuest is the authoritative gender source; the TidyTuesday subset is retained but flagged as non-representative.

---

## 5. Known limitations

- **News corpus volume.** 2,788 raw articles (1,671 after deduplication). The academic corpus (10,105) is the primary backbone.
- **Abstract-only academic corpus.** No full text is available. Control-group prevalence is extractable from approximately half of control-group abstracts; the remainder relies on NHANES/WHO fallback.
- **Nonagenarian floor.** The news corpus contains no cleanly named 90–99 subjects (subject age is floored at 100), so the nonagenarian class is unpopulated from news without additional data.
- **TidyTuesday gender skew.** The TidyTuesday subset is 80.6% male (record-holder oriented) and is not population-representative; it is retained but down-weighted relative to LongeviQuest.
- **Grade C biomarkers.** Several biomarkers with genuine literature signal (epigenetic clocks, VO2 max, gait speed, microbiome, and others) remain Grade C because their values appear in main-text tables rather than abstracts.
- **NHANES encoding.** `nhanes_merged.csv` stores categorical values as CDC numeric codes; a codebook decode and a missing-value sentinel mapping are required before computing population baselines.
- **HMD quality warnings.** 30 of 50 countries carry documented warnings; these are propagated as a confidence penalty, not a score penalty.
- **LongeviQuest profile scrape.** Profile slugs are derived from names; approximately five distinct same-name individuals are not retrieved because of slug collisions (LongeviQuest disambiguates with URL suffixes). The loss is approximately 0.13% and does not affect aggregate statistics.

---

## 6. Changelog

| date | change |
|---|---|
| 2026-05-31 | NLP pipeline completed; deduplication applied; feature registry built (boilerplate filter v2, attribution typing, distinct-individual count, direction of association). |
| 2026-05-31 | Phase 3 reference datasets acquired (GWAS, WHO, UN WPP, NHANES methylation, HMD with quality warnings). |
| 2026-05-31 | Biomarker extraction v1 (18 Grade A, 28 Grade B, 411 Grade C). |
| 2026-06-01 | Phase 3 architecture defined (scoring, confidence intervals, proximity scoring, partial-input handling, NHANES baselines, country exposomic context). |
| 2026-06-01 | Targeted PubMed scrape for under-represented biomarkers (+1,916 papers, 29 queries). |
| 2026-06-01 | Biomarker extraction v2 with normalizer fix (24 Grade A, 38 Grade B, 359 Grade C). |
| 2026-06-01 | Stratified DerSimonian-Laird biomarker pooling with commensurability guardrail. |
| 2026-06-01 | LongeviQuest full atlas (3,924 records) scraped and merged into the supercentenarian registry; known-gender female share corrected to 89.3%. |
| 2026-06-01 | LongeviQuest profile blurbs mined as `database_profile` source records and integrated into the trait pipeline. |
| 2026-06-01 | Biomarker name columns standardized to `biomarker_name_raw` + `biomarker_name` across all four biomarker files. |
| 2026-06-01 | Project audit produced (`audit_report.md`, `data_dictionary.md`, `documentation_gaps.md`). |
| 2026-06-01 | Step D population baselines (NHANES 60+, survey-weighted, Wilson CIs); deferred-gold framework (status_composition valid, mention_rate documentation-biased); smoking restructured to `smoking_status_{never,former,current}`. |
| 2026-06-01 | Step E feature layer assignment + composite evidence scoring (`step_e_feature_layer_assignments.csv`, L1 54 / L2 5 / L3 46); domains kept distinct; `gwas_biomarker_pathways.csv` created. |
| 2026-06-02 | Step F three-tier scoring engine (`step_f_scoring.py`, `models/tier1-3_model.yaml`): evidence-weighted alignment, per-feature `basis` provenance, `evidence_basis_pct`, completeness ladder 30/50/80, `gwas_corroborated` reintroduced at Layer 3, construct-level dedup. |
| 2026-06-02 | Genomic deepening: curated 508-variant longevity panel (`genomic_panel_curated.csv`, `step_e_genomic_panel.py`), 21 scored; WGS build-mismatch documented. Epigenetic deepening: methylation clocks + telomere length at L3, NHANES methylation anchor. Body-composition U-shape. |
| 2026-06-02 | Tier 1 finalized at 12 questions; Tier 2 rebuilt as a standalone 31-item app survey (18 NHANES-aligned behavioral + 13 self-report clinical, incl. self-rated health, cholesterol, disease burden, depression, bone health); no Tier-1 carry-over. |
