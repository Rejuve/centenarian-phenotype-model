# Rejuve Centenarian Longevity Phenotype Model

An open-source model that scores how similar a person's lifestyle, biomarker, and genetic profile is to people who **verifiably lived to 100 or more**.

> **This is a similarity score, not a lifespan predictor.** The output is "your profile is *X%* similar to verified centenarians" — never a predicted age at death. Higher confidence requires deeper data, and your result can change as more data is added. This is not medical advice or diagnosis.

**Model status (read this first):** the deployed v1 scorer is an **evidence-weighted alignment** model built from a curated evidence corpus — *not* the output of a supervised training run, and *not* yet externally validated. It additionally returns a **four-class Naive Bayes posterior** (general population / nonagenarian / centenarian / supercentenarian) as a *derived, calibration-pending* output. A score can be framed **relative to your own country and sex** using a *validated* demographic baseline (HMD life tables), while the mapping from phenotype to personal survival odds stays *calibration-pending*. A fully calibrated Naive Bayes and external validation are the **planned v2**. See [`MODEL_CARD.md`](MODEL_CARD.md), [`VALIDATION_PLAN.md`](VALIDATION_PLAN.md), and [`AUDIT_FIXES.md`](AUDIT_FIXES.md) for exactly what is implemented, validated, planned, and not-yet-safe-to-claim.

The model ships in three tiers, each an evolution of the one before:

- **Tier 1** — 12-question behavioral teaser quiz, instant shareable similarity score (free web/ad widget).
- **Tier 2** — standalone 31-item app survey: 18 NHANES-aligned behavioral + 13 self-report clinical/health items (free app).
- **Tier 3** — **Tier 2 in full** plus blood biomarkers, 21 genomic variants, DNA-methylation clocks + telomere length, and microbiome pending (subscription).

Completeness accumulates across the tiers (~30% → ~50% → ~80%): each tier carries all of the previous tier's questions into its score and adds deeper evidence on top.

Built data-first from an academic + news corpus and validated reference datasets (NHANES, WHO, UN WPP, HMD, GWAS, LongeviQuest). Designed to interoperate with OpenCog Hyperon / PLN: the four-class Naive Bayes posteriors map to PLN truth values (strength, confidence).

---

## Quickstart

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

Scripts run from the repository root: `python <script>.py`. Set `PYTHONIOENCODING=utf-8` for scripts that emit non-ASCII text (Windows/PowerShell: also `chcp.com 65001 > $null`).

The bundled tier models (~50 KB of curated YAML — evidence specifications, not a supervised-training artifact) ship with the application; **end users never run the scrapers or pipeline below.** This repository is for building and reproducing the model.

---

## Scoring package & API

The deployable model is the `centenarian_phenotype` package (dependency-light; bundles its own model YAMLs — no `data/` needed at runtime).

```bash
pip install -e .                 # core scorer
pip install -e ".[api]"          # + FastAPI service
python -c "import centenarian_phenotype as cp; print(cp.score(1, {'q_diet': 0}))"
uvicorn centenarian_phenotype.api:app --reload     # http://127.0.0.1:8000/docs
```

Each layer deploys independently (web widget = L1, app = L2+L3). Contract: `docs/scoring_api.md`. Deployment (AWS Lambda / CORS / Flutter): `docs/deployment.md`.

## Reproducibility & release

`Makefile` wraps the common tasks: `make install | test | lint | build | manifest-check | validate |
longevity-baselines`.

- **Deterministic artifacts:** the bundled model YAMLs are checksummed in
  `centenarian_phenotype/models/MANIFEST.sha256`; CI runs `make manifest-check`, so any model edit must
  bump the model `version` and regenerate the manifest (`make manifest`).
- **Regenerable data:** the `data/` tree is gitignored (third-party/large/personal). Rebuild processed
  artifacts from source via the pipeline (`scripts/pipeline/step_*`); validation cohorts are fetched on
  demand (`scripts/validation/`, see `FETCH_MORTALITY.md`). Nothing under `data/` ships in the wheel.
- **Release stamps a tuple:** package `__version__` + per-tier model `version`s (in every result's
  `model_version`) + the data snapshot the artifacts were built from + a changelog entry (METHODS) +
  current validation status (`MODEL_CARD.md` §10).

## Development & security

```bash
pip install -e ".[test,api]" && python -m pytest -q   # 20 tests
git config core.hooksPath .githooks                    # enable the secret-scan pre-commit hook
```

- **API keys are read from environment variables** (`NCBI_API_KEY`, `SEMANTIC_SCHOLAR_API_KEY`) — never hardcode them.
- A **secret-scan pre-commit hook** (`.githooks/pre-commit`, dependency-free) blocks commits containing key-like strings; `.pre-commit-config.yaml` offers the gitleaks alternative.
- **CI** (`.github/workflows/ci.yml`) runs the test suite and a gitleaks secret scan on every push/PR.

---

## Pipeline run order

Scripts are run from the project root. Full script index: `scripts/README.md`.

| stage | script(s) | output |
|---|---|---|
| 1. Collect | `scripts/scrapers/*.py` (academic, news/GDELT, datasets, LongeviQuest) | `data/raw/**` |
| 2. Merge (A) | `scripts/pipeline/step_a_merge_sources.py` | `master_dataset.csv`, `nhanes_merged.csv` |
| 2.1 Dedup | `scripts/pipeline/dedup_news.py` | `news_blacklist.txt`, `news_dedup_report.csv` |
| 3. NLP features (B) | `scripts/pipeline/step_b_nlp_pipeline.py` | `master_dataset_nlp.csv`, `feature_registry.csv` |
| 3.bio Biomarkers | `extract_biomarkers.py` → `extract_biomarker_cis.py` → `meta_pool_strata.py` → `normalize_strata_names.py` → `promote_normalized.py` (in `scripts/pipeline/`) | `centenarian_biomarker_reference.csv`, `biomarker_summary.csv`, `biomarker_pooled_strata*.csv` |
| 4. Tier-1 traits | `scripts/pipeline/extract_layer1_traits.py` | `layer1_trait_frequency.csv` |
| 5. Tier-1 lock (C) | `scripts/pipeline/step_c_lock_tier1.py` | `tier1_features_locked.csv` |
| 6. Baselines (D) | `scripts/pipeline/step_d_population_baselines.py` *(placeholder)* | `tier3_nhanes_baselines.parquet` |
| 7. Feature mapping (E) | `scripts/pipeline/step_e_feature_mapping.py` *(placeholder)* | `feature_mapping.csv` |
| 8. Model & scoring (F) | `scripts/pipeline/step_f_scoring.py` *(placeholder)* | `models/tier{1,2,3}_model.yaml`, `score.py` |
| 9. Longevity baselines (G) | `scripts/pipeline/step_g_longevity_baselines.py` | `longevity_baselines.csv`, bundled `models/longevity_baselines.yaml` |

All scrapers are idempotent (skip-if-exists / ID dedup) and save incrementally.

---

## Data sources

| source | records | role |
|---|---:|---|
| Academic papers (PubMed/EuropePMC/Semantic Scholar) | 10,105 | primary corpus (abstracts) |
| News / obituary / oral-history / GDELT | 2,788 | lifestyle-trait corpus |
| LongeviQuest atlas + profiles | 3,924 + ~3,800 | validated 110+ registry & biographical profiles |
| Wikipedia / TidyTuesday supercentenarians | 219 / 124 | registry cross-reference |
| NHANES 2017–2018 (+ methylation) | 9,254 (+4,449) | population baselines |
| GWAS Catalog (longevity) | 1,863 | genomic cross-validation |
| WHO GHO / UN WPP / Human Mortality Database | 25,872 / 44,857 / 1,282,383 | country exposomic context |

Full source registry: `data/processed/source_registry.csv`.

---

## Repository layout

```
data/
  sources.md         human-readable source list
  raw/               scraped corpus + reference datasets (gitignored; large)
    datasets/FETCH.md  how to re-acquire large/external files
  processed/         derived analysis files (see docs/data_dictionary.md)
scripts/
  README.md          script index + run order
  scrapers/          data acquisition
  pipeline/          processing & modeling (step_a … step_f)
  analysis/          diagnostics & one-offs
docs/                project documentation (below)
```

## Documentation

- **MODEL_CARD.md** — complete model card: intended/non-intended use, endpoint, evidence grades, bias, failure modes, regulatory disclaimer, versioning, validation status.
- **VALIDATION_PLAN.md** — cohorts, metrics, acceptance gates (nothing validated yet).
- **AUDIT_FIXES.md** — what the latest audit changed, what's deferred, and the model-status statement.
- **docs/SOURCE_REGISTRY.md** — enriched source schema, current sources, and prioritized freely-available candidates toward validation.
- **docs/DATA_STRATEGY.md** — tiered source-quality ranking, AI/LLM-use screening (person-level data vs permitted aggregate/package use), plan for filling missing constructs, nonagenarian/public-figure data, early-life factors, and the behaviour/genetics/experience variance decomposition.
- **docs/EVIDENCE_LONGEVITY_FACTORS.md** — curated, cited aggregate evidence for the model's domains (social, purpose, nonagenarian cohorts), compliant literature backbone.
- **METHODS.md** — methodology, decisions, known limitations, changelog.
- **docs/data_dictionary.md** — schema and join keys for every processed file.
- **docs/ARCHITECTURE.md** — data flow, lineage, join keys, schema quirks.
- **docs/ROADMAP.md** — data/evidence expansion and the predictive-trajectory extension.

## License

[MIT](LICENSE) © 2026 Rejuve.AI
