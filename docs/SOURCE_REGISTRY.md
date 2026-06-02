# Source Registry

Tracked companion to the operational `data/processed/source_registry.csv` (gitignored with the
`data/` tree). This file (a) defines the **enriched schema** every source should carry, (b) documents
the **currently integrated** sources against it, and (c) lists **prioritized, freely-available
candidate sources** — ordered by how much they move the model toward *validation* per the lowest
acquisition effort. See `VALIDATION_PLAN.md` for how these feed the validation gates.

## Schema (target columns)

Each source row should record:

| column | meaning |
|---|---|
| `source_name` | canonical name |
| `license_access` | `open` / `free_registration` / `application_required` / `restricted` |
| `raw_location` | URL or acquisition path |
| `processed_artifact` | path under `data/processed/**` (or `pending`) |
| `population` | who the sample covers |
| `age_range` | covered ages |
| `cent_relevance` | `verified_cent` / `verified_super` / `nonagenarian` / `mortality_outcome` / `healthspan` / `context` |
| `use` | `training` / `validation` / `contextual` only |
| `bias_limitations` | known bias and caveats |

## Currently integrated

| source | license/access | population | age range | cent relevance | use | bias / limitations |
|---|---|---|---|---|---|---|
| LongeviQuest atlas + profiles | open (attribution; partnership discussed) | validated 110+ | 110+ | verified_super | training | ~90% female; Western/high-income skew |
| Wikipedia supercentenarians | open | oldest-people tables | 110+ | verified_super | contextual | crowd-maintained; high missing-gender pre-merge |
| TidyTuesday centenarians | open (CC) | record-holder subset | 100+ | verified_cent | contextual | 80.6% male, non-representative; down-weighted |
| Academic corpus (PubMed/EuropePMC/Semantic Scholar) | open (abstracts) | longevity literature | mixed | healthspan | training | abstract-only; no full text |
| News / GDELT / obituary / oral-history | open (various) | named centenarians | 100+ (age floored) | verified_cent | training | **no 90–99 subjects** (nonagenarian floor) |
| NHANES 2017–2018 (+ methylation) | open | US population | all | mortality_outcome / context | validation | few subjects 95+; cross-sectional |
| GWAS Catalog (longevity) | open | GWAS summary | n/a | healthspan/genetic | training | single longevity source currently |
| WHO GHO / UN WPP / Human Mortality Database | open | country-level | all | context | contextual | 30/50 HMD countries carry quality warnings |
| Italian centenarian WGS | open (Figshare) | semi-supercentenarians | 105+ | verified_super | contextual | small n (~27); GRCh build mismatch |
| Centenarian gut microbiome (Zenodo 6579480; PLOS One) | open | centenarian gut | 100+ | healthspan | pending | no validated reference distribution wired in |

## Prioritized candidate sources (toward validation)

Ordered: **lowest effort × highest validation value first.** All listed are freely usable for
research under the stated access tier; none require purchase.

### P1 — closes a validation gate directly

1. **NHANES Public-Use Linked Mortality File** (NCHS) — `license_access: open`.
   - Raw: `cdc.gov/nchs/data-linkage/mortality-public.htm`. We already hold NHANES; this is the
     linkage that turns it into a **survival outcome** dataset.
   - `cent_relevance: mortality_outcome`; `use: validation`. Enables calibration + score-distribution
     + ablation against actual mortality (`VALIDATION_PLAN.md` §2). **Highest ROI, near-zero new cost.**
   - Bias: follow-up is all-cause mortality; few reach 100 within follow-up.

2. **Health and Retirement Study (HRS)** — `license_access: free_registration`.
   - Raw: `hrsdata.isr.umich.edu`. US 50+ panel with biomarkers, frailty, cognition, **and the 90–99
     band the corpus lacks** + linked mortality.
   - `cent_relevance: nonagenarian + mortality_outcome`; `use: validation` (and likelihood
     calibration). **Closes the nonagenarian-class gap** that blocks the four-class NB calibration.

3. **Gateway to Global Aging Data (harmonized HRS/ELSA/SHARE)** — `license_access: free_registration`.
   - Raw: `g2aging.org`. Harmonized variables across US/England/Europe aging panels → cross-population
     **subgroup validation** (geography) with one schema.
   - `cent_relevance: nonagenarian/healthspan`; `use: validation`.

### P2 — strengthens evidence base / external validation

4. **GWAS Catalog + IEU OpenGWAS lifespan/parental-longevity/healthspan traits** — `open`.
   - Raw: `ebi.ac.uk/gwas`, `gwas.mrcieu.ac.uk`. Adds GWAS sources beyond the single current one →
     lets the Layer-3 `gwas_corroborated` weight scale up with more than one source.
   - `use: training`; bias: ancestry skew toward European cohorts.

5. **Public DNA-methylation datasets (GEO) with computable clocks** — `open`.
   - Raw: NCBI GEO series carrying 450K/EPIC betas; clock coefficients open for Horvath/Hannum/
     PhenoAge/DunedinPACE (GrimAge restricted). Pairs with `clocks.py`.
   - `cent_relevance: healthspan/biological_age`; `use: validation` of the epigenetic mappers.

6. **International Database on Longevity (IDL) / GRG verified tables** — `free_registration` /
   research-use. Independent verified 110+ records for **external validation** of the registry,
   distinct from LongeviQuest. `use: validation`.

7. **MIDUS (Midlife in the US) biomarker project** — `free_registration`.
   - Raw: `midus.wisc.edu`. Biomarkers + mortality linkage; complements HRS for clinical-clock
     (clinical PhenoAge) validation. `use: validation`.

### P3 — application-gated (higher effort)

8. **UK Biobank** — `application_required` (cost + approval). Deep biomarkers/genomics/methylation
   subset/accelerometry; powerful for ablation + subgroup but heavyweight access.
9. **Long Life Family Study (LLFS)** / **New England Centenarian Study** — `application_required`
   (dbGaP/PI). Directly on-endpoint (familial longevity, centenarian offspring) but restricted.

## How candidates map to validation work

- P1.1 (NHANES mortality) → calibration + score-distribution + ablation gates.
- P1.2/P1.3 (HRS / G2Aging) → **nonagenarian-class likelihood calibration** (flips NB
  `calibration` from `heuristic_pending` → `calibrated`) + geographic subgroup performance.
- P2.4 (more GWAS) → scales Layer-3 genetic weight beyond a single source.
- P2.5 (GEO methylation) → validates `clocks.py` / epigenetic mappers.
- P2.6 (IDL/GRG) → independent external validation of the verified-centenarian registry.
