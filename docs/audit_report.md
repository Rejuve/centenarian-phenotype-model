# PROJECT AUDIT REPORT — Rejuve Centenarian Longevity Phenotype Model

*Living status document. Generated 2026-06-01, before Step D (NHANES baselines) and scoring. Companion docs: [`data_dictionary.md`](data_dictionary.md) (schemas), [`documentation_gaps.md`](documentation_gaps.md) (missing top-level docs).*

> **Snapshot:** Phases 1–2.7 complete. LongeviQuest integration **in progress** (full-DB gender merge done; profile-blurb scrape running, ~1,300 / 3,861 at time of writing). Phase 3 build steps (A–H) largely **not started**. Two stale processed files identified (§2). Repo is **not yet version-controlled** and lacks README/requirements/LICENSE (§5c, `documentation_gaps.md`). Package readiness: **2 / 5** (§6).

---

## 0. ACADEMIC_PAPERS.CSV — control-baseline extractability (answer to the pre-audit question)

**Q1 — full_text column?** ❌ No. The file has an **`abstract`** column only, populated for **10,105 / 10,105 rows (100%)**. There is no full-text anywhere in the academic corpus.

**Q2 — silver-tier control-group prevalence: full_text vs abstract-only.** Since there is no full_text, **every silver-tier paper is abstract-only (0% full text).** Control-group designs (cohort + case_control + cross_sectional + randomized_trial) = **3,333 / 10,105 (33%)**. Of those, only **52% report a percentage figure in the abstract**. By silver category:

| silver category | tagged papers | control-group designs | …with a % in abstract | extractable |
|---|---:|---:|---:|---:|
| social | 2,925 | 1,294 | 664 | 51% |
| purpose_psychology | 4,120 | 1,584 | 806 | 51% |
| diet | 3,178 | 997 | 554 | 56% |

**Verdict:** `corpus_control` baselines are **only partially extractable** (~half of control-group papers surface a prevalence number in the abstract; the rest keep it in results tables we don't have). For the 16 silver traits routed to `corpus_control`, expect **roughly half to need NHANES/WHO fallback** — and the social/purpose traits (no clean NHANES analogue) are the most exposed. **Recommendation:** treat `corpus_control` as best-effort, set a per-trait `n_control_papers_with_pct` threshold, and pre-wire NHANES proxies (or WHO) as the documented fallback before scoring.

---

## 1. FILE INVENTORY

124 files total. Production scripts and analytically-active data listed individually; bulk reference archives grouped. **Status legend:** 🟢 active · 🟡 intermediate (safe to delete) · 🔴 superseded · ⚪ unknown.

### Pipeline scripts (repo root, 31 `.py`)

| file | KB | modified | purpose | status |
|---|--:|---|---|---|
| merge_all.py | 36 | 05-31 | academic+news → master_dataset.csv; cleans wiki; joins 15 NHANES → nhanes_merged.csv | 🟢 |
| dedup_news.py | 7 | 05-31 | 7-word-shingle syndication clustering → blacklist + dedup report | 🟢 |
| nlp_pipeline.py | 75 | 05-31 | Phase 2 NLP: boilerplate filter, NER, 5 phrase types, registry | 🟢 (output stale §2) |
| extract_biomarkers.py | 33 | 06-01 | data-first biomarker value/ratio extraction + grading | 🟢 |
| extract_biomarker_cis.py | 5 | 06-01 | CI parsing pass for biomarker mentions | 🟢 |
| meta_pool_biomarkers.py | 8 | 06-01 | DerSimonian-Laird pooling driver | 🟢 |
| meta_pool_strata.py | 13 | 06-01 | stratified pooling (biomarker×contrast×class) | 🟢 |
| normalize_strata_names.py | 11 | 06-01 | biomarker-name normalization | 🟢 |
| promote_normalized.py | 11 | 06-01 | promote normalized strata → summary | 🟢 |
| extract_layer1_traits.py | 28 | 06-01 | Tier-1 quiz trait extraction (master-list match + keyword) | 🟢 |
| step_c_lock_tier1.py | 9 | 06-01 | lock 24 Tier-1 features w/ baseline routing | 🟢 (output stale §2) |
| process_new_datasets.py | 23 | 05-31 | GWAS/WHO/UN/HMD/methylation download+process | 🟢 |
| scraper_academic.py | 31 | 06-01 | PubMed/EuropePMC/Semantic Scholar | 🟢 |
| scraper_datasets.py | 30 | 05-31 | structured dataset scraper | 🟢 |
| scraper_news/​search/​google_news/​gdelt.py | 23–52 | 05-29–31 | news scrapers (use `ddgs`) | 🟢 |
| scraper_targeted_profiles.py | 16 | 05-31 | obituary/oral-history/regional profiles | 🟢 |
| scrape_longeviquest.py | 3 | 06-01 | LongeviQuest atlas (registry) scraper | 🟢 |
| scrape_longeviquest_profiles.py | 8 | 06-01 | **NEW** profile-blurb scraper (running) | 🟢 |
| analyze_profile_delta.py | 4 | 06-01 | **NEW** news-vs-profile trait delta (queued) | 🟢 |
| _verified_in_news.py | 2 | 06-01 | intermediate: dump 61 verified-in-news names | 🟡 |
| _audit_registry_and_dedup.py | 9 | 05-31 | older registry diagnostic (pre-rebuild) | 🔴 |
| _report_after_scrape.py / _scrape_biomarker_queries.py / _show_cuts.py | 1–4 | 06-01 | one-off diagnostics/wrappers | 🟡 |
| _inv.py / _doc.py / _integrity.py / _schema_doc.py | 1–4 | 06-01 | this audit's scratch scripts | 🟡 delete |

### Data — active

| file | size | modified | status |
|---|--:|---|---|
| data/raw/academic_papers.csv (10,105) | 20.4 MB | 06-01 02:13 | 🟢 |
| data/raw/news_articles.csv (2,788 → +profiles pending) | 29.1 MB | 06-01 00:07 | 🟢 (merge pending) |
| data/processed/master_dataset.csv (12,893) | 45.9 MB | 06-01 02:14 | 🟢 |
| data/processed/master_dataset_nlp.csv (9,786) | 39.1 MB | 06-01 00:34 | 🟡 **STALE §2** |
| data/processed/feature_registry.csv (200) | 91 KB | 06-01 00:34 | 🟡 **STALE §2** |
| data/processed/supercentenarians.csv (3,956) | 335 KB | 06-01 17:27 | 🟢 (LongeviQuest-merged) |
| data/processed/layer1_trait_frequency.csv (35) | 47 KB | 06-01 18:05 | 🟢 |
| data/processed/tier1_features_locked.csv (24) | 2 KB | 06-01 16:21 | 🟡 **STALE §2** |
| data/processed/centenarian_biomarker_reference.csv (896) | 127 KB | 06-01 11:28 | 🟢 |
| data/processed/biomarker_summary.csv (421) | 39 KB | 06-01 14:23 | 🟢 |
| data/processed/biomarker_pooled_strata_normalized.csv | 27 KB | 06-01 14:23 | 🟢 |
| data/processed/nhanes_merged.csv (9,254 × 250) | 7.0 MB | 06-01 02:14 | 🟢 |
| data/raw/datasets/longeviquest_atlas.csv (3,924) | 336 KB | 06-01 17:20 | 🟢 |
| data/raw/datasets/longeviquest_profiles.csv (growing) | 1.9 MB | 06-01 live | 🟢 in progress |
| data/processed/source_registry.csv (5) | 1 KB | 06-01 18:34 | 🟢 NEW |

### Data — intermediate / superseded (cleanup candidates)

| file | status | note |
|---|---|---|
| data/raw/academic_papers_preview.csv (5.6 MB) | 🔴 | preview sample, superseded by full file |
| data/raw/news_articles_preview.csv (43 KB) | 🔴 | preview sample, superseded |
| data/processed/biomarker_pooled_strata.csv (15 KB) | 🟡 | superseded by `_normalized` (promoted version) |
| data/processed/_verified_in_news.csv | 🟡 | scrape helper, delete after profile run |
| data/raw/datasets/longeviquest_atlas_raw.md (8 KB) | 🟡 | raw top-100 capture; keep as provenance |
| data/raw/datasets/figshare_italian_genomics_metadata.csv (0 KB) | 🔴 | **empty file** — failed download, re-acquire or remove |
| data/raw/datasets/hmd_DOWNLOAD_INSTRUCTIONS.txt (0 KB) | 🔴 | empty |

### Data — bulk reference archives (grouped)

| group | count | size | status |
|---|--:|--:|---|
| data/raw/datasets/nhanes_*.csv | 15 | ~13 MB | 🟢 source for nhanes_merged |
| data/raw/datasets/hmd/*.zip | 41 | ~280 MB | 🟢 kept for re-extraction (gitignore) |
| hmd_life_tables.csv / un_population_prospects.csv / who_life_expectancy.csv | 3 | 134 MB | 🟢 Phase-3 reference |
| cent_WGS.txt (151 MB) / dnmepi.sas7bdat / WPP…xlsx (25 MB) | 3 | ~178 MB | 🟢 genomic/methylation sources (gitignore) |
| gapminder/owid/gwas_longevity | 3 | ~1.5 MB | 🟢 |

---

## 2. PIPELINE INTEGRITY

### Data lineage (raw → processed)

```
academic_papers.csv ┐
news_articles.csv   ┼─merge_all.py──► master_dataset.csv ─nlp_pipeline.py─► master_dataset_nlp.csv
                    │                                                      └► feature_registry.csv
nhanes_*.csv (15) ──┴─merge_all.py──► nhanes_merged.csv ◄─seqn─ nhanes_methylation.csv

academic_papers.csv ─extract_biomarkers.py─► centenarian_biomarker_reference.csv
        └─meta_pool_strata → normalize_strata_names → promote_normalized─► biomarker_pooled_strata_normalized.csv ─► biomarker_summary.csv

wikipedia + tidytuesday + longeviquest_atlas ─► supercentenarians.csv  (master 110+ list)
news_articles.csv + supercentenarians + longeviquest_atlas ─extract_layer1_traits.py─► layer1_trait_frequency.csv ─step_c_lock_tier1.py─► tier1_features_locked.csv

process_new_datasets.py ─► gwas_longevity / who_life_expectancy / un_population_prospects / hmd_life_tables / nhanes_methylation
```

### ⚠ Staleness (processed file older than a source it depends on)

1. **`master_dataset_nlp.csv` + `feature_registry.csv` (06-01 00:34) predate `academic_papers.csv` (02:13) and `master_dataset.csv` (02:14).** The NLP feature matrix and the 200-row feature registry were built **before the +1,916-paper biomarker scrape** landed. They reflect the ~8,189-paper corpus, not the final 10,105. *Impact:* moderate for Tier-1 lifestyle features (the added papers were biomarker-focused), but the registry is not built on the final corpus and should not be cited as such. **Action: regenerate `nlp_pipeline.py` on the current `master_dataset.csv`, or explicitly document that the registry is the pre-biomarker-scrape snapshot.**
2. **`tier1_features_locked.csv` (16:21) predates `layer1_trait_frequency.csv` (18:05).** The locked 24-feature table was built from the 29-row trait frequencies; the LongeviQuest master-list expansion then regenerated trait frequencies to 35 rows with higher `individual_count`s. *Impact:* the locked counts/`n_supercentenarian` are slightly understated. **Action: re-run `step_c_lock_tier1.py` after the LongeviQuest integration settles.**

### 🔻 Pending regeneration cascade (LongeviQuest profile integration, in progress)

Merging the ~3,861 profile rows into `news_articles.csv` will invalidate everything downstream of it. **After the scrape + merge, regenerate in this order:**
`news_articles.csv` → `merge_all.py` (master_dataset) → `nlp_pipeline.py` (nlp + registry) → `extract_layer1_traits.py` (trait freq) → `step_c_lock_tier1.py` (tier1 lock). This single cascade also clears staleness items 1 & 2 above. **Do this before Step D/scoring.**

### Broken references
✅ **None.** All file paths referenced in the 31 scripts resolve to existing files. No renamed/missing-file references detected.

---

## 3. MISSING STEPS (planned Steps A–H)

*The Step A–H roadmap and open decisions previously lived in PROJECT_BRIEF.md (now formalized as METHODS.md, which intentionally omits the roadmap). The roadmap is preserved here as the project's living status record.*

| step | deliverable | status | blocker |
|---|---|---|---|
| Phase 1–2.7 | corpus, dedup, NLP, biomarkers, ref datasets | ✅ Complete | — |
| Biomarker pooling | DL random-effects strata + summary | ✅ Complete (post-brief; not yet in changelog) | — |
| LongeviQuest gender merge | full atlas → supercentenarians.csv, 89.3% F | ✅ Complete | — |
| LongeviQuest profile mining | 3,861 blurbs → news_articles.csv + trait delta | 🔄 **In progress** (scrape ~1,300/3,861; merge + `analyze_profile_delta.py` queued) | scrape runtime (~2h) |
| **Step A** | `biomarker_curated_supplement.csv` (Horvath/GrimAge/PhenoAge/IGF-1/VO2max/gait) `evidence_grade=A_curated` | ❌ Not started | open decision #1 (curation execution) |
| **Step B** | directional biomarker extraction pass (`value_type='directional'`) | ⚪ Partial? `extract_biomarker_cis.py` exists but the `directional_only` second pass per brief is unconfirmed | verify vs brief intent |
| **Step C** | `country_baseline.csv` (WHO×UN×HMD×BlueZone) | ❌ Not started | needs WHO/UN/HMD join |
| **Step D** | `tier3_nhanes_baselines.parquet` (μ,σ,p5..p95 by age×gender) | ❌ Not started | **the step the user is heading to** |
| **Step E** | Tier-1 feature lock | ✅ Done as `tier1_features_locked.csv` (🟡 stale — regen) | naming drift: brief says `tier1_features.csv` |
| **Step F** | model YAMLs (`models/tier{1,2,3}_model.yaml`) | ❌ Not started | needs Steps A–E settled; no `models/` dir |
| **Step G** | `score.py` scoring engine | ❌ Not started | Step F |
| **Step H** | FastAPI + Flutter/React clients | ❌ Not started | Phase 4 |

**Open decisions still unresolved (brief §OPEN DECISIONS):** (1) Grade-C biomarker gap execution (Options A+B), (2) Tier-1 8-feature finalization vs the 24 locked, (3) attribution confirmed dead — accepted.

---

## 3.5 DEPENDENCY FINDING — are master_dataset*/feature_registry needed for Steps D/E/F?

*Requested check. Report only — nothing deleted or moved.*

**Who reads each file** (production scripts; scratch/`_*` diagnostics excluded):

| file | written by | read by (production) | read by any D/E/F input? |
|---|---|---|---|
| `master_dataset.csv` | merge_all.py | extract_biomarkers.py, extract_biomarker_cis.py, nlp_pipeline.py | **No** (D/E/F don't read it directly) |
| `master_dataset_nlp.csv` | nlp_pipeline.py | **nobody** (terminal output) | **No** |
| `feature_registry.csv` | nlp_pipeline.py | nobody in the D/E/F path | **No** for D/E; **Yes** for F (Tier 2/3) |

**Step-by-step:**
- **Step D** (`tier3_nhanes_baselines.parquet`) reads `nhanes_merged.csv` + `biomarker_summary.csv`. Both already exist as newer/cleaner derived files. **Does not need any of the three. Not blocked.**
- **Step E** (Tier-1 lock) is already implemented: `extract_layer1_traits.py` reads news + supercentenarians + wiki + tidytuesday + longeviquest_atlas; `step_c_lock_tier1.py` reads `layer1_trait_frequency.csv` + `academic_papers.csv`. **Reads none of the three. Not blocked.**
- **Step F** (model YAMLs): Tier-1 sources `tier1_features_locked.csv` + `biomarker_summary.csv` — independent. **Tier-2/Tier-3** feature selection draws the ~25 lifestyle features from `feature_registry.csv` (no newer replacement exists — it is the only feature-discovery output). **feature_registry is needed for Step F Tier 2/3 only.**

**Verdict:**
- **`master_dataset_nlp.csv` → SAFE TO ARCHIVE.** No production script reads it; it is a terminal feature matrix. Regenerable from `master_dataset.csv` via `nlp_pipeline.py` if ever needed. Blocks nothing in D/E/F.
- **`master_dataset.csv` → KEEP (not needed for D/E/F directly).** It is the input to the biomarker pipeline (`extract_biomarkers`/`_cis`) and NLP pipeline, so it is required for **Steps A/B** (biomarker curation/directional pass) and any registry regeneration — not for D/E/F. Do not archive while A/B are pending.
- **`feature_registry.csv` → KEEP.** Not needed for D or E; **required for Step F Tier 2/3**. It is currently **stale** (built pre-biomarker-scrape, §2.1) and should be regenerated before Step F via `nlp_pipeline.py` on a current `master_dataset.csv`.

**Nothing blocks Steps D or E.** The only D/E/F dependency among the three is `feature_registry.csv` for Step F Tier 2/3, and the clean regeneration path is the §2 cascade (`merge_all.py` → `nlp_pipeline.py`).

## 4. DATA QUALITY FLAGS (consolidated)

| # | issue | status | detail |
|---|---|---|---|
| 1 | **tidytuesday male skew** | ✅ resolved | 80.6% male (record-holder subset). LongeviQuest full-DB merge swamps it → overall 89.3% F of known, matching reality. tidytuesday flagged non-representative in `source_registry.csv`. |
| 2 | **Wikipedia missing gender** | ✅ resolved | was 53.9% missing → 8.7% after LongeviQuest fill (0 conflicts). |
| 3 | **Academic corpus abstract-only** | ⚠ known limitation | no full_text; ~half of control-group papers lack an abstract-level prevalence (§0). corpus_control baselines partly fall back to NHANES/WHO. |
| 4 | **Nonagenarian (90-99) floor** | ⚠ known limitation | news `subject_age` hard-floored at 100; 0 named nonagenarians. 3-tier schema present but tier empty. Needs targeted scrape or extractor fix to populate. |
| 5 | **Alcohol syndication artifact** | ✅ resolved | distinct-individual counting (not article counting) controls it; dedup blacklist (Calment-77, Bev-76) applied at NLP load. |
| 6 | **Attribution signal dead** | ⚠ known limitation (accepted) | 0 attribution phrases clear freq≥3 after dedup; model proceeds on noun/verb + NHANES. |
| 7 | **Grade-C biomarkers under-graded** | 🔧 needs fix | Horvath/GrimAge/mTOR/VO2max/gait etc. have real signal but values live in main-text tables, not abstracts → stuck at C. Steps A/B planned. |
| 8 | **NLP matrix / registry stale** | 🔧 needs fix | built pre-biomarker-scrape (§2.1). Regenerate. |
| 9 | **tier1 lock stale** | 🔧 needs fix | predates LongeviQuest trait-freq refresh (§2.2). Re-run. |
| 10 | **NHANES sentinel value** | ⚠ known limitation | `5.397605346934028e-79` recurs in count columns (≈ encoded missing/zero); needs explicit NA mapping before baseline stats in Step D. |
| 11 | **NHANES values are raw codes** | ⚠ known limitation | `nhanes_merged.csv` categoricals are CDC numeric codes, not labels; codebook decode needed before scoring. |
| 12 | **`supercentenarians.still_alive` mixed type** | 🔧 minor fix | "deceased"/"alive" strings (wiki rows) vs bool (atlas rows) in one column. Normalize. |
| 13 | **Empty/failed dataset files** | 🔧 minor fix | `figshare_italian_genomics_metadata.csv` and `hmd_DOWNLOAD_INSTRUCTIONS.txt` are 0 KB. |
| 14 | **NHANES too few 95+** | ⚠ known limitation (by design) | centenarian-class biomarker distributions need literature/curation, not NHANES (Step A). |
| 15 | **HMD quality warnings** | ✅ handled | 30/50 countries flagged; propagated as CI-widening, not score penalty. |
| 16 | **LongeviQuest slug-collision loss** | ⚠ known limitation (accepted) | Profile scraper derives slugs from names; 4 names collide (Grace Jones ×3, Louise Fleury ×2, Sarah Smith ×2, Tome Tanaka ×2) → **~5 distinct supercentenarians not scraped** (LongeviQuest disambiguates with `-2`/`-3` URL suffixes we don't request). ~0.13% loss, all common Anglo names; no material effect on trait stats. **Fix if needed:** retry colliding slugs with `-2`/`-3` suffixes (cheap top-up), or capture real profile hrefs from atlas list pages (robust). User decision: **keep as-is.** |
| 17 | **`N/A` anonymous-row filter gap** | ⚠ known limitation | `scrape_longeviquest.py` filters exact `N/A` but not spaced variants (`N / A`, `N/ A`), so ~59 anonymous validated supercentenarians remain in `longeviquest_atlas.csv` (3,924 named rows). They collapse to one `n-a` slug in the profile scrape (404s harmlessly — no profile page exists). **They were included in the 90.4%-female atlas gender stat** — acceptable (real people, just unnamed), but note the named-only count is ~3,865. |

---

### LongeviQuest scrape count reconciliation (3,941 → staged)

For the record, why the profile scrape count is not 3,941:

| stage | count | dropped |
|---|--:|---|
| Atlas site total | 3,941 | — |
| Named rows in `longeviquest_atlas.csv` | 3,924 | −17 (exact-`N/A` filtered at parse) |
| Unique slugs (scrape targets) | 3,861 | −63: ~59 spaced-`N/A` anonymous collapsing to one `n-a` slug (flag 17) + ~5 distinct-people name collisions (flag 16) |
| Staged after fetch | ~3,750–3,850 (expected) | further −404s (derived slug ≠ real slug) and −short-bios (<20 words) |

This is expected and accepted; the only real loss is the ~5 collision people (flag 16). Anonymous `n-a` has no profile page to scrape.

## 5b. CODE DOCUMENTATION

✅ **Strong baseline:** every one of the 31 scripts has a **module-level docstring**, and **zero scripts use hardcoded absolute paths** (all relative-from-root). Imports are complete (scripts run as-is).

⚠ **Gaps:**
- **Function-level docstrings are sparse** in the large scrapers and some pipeline scripts: `scraper_academic.py` (1/16 functions documented), `scraper_news.py` (1/15), `scraper_datasets.py` (1/18), `process_new_datasets.py` (3/13), `merge_all.py` (3/9), `normalize_strata_names.py` (0/4), `scrape_longeviquest_profiles.py` (0/9). The well-documented ones: `extract_biomarkers.py` (8/11), `extract_layer1_traits.py` (9/13), `nlp_pipeline.py` (16/26).
- **Recommendation:** add one-line docstrings to public functions in the four big scrapers before publication; they're the files an external contributor will read first.
- **No type hints** anywhere — acceptable for research code, but the eventual `score.py` (public API) should have them.
- Convention is consistent: `python script.py` from repo root, `PYTHONIOENCODING=utf-8` for non-ASCII, idempotent skip-if-exists scrapers.

## 5c. PROJECT STRUCTURE

Current layout vs. standard research/package layout:

| expected | present? | note |
|---|---|---|
| `data/{raw,processed}` | ✅ | well organized; `data/raw/datasets/` mixes scraped + external reference data |
| `data/external/` | ❌ | external reference sets (HMD, WHO, UN, NHANES) live under `data/raw/datasets/` — consider splitting `external/` from scraped `raw/` |
| `src/` or `scripts/` | ❌ | **all 31 `.py` sit in repo root** — flat. Should move to `src/` (or `scripts/` + `src/`), separating the ~10 production-pipeline modules from scrapers and `_*` scratch |
| `notebooks/` or `analysis/` | ❌ | no separation of exploratory vs production; the `_*.py` diagnostics are the de-facto analysis layer, intermixed in root |
| `models/` | ❌ | not yet created (Phase 3 Step F) |
| root README/docs | ✅ | `README.md`, `METHODS.md`, `data_dictionary.md`, `documentation_gaps.md`, `audit_report.md` |
| `requirements.txt` / env | ❌ | missing |
| `.gitignore` / git | ❌ | **not a git repository** |

**Orphaned / misplaced:** the 8 `_*.py` scratch scripts in root should be moved to a `scratch/`/`analysis/` dir or deleted; `_audit_registry_and_dedup.py` is superseded. Two 0-KB data files (flag 13) are dead.

---

## 6. PACKAGE READINESS — **3.5 / 5**  *(was 2/5; raised 2026-06-01)*

> *Can someone clone this and run the pipeline end-to-end?* Nearly — env, entry point, and license are now in place; git init and the large-file fetch remain.

| criterion | state |
|---|---|
| One-line env setup (`pip install -r requirements.txt`) | ✅ `requirements.txt` added (note: spaCy model needs `python -m spacy download en_core_web_sm`) |
| Clear "what to run first" | ✅ pipeline run order documented in `README.md` |
| No assumed local files | ⚠ pipeline assumes large local raw files (151 MB WGS, 111 MB HMD, 280 MB zips) not fetchable by a clone; no download script for those |
| Version control | ⚠ `.gitignore` ready (excludes ~600 MB), but **`git init` not yet run** |
| License | ✅ MIT (`LICENSE`) |
| Reproducibility of derived files | ⚠ scripts idempotent, but two outputs are stale (§2) and there's no single `run_all` orchestrator |

**What moves it to 4.5/5:** `git init` + first commit; regenerate the stale outputs (§2 cascade); move scripts into `src/`. **5/5** additionally needs a `run_all.py` orchestrator and a fetch script (or data release) for the large external files.

---

## RECOMMENDED ORDER BEFORE STEP D

1. **Finish LongeviQuest integration** (scrape running) → merge → `analyze_profile_delta.py` → report delta.
2. **Run the §2 regeneration cascade** (clears both stale-file flags and folds in profiles).
3. **Quick-win docs** — README, METHODS, requirements.txt, .gitignore, LICENSE all done (2026-06-01); **`git init` + first commit** still outstanding.
4. **Then Step D** (`tier3_nhanes_baselines.parquet`) — but first apply NHANES NA-sentinel mapping (flag 10) and codebook decode (flag 11), or the baselines will be corrupted.
