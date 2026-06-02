# Rejuve Centenarian Longevity Phenotype Model

An open-source machine-learning model that scores how similar a person's lifestyle, biomarker, and genetic profile is to people who live to 100 or more.

> **This is a similarity score, not a lifespan predictor.** The output is "your profile is *X%* similar to verified centenarians" — never a predicted age at death.

The model ships in three tiers, each an evolution of the one before:

- **Tier 1** — 12-question behavioral teaser quiz, instant shareable similarity score (free web/ad widget).
- **Tier 2** — standalone 31-item app survey: 18 NHANES-aligned behavioral + 13 self-report clinical/health items (free app).
- **Tier 3** — **Tier 2 in full** plus blood biomarkers, 21 genomic variants, DNA-methylation clocks + telomere length, and microbiome pending (subscription).

Completeness accumulates across the tiers (~30% → ~50% → ~80%): each tier carries all of the previous tier's questions into its score and adds deeper evidence on top.

Built data-first from an academic + news corpus and validated reference datasets (NHANES, WHO, UN WPP, HMD, GWAS, LongeviQuest). Designed to interoperate with OpenCog Hyperon / PLN: Naive Bayes outputs map to PLN truth values.

---

## Quickstart

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

Scripts run from the repository root: `python <script>.py`. Set `PYTHONIOENCODING=utf-8` for scripts that emit non-ASCII text (Windows/PowerShell: also `chcp.com 65001 > $null`).

The trained model (~50 KB) ships with the application; **end users never run the scrapers or pipeline below.** This repository is for building and reproducing the model.

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

- **METHODS.md** — methodology, decisions, known limitations, changelog.
- **docs/data_dictionary.md** — schema and join keys for every processed file.
- **docs/ARCHITECTURE.md** — data flow, lineage, join keys, schema quirks.
- **docs/ROADMAP.md** — data/evidence expansion and the predictive-trajectory extension.
- **docs/audit_report.md** — living status: inventory, integrity, missing steps, data-quality flags, readiness.
- **docs/model_card_stub.md** — model card seed (framing, limitations).
- **docs/documentation_gaps.md** — outstanding documentation/packaging tasks.

## License

[MIT](LICENSE) © 2026 Rejuve.AI
