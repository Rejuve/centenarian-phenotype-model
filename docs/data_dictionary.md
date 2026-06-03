# DATA DICTIONARY — `data/processed/`

*Generated 2026-06-01 as part of the pre-Step-D project audit. One table per processed file. Types are pandas-inferred from the current files. "Source" = where the column's value originates.*

> **Naming convention:** all files use `snake_case` column names. **Biomarker-name columns were standardized 2026-06-01** to a single schema across all four biomarker files: `biomarker_name_raw` (as-extracted original) and `biomarker_name` (snake_case canonical join key). The previously divergent names (`biomarker_name_norm`, `biomarker_normalized`, `biomarker_name_normalized`) are retired.
>
> **Foreign keys (relationships):**
> - `record_id` (e.g. `AP_00012`, `NA_00686`) links `centenarian_biomarker_reference.csv`, `news_dedup_report.csv`, and `master_dataset*.csv` back to source corpus rows. `AP_` = academic paper, `NA_` = news article.
> - `pmid` links biomarker rows → `academic_papers.csv`.
> - `seqn` links `nhanes_merged.csv` → `nhanes_methylation.csv` and all raw `nhanes_*` files.
> - **`biomarker_name` (canonical) is the universal join key across all four biomarker files** — verified: strata (63) ⊆ summary (191) ⊆ reference (195); the reference's 4 extra are DROP_RAW mentions excluded from the aggregates.
> - `nhanes_variable` / `nhanes_module` join `feature_registry.csv` and `tier1_features_locked.csv` → NHANES columns.

---

## supercentenarians.csv  (3,956 rows × 15 cols)
Verified 110+ registry: Wikipedia + TidyTuesday + **LongeviQuest full atlas** (merged 2026-06-01).

| column | data_type | description | source | example |
|---|---|---|---|---|
| rank | float | LongeviQuest all-time age rank (atlas rows only) | LongeviQuest | 1.0 |
| name | str | full name | all sources | Jeanne Calment |
| birth_date | str (ISO) | YYYY-MM-DD | source | 1875-02-21 |
| death_date | str (ISO) | YYYY-MM-DD, blank if living | source | 1997-08-04 |
| age_years | float | age at death/now in years (may be fractional) | source | 122.449 |
| age_raw | str | original "X years, Y days" string | wiki/atlas | 122 years, 164 days |
| place | str | place of residence/death | wiki | France |
| country | str | country | all | France |
| gender | str | M / F (LongeviQuest authoritative post-merge) | LongeviQuest>wiki>tt | F |
| nationality | str | nationality (sparse) | wiki | — |
| notability | str | notability note (sparse) | wiki | — |
| still_alive | str | "deceased"/"alive" (wiki) OR bool (atlas) — **mixed type, flag** | source | deceased |
| wiki_page | str | wiki list section the record came from | wiki | oldest_verified |
| age_as_of_20260530 | float | recomputed age for living subjects | derived | 114.44 |
| dataset_source | str | provenance, `+`-joined when merged | derived | wikipedia+longeviquest |

## layer1_trait_frequency.csv  (35 rows × 14 cols)
Tier-1 quiz trait frequencies across named centenarians (output of `extract_layer1_traits.py`).

| column | data_type | description | source | example |
|---|---|---|---|---|
| trait | str | trait label (`[tagged]` = from boolean cols) | pipeline | [tagged] socially connected |
| individual_count | int | distinct verified individuals exhibiting trait | pipeline | 88 |
| core_count | int | super + centenarian only (leads ranking) | pipeline | 88 |
| longevity_tier | str | tier driving the count | pipeline | supercentenarian |
| tier_concentration | str | single_tier / concentrated / spread | pipeline | concentrated |
| n_supercentenarian | int | distinct 110+ individuals | pipeline | 57 |
| n_centenarian | int | distinct 100-109 individuals | pipeline | 31 |
| n_nonagenarian | int | distinct 90-99 (always 0 — corpus floor) | pipeline | 0 |
| tier_breakdown | str | `super:X\|cent:Y\|nona:Z` | pipeline | super:57\|cent:31\|nona:0 |
| centenarian_examples | str | sample names | pipeline | … |
| trait_category | str | physical_activity/diet/social/purpose_psychology/sleep/substance_use | pipeline | social |
| article_mention_count | int | total article mentions (pre-dedup of individuals) | pipeline | 256 |
| sample_quote | str | 40-word window quote | pipeline | … |
| extraction_method | str | boolean / keyword | pipeline | boolean |

## tier1_features_locked.csv  (53 rows × 12 cols)
Locked Tier-1 candidate features with corroboration tiering (output of `step_c_lock_tier1.py`). Expanded from 24→53 after the LongeviQuest profile merge surfaced more keyword traits.

| column | data_type | description | source | example |
|---|---|---|---|---|
| trait | str | trait name | layer1 | walking daily |
| trait_category | str | lifestyle family | layer1 | physical_activity |
| individual_count | int | distinct centenarians | layer1 | 7 |
| n_supercentenarian | int | of which 110+ | layer1 | 1 |
| n_centenarian | int | of which 100-109 | layer1 | 6 |
| article_mention_count | int | news mentions | layer1 | 13 |
| academic_paper_count_raw | int | papers tagged (raw) | academic | 67 |
| academic_paper_count | int | papers tagged (deduped) | academic | 67 |
| nhanes_module | str | NHANES file for baseline | mapping | nhanes_physical_activity |
| baseline_source | str | available population baseline dataset: nhanes / who / corpus_control / none | decision | nhanes |
| corroboration_tier | str | silver / bronze (gold deferred to Step D) | decision | silver |
| gold_eligible | bool | silver + independent population baseline available → Step D tests for a real centenarian association to confer gold | decision | True |

**Tiering:** bronze = news-corpus individual evidence; silver = + academic corroboration of longevity association; **gold = deferred to Step D** — conferred only when Step D quantifies a centenarian-vs-population association (mere presence in a reference dataset is not gold). LongeviQuest is never a baseline (it sources the case data). Current breakdown: gold 0, silver 49, bronze 4; 14 gold_eligible.

## feature_registry.csv  (200 rows × 17 cols)
Ranked NLP-discovered features (output of `nlp_pipeline.py`). **⚠ stale — see audit §2.**

| column | data_type | description | source | example |
|---|---|---|---|---|
| feature_name | str | discovered phrase | NLP | social medium |
| feature_type | str | noun_phrase/verb_phrase/attribution… | NLP | noun_phrase |
| tier | float | assigned tier (if NHANES-mapped) | NLP | 1.0 |
| corpus_lift_score | float | centenarian vs background lift | NLP | 1.709 |
| document_count | int | docs containing phrase | NLP | 78 |
| centenarian_freq | int | docs in centenarian subset | NLP | 46 |
| individual_count | int | distinct individuals | NLP | 43 |
| individuals_sample | str | sample names (`\|`-joined) | NLP | Andrew\|… |
| weighted_score | float | doc-weighted score | NLP | 131.3 |
| population_score | float | population-normalized | NLP | 6.4681 |
| n_countries | int | distinct countries | NLP | 3 |
| cross_cultural | bool | ≥N countries | NLP | True |
| nhanes_variable | str | mapped NHANES var(s) | mapping | marital_status\|… |
| nhanes_concept | str | concept group | mapping | social_connection |
| nhanes_category | str | lifestyle/biomarker/… | mapping | lifestyle |
| direction | str | direction-of-association | NLP | high (48%) |
| example_phrases | str | `[record_id]` evidence snippets | NLP | [AP_02509] … |

## centenarian_biomarker_reference.csv  (896 rows × 18 cols)
Per-mention biomarker extractions (output of `extract_biomarkers.py`).

| column | data_type | description | source | example |
|---|---|---|---|---|
| biomarker_name_raw | str | as-extracted name | academic | had diabetes |
| biomarker_name | str | snake_case canonical join key | derived (canonical_name) | diabetes |
| value | float | extracted value | academic abstract | 59.3 |
| value_low / value_high | float | range bounds if given | abstract | 0.24 |
| unit | str | %, kb, mg/L… | abstract | % |
| value_type | str | point_estimate/odds_ratio/hazard_ratio/ci/mean/median | abstract | point_estimate |
| pmid | int | PubMed ID (FK→academic_papers) | academic | 11305016 |
| record_id | str | corpus row id (FK) | corpus | AP_00012 |
| pub_year | float | publication year | academic | 2001 |
| study_type | str | cohort/case_control/… | academic | other |
| sample_size | float | n | abstract | 4427 |
| population_country | str | study country | academic | China |
| subject_class | str | general/nonagenarian/centenarian/supercentenarian | derived | centenarian |
| source_journal | str | journal | academic | … |
| ci_lower / ci_upper | float | confidence interval | abstract | 1.07 / 3.62 |
| ci_sep_format | str | how CI was parsed | derived | labelled |

## biomarker_summary.csv  (421 rows × 29 cols)
One row per normalized biomarker, with pooled primary stratum + base rate.

| column | data_type | description | source | example |
|---|---|---|---|---|
| biomarker_name | str | canonical biomarker name (**universal join key**) | derived | mortality |
| n_mentions | int | total mentions | ref | 68 |
| n_independent_sources | int | distinct papers | ref | 52 |
| n_countries | int | distinct countries | ref | 10 |
| countries_sample | str | sample (`\|`) | ref | Australia\|China\|… |
| subject_classes_seen | str | classes present | ref | centenarian\|general\|… |
| value_types | str | measure types present | ref | ci\|hazard_ratio\|… |
| units_seen | str | units present | ref | %\|kb |
| median_sample_size | float | median n | ref | 770 |
| in_nhanes / in_gwas | bool | cross-validation flags | mapping | True |
| evidence_grade_legacy | str | pre-pooling grade | legacy | A |
| n_strata | int | strata pooled | pooling | 5 |
| n_commensurable_strata | int | commensurable strata | pooling | 0 |
| primary_effect_measure | str | OR/HR/RR | pooling | HR |
| primary_contrast_type | str | prevalence_longlived/prognostic_mortality/… | pooling | prognostic_mortality |
| primary_subject_class | str | class of primary stratum | pooling | centenarian |
| primary_pooled_OR | float | pooled effect | pooling | 1.75 |
| primary_ci_lower/upper | float | pooled CI | pooling | 1.04 / 2.95 |
| primary_I_squared | float | heterogeneity I² | pooling | 65.19 |
| primary_tau_squared | float | between-study var | pooling | 0.40 |
| primary_n_studies | float | studies pooled | pooling | 2 |
| primary_n_ci_studies | float | CI-bearing studies | pooling | 1 |
| evidence_grade | str | current grade | pooling | C |
| model_use | str | similarity_primary/directional_only | decision | directional_only |
| base_rate | float | population base rate | derived | 0.1088 |
| base_rate_CI_lower/upper | float | Wilson CI on base rate | derived | 0.084 / 0.140 |

## biomarker_pooled_strata.csv  (17 cols) & biomarker_pooled_strata_normalized.csv  (22 cols)
DerSimonian-Laird random-effects pools, one row per (biomarker × contrast × class) stratum. Both files now key on `biomarker_name` (canonical). The `_normalized` file additionally carries `biomarker_name_raw` (pre-normalization strata name) plus the audit columns (`contrast_type_normalized`, `name_changed`, `review_priority`, `normalization_note`). Shared core columns: `biomarker_name`, `effect_measure` (OR/HR), `contrast_type`, `subject_class`, `pooled_log_effect`, `se`, `pooled_OR`, `ci_lower/upper`, `I_squared`, `tau_squared`, `n_studies`, `n_ci_bearing_studies`, `direction_consistent`, `commensurable_pool` (bool — never pool OR with HR), `evidence_grade`, `model_use`. Note: `biomarker_pooled_strata.csv` is an aggregate (one row per stratum) so it carries only the canonical `biomarker_name`, not `biomarker_name_raw`.

## nhanes_merged.csv  (9,254 rows × 250 cols)
15 NHANES 2017-18 files joined on `seqn`. CDC codes renamed to human-readable snake_case. **Too wide to list fully**; column groups: identifiers (`seqn`, `nhanes_survey_cycle`), demographics (`gender`, `age_years`, `race_ethnicity`, `education_*`, `marital_status`, `household_*`, income), survey weights (`interview_weight_2yr`, `exam_weight_2yr`, `variance_psu/strata`), and biomarker panels (`crp_mg_l`, CBC `*_1000_per_ul`/`*_pct`, cholesterol, glucose/`hba1c`, blood pressure, body measures, etc.). **All values are NHANES numeric codes (float), not labels** — a codebook join is still needed for categoricals. ⚠ A recurring sentinel `5.397605346934028e-79` appears in count columns (≈ encoded missing/zero) — flag in audit §4.

## master_dataset_nlp.csv  (≈9,786 rows × 264 cols)
Post-NLP feature matrix. **⚠ stale (see audit §2).** Base corpus columns (source_*, subject_*, trait_*, biomarker_*, gene_*) plus `nlp_np_*` / `nlp_vp_*` / `nlp_at_*` binary phrase features, `nlp_doc_weight`, `nlp_subject_name_ner`, `nlp_subject_age_ner`, `nlp_n_persons`. Too wide to enumerate; see `nlp_pipeline.py` for the generation logic.

## source_registry.csv  (5 rows × 7 cols)  — NEW 2026-06-01
| column | data_type | description | example |
|---|---|---|---|
| source_name | str | dataset/source name | LongeviQuest |
| source_class | str | news/database_profile/survey/encyclopedia/dataset | database_profile |
| source_country | str | coverage | international |
| attribution | str | citation/URL | longeviquest.com |
| record_count | float | rows contributed | 3924 |
| date_added | str | ISO date | 2026-06-01 |
| notes | str | provenance/caveats | validated 110+ profiles… |

## Supporting / intermediate processed files
- **news_dedup_report.csv** (220 rows × 4): `cluster_id`, `n_members`, `representative` (record_id), `members` (`\|`-joined ids). Syndication clusters.
- **news_blacklist.txt**: 1,117 record_ids skipped by NLP.
- **_verified_in_news.csv** (61 rows × 3): `canonical_name`, `news_article_count`, `slug`. Intermediate for the profile scrape — safe to delete after.
- **master_dataset.csv** (≈12,893 × 57): unified academic+news pre-NLP. Source for NLP + biomarker extraction.

## Step F — scoring models & genomic panel
- **step_e_feature_layer_assignments.csv** (105 rows × 14): every feature's layer + evidence metadata. Columns: `feature`, `layer` (1/2/3), `domain`, `evidence_score`, `corroboration_tier`, `gwas_corroborated`, `direction`, `quiz_question_eligible`, `nhanes_prevalence`, `centenarian_prevalence`, `prevalence_ratio`, `finding_context`, `genetic_evidence_note`, `confidence_completeness_pct`. **Layer counts: L1 54 · L2 5 · L3 46.** Body composition is captured at the fidelity it exists: `waist_circumference` and `body_mass_index` at L2 (self-report), and `waist_circumference` again at L3 (measured). `muscle_mass` / `fat_mass` / `hip_circumference` are **not in the corpus and are intentionally not added** — the schema ingests new features only when data exists for them.
- **genomic_panel_curated.csv** (508 rows × 15): curated longevity variant panel produced by `scripts/pipeline/step_e_genomic_panel.py` from `gwas_longevity.csv` (genome-wide-significant, p<5e-8, longevity-relevant traits) and corroborated against `cent_WGS.txt` by CHR:POS. Columns: `snp`, `gene`, `trait`, `effect_direction` (`longevity_associated` / `longevity_adverse` / `reported`), `risk_allele`, `or_beta`, `p_value`, `chr`, `pos`, `wgs_a1`, `wgs_cent_freq` (F_105), `wgs_ctrl_freq` (F_CTRL), `wgs_freq_diff`, `first_author`, `pubmedid`. 80 rows have interpretable direction (scoreable); 2 are WGS-position-corroborated (GRCh38↔WGS build mismatch limits the rest).
- **models/tier1_model.yaml** — Layer-1 behavioral quiz: 12 questions / 11 domains; each option has `trait_tags`, `alignment` (0–1), and a `basis` provenance tag; `basis_legend` + `scoring` (completeness 30, gwas weight 0).
- **models/tier2_model.yaml** — Layer-2 **standalone app survey, 32 questions**: 19 NHANES-aligned behavioral (physical activity ×2, sleep, smoking, alcohol, diet, social ×2, loneliness, family ×3, purpose ×2, cognitive ×2, outlook, faith, independence — re-asked at depth, mapped to top centenarian features) + 13 self-report clinical/health (diabetes, hypertension, BMI, waist, family history of longevity, cardiovascular event, cancer, functional mobility, self-rated health, cholesterol, disease burden, depression, bone health). L2 **re-captures every variable fresh** (no carry-over/pre-fill from the L1 teaser), at finer granularity; completeness 50, gwas weight 0.
- **models/tier3_model.yaml** — Layer-3 spec (not a quiz): `clinical_biomarkers`, `clinical_disease_flags`, `genomic_variants` (21 scored), `genomic_panel_extended` (ref to the 508-variant file), `epigenetic_methylation` (5 clocks) + `epigenetic_population_anchor`, `microbiome` (pending); completeness 80, `gwas_corroborated_weight` 0.15.
- Scored by **`scripts/pipeline/step_f_scoring.py`** `score_profile(layer_models, quiz_answers, tier3_spec, clinical_alignments)` → `score_pct`, 95% interval, `completeness_pct`, `subscores`, `evidence_basis_pct`, `gwas_corroborated_weight_share_pct`, `superseded_by_l3` (construct dedup — deepest layer wins).
