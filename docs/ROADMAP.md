# Roadmap — Centenarian Longevity Phenotype Model

## Data & Evidence Expansion

### Near-term
- **Nonagenarian (90–99) cohort:** targeted scrape of named nonagenarian profiles to extend the longevity tail (the current corpus floor is 100+).
- **Blue Zone regional cohort data:** dedicated datasets from Okinawa, Sardinia, Nicoya, and Loma Linda studies. These regions are currently represented only organically through the news/academic corpus; structured cohort data would materially strengthen population baselines.
- **Gut microbiome integration:** published centenarian microbiome composition profiles (American Gut Project, Italian supercentenarian microbiome studies).

### Recently completed (Step F — this version)
- **Three-tier scoring engine** (`scripts/pipeline/step_f_scoring.py`, `models/tier1-3_model.yaml`): Layer 1 behavioral quiz (12 q / 11 domains), Layer 2 self-report clinical + family history (8 items), Layer 3 blood biomarkers + genomics + epigenetics. Cross-layer combination, per-feature `basis` provenance, `evidence_basis_pct`, completeness ladder (30 / 50 / 80%), and `gwas_corroborated` reintroduced at Layer 3.
- **Epigenetic clock integration:** Horvath, Hannum, SkinBlood, PhenoAge, GrimAge, DunedinPACE + telomere length wired into Layer 3; `nhanes_methylation.csv` registered as the population baseline (epigenetic age acceleration now gold-eligible).
- **SNP / genetic variant enrichment:** expanded from 11 → 21 scored variants from a 508-variant curated longevity panel (`data/processed/genomic_panel_curated.csv`, `step_e_genomic_panel.py`), drawn from `gwas_longevity.csv` (FOXO3, APOE, APOC1, CETP, IL6, ATXN2, HLA-DRB1, ALDH2, the 15q25 cluster, etc.).

### Medium-term
- **Epigenetic gold delta:** compute the quantified centenarian-vs-NHANES epigenetic age acceleration (the anchor is in place; the centenarian clock values remain to be extracted).
- **WGS build-lift:** lift `cent_WGS.txt` positions to GRCh38 so the centenarian-vs-control allele frequencies corroborate more than the current 2 position-matched variants.
- **Metabolomic and proteomic profiles** from published centenarian cohorts.

## Priority data sources

Ranked integration targets. **Documentation only — not yet integrated.**

### Free / public
1. **New England Centenarian Study (NECS)** — public phenotypic summaries and published trait frequencies; highest-quality centenarian cohort. Would upgrade many silver traits toward gold and validate the disease-escape/delayer phenotype encoded at Layers 2–3.
2. **NHANES public files** — already partially integrated (smoking, alcohol, body measures, CBC, CRP, lipids, glucose, methylation, sleep, physical activity). Expand to additional cycles and biomarker modules for tighter population baselines.
3. **GEO (Gene Expression Omnibus)** — centenarian methylation and transcriptomic datasets (search: "centenarian", "supercentenarian", "longevity"; filter *Homo sapiens*). Directly feeds the epigenetic gold-delta and a future transcriptomic layer.
4. **OpenGWAS / IEU GWAS database** — additional longevity GWAS hits beyond `gwas_longevity.csv`; pulling GRCh38-aligned files **resolves the WGS build mismatch** and expands the scored variant panel beyond 21.
5. **Human Mortality Database (HMD)** — population mortality reference (partially present as `hmd_life_tables.csv`); useful for prevalence-ratio grounding.
6. **LongevityMap (genomics.senescence.info)** — curated longevity-variant database; cross-reference against our 21 scored variants to confirm/expand effect directions.
7. **ClinVar + dbSNP** — variant annotation to fill effect-direction gaps in the 80 interpretable variants (428 of the 508 are currently direction-ambiguous `reported`).
8. **Blue Zones Project public data** — already partially backfilled via the news/academic corpus; complete the structured merge (Okinawa, Sardinia, Nicoya, Ikaria, Loma Linda).
9. **PubMed / Europe PMC bulk export** — additional academic corroboration for traits currently below `evidence_score` 0.55 (the bronze tier).

### Restricted but we have access
10. **UK Biobank** — priority targets: body-composition phenotypes (`muscle_mass`, `fat_mass`, `hip_circumference` — stronger signals than BMI that the Layer-2 schema is designed to ingest once sourced; **not yet features**), lifestyle × longevity interactions, and biological-age proxies. Also the longitudinal linkage needed for the predictive-trajectory extension below.

### Suggested additions (beyond the listed set)
- **GWAS Catalog (full, GRCh38)** — the upstream of `gwas_longevity.csv`; a direct re-pull on GRCh38 is the cleanest single fix for the build mismatch.
- **American Gut / Human Microbiome Project** — open microbiome references to give the currently *pending* L3 microbiome feature a scoreable population baseline (see status below).
- **GenAge / DrugAge (HAGR)** — curated ageing-gene and geroprotector references to annotate genomic and (future) intervention features.
- **MetaboLights / Metabolomics Workbench** — open metabolomic repositories for the planned metabolomic layer.

### Status — microbiome integration
Acquired (registration-free): `figshare_pone.0305583` (PLOS One centenarian study supplement), `zenodo_master_table_MGV.txt` + `zenodo_VOGtable.xls` (centenarian gut **bacteriophage / viral** tables). Biagi 2016 (PMID 27185560) and Wilmanski 2021 (PMID 34663975) were **paywalled — not retrievable**. Current state: `gut_microbiome_diversity` is in `tier3_model.yaml` as `status: pending`, **weight 0.00** — the acquired files are raw taxonomy/viral catalogues, **not** a validated centenarian-vs-population diversity distribution, so nothing is scored yet. **To complete:** add an open population microbiome reference (American Gut / HMP, item above) to derive a centenarian-vs-population diversity contrast, then enable the feature with a real weight.

### Long-term — Toward Predictive Trajectory Modeling
The current model characterizes phenotypic patterns associated with exceptional longevity. A planned extension will shift from descriptive similarity to **predictive trajectory modeling** — estimating the likelihood of a superaging phenotype or dramatically slowed biological aging, rather than predicting a specific lifespan.

This extension requires:
- **Longitudinal cohort linkage** (UK Biobank mortality/healthspan follow-up; NHANES mortality linkage).
- **Time-to-event modeling** (Cox regression, Kaplan–Meier survival curves) to derive trajectory likelihood from trait profiles.
- **Interaction modeling** to capture synergistic trait effects. The current Naive Bayes independence assumption is a known simplification; logistic regression with feature-interaction terms is the planned upgrade.
- **Biological aging-rate biomarkers** (epigenetic age delta, telomere attrition rates, frailty progression slope).

The goal is not to predict "will live to 100," but to identify individuals on a superaging trajectory — biological aging dramatically slower than chronological age would predict — and to inform how, where possible, a person may improve their trajectory toward that path.
