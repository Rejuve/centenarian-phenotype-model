# Architecture — Centenarian Longevity Phenotype Model

How data flows through the pipeline as it actually exists today. Stages A–C are implemented; D–F are placeholders.

## Pipeline stages

| stage | script | status | produces |
|---|---|---|---|
| A — merge sources | `pipeline/step_a_merge_sources.py` | ✅ | `master_dataset.csv`, `nhanes_merged.csv` |
| A.1 — dedup news | `pipeline/dedup_news.py` | ✅ | `news_blacklist.txt`, `news_dedup_report.csv` |
| B — NLP features | `pipeline/step_b_nlp_pipeline.py` | ✅ (stale) | `master_dataset_nlp.csv`, `feature_registry.csv` |
| B.bio — biomarkers | `extract_biomarkers → extract_biomarker_cis → meta_pool_strata → normalize_strata_names → promote_normalized` | ✅ | `centenarian_biomarker_reference.csv`, `biomarker_summary.csv`, `biomarker_pooled_strata*.csv` |
| C — Tier-1 traits & lock | `pipeline/extract_layer1_traits.py` → `pipeline/step_c_lock_tier1.py` | ✅ | `layer1_trait_frequency.csv`, `tier1_features_locked.csv` |
| D — population baselines | `pipeline/step_d_population_baselines.py` | ⛔ placeholder | `tier3_nhanes_baselines.parquet` |
| E — feature mapping | `pipeline/step_e_feature_mapping.py` | ⛔ placeholder | `feature_mapping.csv` |
| F — model & scoring | `pipeline/step_f_scoring.py` | ⛔ placeholder | `models/tier{1,2,3}_model.yaml`, `score.py` |

## Data lineage (raw → processed → model inputs)

```
academic_papers.csv ┐
news_articles.csv   ┼─[A]step_a_merge_sources─► master_dataset.csv ─[B]step_b_nlp─► master_dataset_nlp.csv
                    │                                                              └► feature_registry.csv ──► (model: Tier 2/3 features)
nhanes_*.csv (15) ──┴─[A]──────────────────────► nhanes_merged.csv ◄─seqn─ nhanes_methylation.csv ──► (model: Step D baselines)

academic_papers.csv ─[B.bio]extract_biomarkers─► centenarian_biomarker_reference.csv
   └─ meta_pool_strata → normalize_strata_names → promote_normalized ─► biomarker_pooled_strata_normalized.csv ─► biomarker_summary.csv ──► (model: Tier 3)

wikipedia + tidytuesday + longeviquest_atlas ─► supercentenarians.csv          (verified 110+ registry, gender)
news_articles.csv (+ longeviquest_profiles) + supercentenarians + longeviquest_atlas
   ─[C]extract_layer1_traits─► layer1_trait_frequency.csv ─[C]step_c_lock_tier1─► tier1_features_locked.csv ──► (model: Tier 1)

process_new_datasets ─► gwas_longevity / who_life_expectancy / un_population_prospects / hmd_life_tables ──► (model: country exposomic context, Step F)
```

**Model-input summary:** Tier 1 ← `tier1_features_locked.csv`; Tier 2 ← `feature_registry.csv`; Tier 3 ← `biomarker_summary.csv` + `tier3_nhanes_baselines.parquet` (Step D); country context ← WHO/UN/HMD joins (Step F).

## Join keys

| key | links | notes |
|---|---|---|
| `biomarker_name` | the four biomarker files | snake_case canonical, standardized 2026-06-01. Universal join key: strata (63) ⊆ summary (191) ⊆ reference (195). `biomarker_name_raw` carries the as-extracted form. |
| `record_id` | `centenarian_biomarker_reference.csv`, `news_dedup_report.csv`, `master_dataset*.csv` | `AP_*` = academic paper, `NA_*` = news article. |
| `pmid` | biomarker rows → `academic_papers.csv` | PubMed ID. |
| `seqn` | `nhanes_merged.csv` ↔ `nhanes_methylation.csv` and all raw `nhanes_*` | NHANES respondent ID. |
| `name` (+ `birth_date`, `death_date`) | `supercentenarians.csv` ↔ LongeviQuest atlas/profiles | person identity for registry merges. |
| `nhanes_variable` / `nhanes_module` | `feature_registry.csv`, `tier1_features_locked.csv` → NHANES columns | feature → population-baseline mapping. |

## Source-class taxonomy

`source_class` on each corpus row (and in `source_registry.csv`):

| class | meaning | example sources |
|---|---|---|
| `academic` | peer-reviewed paper (abstract) | PubMed, Europe PMC, Semantic Scholar |
| `news` | topical news article | GDELT, DuckDuckGo search, regional outlets |
| `database_profile` | single-subject biographical record (obituary-family, not topical news) | LongeviQuest profiles |
| `dataset` | structured reference dataset | GWAS, WHO, UN WPP, HMD, TidyTuesday |
| `survey` | population survey | NHANES |
| `encyclopedia` | crowd-maintained reference | Wikipedia |

## Known schema quirks

- **`supercentenarians.still_alive` mixed type:** `"deceased"`/`"alive"` strings (Wikipedia rows) coexist with booleans (atlas rows). Normalize before use.
- **NHANES missing-value sentinel:** `nhanes_merged.csv` count columns contain `5.397605346934028e-79` as an encoded missing/zero value. Map to NA before computing Step-D baselines, or statistics will be corrupted.
- **NHANES categorical codes:** values are raw CDC numeric codes, not labels; a codebook decode is required before scoring.
- **Abstract-only academic corpus:** `academic_papers.csv` has an `abstract` column (100% populated) but no full text. Control-group prevalence is extractable from ~52% of control-group abstracts; the remainder relies on NHANES/WHO fallback.
- **Nonagenarian floor:** the news corpus has no cleanly named 90–99 subjects (subject age floored at 100), so that class is unpopulated from news.
- **Stale derived files:** `master_dataset_nlp.csv` and `feature_registry.csv` predate the +1,916-paper biomarker scrape; regenerate before relying on them for Step F Tier 2/3.
