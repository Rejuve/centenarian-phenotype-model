# Scripts

All scripts are run **from the project root** (not from inside `scripts/`), because data paths are root-relative:

```bash
python scripts/pipeline/step_a_merge_sources.py
```

Set `PYTHONIOENCODING=utf-8` for scripts that emit non-ASCII text.

## Layout

### `scrapers/` — data acquisition
| script | purpose |
|---|---|
| `scrape_academic_papers.py` | PubMed / Europe PMC / Semantic Scholar abstracts (incl. `bio_*` biomarker queries) |
| `scrape_news_gdelt.py` | GDELT news corpus |
| `scraper_news.py`, `scraper_search.py`, `scraper_google_news.py` | additional news scrapers (use `ddgs`) |
| `scraper_targeted_profiles.py` | obituary / oral-history / regional centenarian profiles |
| `scraper_datasets.py`, `process_new_datasets.py` | structured reference datasets (Wikipedia, TidyTuesday, NHANES, GWAS, WHO, UN WPP, HMD) |
| `scrape_longeviquest.py` | LongeviQuest atlas (validated 110+ registry) |
| `scrape_longeviquest_profiles.py` | LongeviQuest profile blurbs (`database_profile` source) |

### `pipeline/` — processing & modeling (run in order)
| script | stage | output |
|---|---|---|
| `step_a_merge_sources.py` | A | `master_dataset.csv`, `nhanes_merged.csv` |
| `dedup_news.py` | A.1 | `news_blacklist.txt`, `news_dedup_report.csv` |
| `step_b_nlp_pipeline.py` | B | `master_dataset_nlp.csv`, `feature_registry.csv` |
| `extract_biomarkers.py` → `extract_biomarker_cis.py` → `meta_pool_strata.py` → `normalize_strata_names.py` → `promote_normalized.py` | B.bio | `centenarian_biomarker_reference.csv`, `biomarker_summary.csv`, `biomarker_pooled_strata*.csv` |
| `extract_layer1_traits.py` | C.1 | `layer1_trait_frequency.csv` |
| `step_c_lock_tier1.py` | C | `tier1_features_locked.csv` |
| `step_d_population_baselines.py` | D | *(placeholder)* `tier3_nhanes_baselines.parquet` |
| `step_e_feature_mapping.py` | E | *(placeholder)* `feature_mapping.csv` |
| `step_f_scoring.py` | F | *(placeholder)* model YAMLs + `score.py` |

### `analysis/` — diagnostics & one-offs (not part of the production pipeline)
`analyze_profile_delta.py` (news vs LongeviQuest-profile trait delta), `_verified_in_news.py`, `_report_after_scrape.py`, `_show_cuts.py`, `_audit_registry_and_dedup.py`, `_scrape_biomarker_queries.py`.

> Scripts in `scrapers/` and `analysis/` that import a `pipeline/` module add `scripts/pipeline` to `sys.path` at the top so the import resolves regardless of where the module physically lives.
