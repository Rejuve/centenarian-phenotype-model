# Tier 2 & Tier 3 evaluation — variables, scoring, and mortality/PhenoAge validation

This document specifies the Tier-2 and Tier-3 variable sets and scoring, and reports their validation
against all-cause mortality and against PhenoAge (Levine 2018) on NHANES with linked mortality. It is
structured to map onto STROBE (observational association) and TRIPOD (prediction-model reporting).

The tiers are **compounding**: Tier 3 encompasses Tier 2, which encompasses Tier 1.

```
Tier 1  (teaser, 12 self-report behavioural items)
   ⊂ Tier 2  (self-report — behaviour + clinical state + family history — PLUS non-invasive measured
              features: anthropometrics, grip, BP, basic body composition)
        ⊂ Tier 3  (Tier 2 + features needing a biospecimen/assay: lab biomarkers, genomic variants,
                    DNA-methylation clocks)
```

The tier boundary is the **necessity of a biospecimen + specialized assay**, encoded per feature as an
`access` tag (`self_report | anthropometric | lab | genomic | epigenetic`). Tier 2 = self-report +
`anthropometric` (non-invasive, free/consumer-obtainable, assumed true for insights). Tier 3 adds
`lab | genomic | epigenetic` — what you could only get from a blood draw, genotyping, or a methylation
array. Tier 3 does not re-list diagnoses (those stay self-report at Tier 2); it detects and quantifies
the underlying state through measurement. Product/paywall gating is a separate app concern and is not
represented in the open model.

---

## 1. Data

- **NHANES Continuous (1999–2016)** survey + examination + laboratory files, linked to the **NCHS
  Public-use Linked Mortality File** (2019 release; doi:10.15620/cdc:117142). Cohort: **N = 53,255**
  mortality-linked adults, **9,104 deaths**.
- **PhenoAge** computed from its published 9-biomarker + age formula on the 2005–2016 cycles with the
  full lab panel: **n = 10,495**, **1,365 deaths**.
- **DNA-methylation clocks** from the NHANES **DNAm Epigenetic Biomarkers** public file (1999–2002
  subsample, published 2024): **n = 2,532** with clocks, **1,361 deaths**.

All-cause mortality within follow-up is a **survival proxy**, not centenarian attainment; results are a
single national cohort; estimates are unweighted (survey-design weighting is a planned collaborator
item). Aggregate results only, per the NCHS Data Use restrictions.

---

## 2. Tier-2 variables (self-report)

Behavioural block (NHANES-aligned) + self-reported clinical/health block + family history. 32 items;
inclusion follows the data-first rule (behaviours present in the news ∩ academic corpus; clinical
constructs are centenarian-correlates from the academic/biomarker corpus, each documented and cited).

Self-report features ranked by age/sex-adjusted mortality association (negative = protective; landmark
excludes deaths < 24 months as a reverse-causation guard):

| feature | adj. coef | landmark |
|---|---:|---:|
| functional mobility | −0.389 | −0.354 |
| smoking | −0.362 | −0.357 |
| self-rated health | −0.346 | −0.318 |
| depression (absence) | −0.230 | −0.204 |
| cardiovascular event (absence) | −0.222 | −0.204 |
| partnership | −0.216 | −0.196 |
| alcohol (moderate) | −0.171 | −0.153 |
| sleep | −0.130 | −0.115 |
| diabetes (absence) | −0.119 | −0.108 |
| hypertension (absence) | −0.106 | −0.095 |
| diet | −0.097 | −0.089 |
| cancer history (absence) | −0.065 | −0.045 |

Family-history-of-longevity (parents/grandparents/siblings to 90+) is the highest-weighted Tier-2
feature (0.75); it is not separately NHANES-testable (NHANES does not capture parental age-at-death),
and is grounded in the familial-longevity literature.

**Tier 2 also includes non-invasive *measured* features** (`access: anthropometric`) — obtainable in a
free/consumer setting and assumed true for insights: **grip strength, BMI, calf circumference, muscle
strength** (and waist/BP captured at Layer 2). The scientific tier boundary is whether a feature needs a
**biospecimen + assay**, not whether it is literally typed by the user. NHANES-validated of these:

| Tier-2 measured feature | n | AUC→survival | adj. coef | landmark | read |
|---|---:|---:|---:|---:|---|
| grip strength | 10,367 | 0.561 | −0.171 | −0.143 | sarcopenia/frailty marker (2011–2014) |
| BMI | 49,697 | 0.496 | +0.007 | +0.002 | **null** — U-shape, see §6 |

---

## 3. Tier-3 variables (measured by biospecimen/assay) + NHANES testability

Tier 3 = Tier 2 **plus** features that require a **blood draw + lab assay, genotyping, or a methylation
array** (`access: lab | genomic | epigenetic`). The testability column states whether each is
validatable on NHANES today (the genomic block is not — it requires an external genotyped cohort).

### 3a. Lab biomarkers (blood draw + assay, 14) — NHANES-testable

Age/sex-adjusted mortality association (rebuilt cohort with the widened panel):

| lab biomarker | n | AUC→survival | adj. coef | landmark | read |
|---|---:|---:|---:|---:|---|
| C-reactive protein | 36,838 | 0.598 | −0.310 | −0.284 | strongest lab biomarker |
| white blood cell | 48,116 | 0.513 | −0.222 | −0.204 | inflammaging / PhenoAge component |
| triglycerides | 22,914 | 0.590 | −0.192 | −0.199 | robust |
| eGFR | 42,206 | 0.780 | −0.185 | −0.145 | high AUC is age-linked; still protective adjusted |
| telomere length | 7,823 | 0.703 | −0.155 | −0.158 | 1999–2002 T/S ratio |
| HDL cholesterol | 42,548 | 0.504 | −0.125 | −0.116 | modest |
| glucose | 23,326 | 0.636 | −0.104 | −0.100 | robust |
| HbA1c | 48,087 | 0.649 | −0.079 | −0.075 | weak, protective |
| LDL cholesterol | 22,032 | 0.493 | +0.025 | +0.018 | **null/inverted** — see §6 |

Seven of nine NHANES-testable lab biomarkers show protective age/sex-adjusted associations robust to
landmarking (LDL is the documented paradox; the remaining Tier-3 lab features — IL-6, cortisol,
testosterone, thyroid — are scored from a panel but not in standard NHANES).
The remaining Tier-3 clinical features (IL-6, cortisol, testosterone, thyroid, muscle strength, calf
circumference) are scored from a user's panel but are not in standard NHANES, so are not validated here.

### 3b. DNA-methylation clocks (epigenetic) — NHANES-testable (1999–2002 subsample)

Age acceleration = clock age − chronological age (lower favourable); DunedinPACE is pace of ageing
(<1.0 favourable). Age/sex-adjusted mortality association:

| clock | adj. coef | landmark | note |
|---|---:|---:|---|
| GrimAge2 | −0.685 | −0.660 | strongest single feature in the model |
| GrimAge | −0.649 | −0.618 | |
| DunedinPACE | −0.472 | −0.452 | pace of ageing |
| PhenoAge (DNAm) | −0.365 | −0.343 | |
| Hannum | −0.282 | −0.268 | |
| Horvath | −0.247 | −0.231 | |
| SkinBlood | −0.103 | −0.099 | chronological clock, weaker mortality signal |
| DNAm telomere (HorvathTelo) | 0.000 | 0.000 | scale mismatch with the T/S-ratio mapper (fix pending), not a biological null |

The raw unadjusted AUC for acceleration-based clocks is age-confounded; the **age-adjusted coefficient**
is the correct read and is the strongest in the feature set, consistent with GrimAge being the leading
mortality clock in the literature (Lu 2019; Belsky 2022).

### 3c. Genomic variants — NOT NHANES-testable

21 inlined longevity variants + an 80-variant scoreable curated catalogue. NHANES releases no public
genotypes, so the genomic layer is literature-grounded (GWAS Catalog effect directions) but **not yet
validated on linked individual-level mortality**. External validation requires a genotyped + mortality
cohort (UK Biobank / dbGaP) — a collaborator-dependent item.

---

## 3d. Intended use: Tier 3 as a longevity-trajectory / efficacy instrument

The Tier-3 measured panel, taken **together and measured repeatedly**, is intended as a longevity-
trajectory predictor: an objective instrument to evaluate whether a therapeutic or protocol is placing a
person on a healthier trajectory toward 100+. A single reading estimates current standing; the change in
the panel between readings is the trajectory signal, and serves as a surrogate read-out of intervention
efficacy.

This use favours features that are both mortality-predictive (§3a–b) **and responsive to change**.
Several components are purpose-built or well-suited for repeated-measures tracking:

- **DunedinPACE** — pace of ageing per calendar year; designed to detect intervention effects in trials.
- **Epigenetic age acceleration** (GrimAge/PhenoAge/Hannum/Horvath) — the strongest mortality signals
  here, and shift with sustained exposures.
- **CRP / WBC** (inflammatory load), **HbA1c / glucose** (glycaemic control), **grip strength**
  (function), **HDL / triglycerides** (lipids) — established, modifiable, repeatable markers.

The cross-sectional mortality association in this document establishes that the panel **tracks survival**.
Using it as an *efficacy* instrument additionally requires **within-person sensitivity-to-change**
validation (a repeated-measures or interventional cohort) and links to the cause-specific trajectory
model (`scripts/validation/trajectory_model.py`). Both are collaborator/data-dependent and are stated as
pending, not claimed.

## 4. Tiered score → mortality discrimination (compounding)

The composite score at each tier, as a predictor of all-cause survival (age/sex-adjusted weight;
negative = higher score lowers modelled mortality):

| score | n | deaths | AUC→survival | age/sex-adj weight |
|---|---:|---:|---:|---:|
| **Tier 2** (self-report quiz) | 53,255 | 9,104 | 0.660 | −0.318 |
| measured-only (all clinical inputs) | 50,559 | 8,155 | 0.662 | −0.374 |
| **Tier 3 = self-report + measured** | 53,255 | 9,104 | **0.692** | **−0.439** |

Self-report and measured data are complementary: the compounded score discriminates better than either
component alone, and carries the strongest age/sex-adjusted protective weight. Two caveats: (1) this
composite does not yet fold in the epigenetic clocks of §3b, which were validated separately and are the
strongest individual signals; integrating them is a pending step. (2) The "measured-only" row pools all
clinical inputs as run; under the `access` taxonomy the anthropometric features (grip/BMI/calf) belong to
Tier 2, so a fully access-partitioned re-run (self-report+anthropometric vs lab/omics) is a refinement —
it does not change the conclusion that the layers compound.

Calibration of the composite (held-out): ECE 0.018, Brier 0.090.

---

## 5. Benchmark against PhenoAge (Levine 2018)

PhenoAge is the clinical-biomarker biological-age gold standard. On the 2005–2016 PhenoAge subset
(n = 10,495, 1,365 deaths):

- **Concurrent validity** — the phenotype score correlates with PhenoAge acceleration: Pearson −0.589,
  Spearman −0.609, age/sex-adjusted standardized β −0.601. A more centenarian-like profile corresponds
  to a decelerated (younger) PhenoAge.
- **Mortality discrimination** — raw AUC: PhenoAge 0.885 vs phenotype score 0.698 (PhenoAge embeds
  chronological age in its formula; the phenotype score is age-independent by design). Age/sex-adjusted
  out-of-sample: age+sex 0.861 → +PhenoAgeAccel 0.883 → +phenotype score 0.875. The phenotype score
  adds nearly as much over age/sex as PhenoAge acceleration does.
- **Incremental value** — added on top of PhenoAge acceleration + age + sex (non-circular; PhenoAge
  input features excluded): the self-report block adds **+0.020** AUC (0.883 → 0.903); the full
  non-PhenoAge block adds **+0.020** (→0.903). The phenotype features carry mortality information beyond
  PhenoAge.

---

## 5b. Data-first feature re-check (enriched corpus)

After expanding the academic corpus with a foundational aging-biology backbone (hallmarks of aging,
geroscience, compression-of-morbidity) and the missing NECS papers, an open screen
(`scripts/analysis/corpus_feature_recheck.py`) tested whether any construct *not* already modelled
earns a data-first basis for inclusion — without pre-entering candidates. On the
longevity/centenarian-focused subset (n≈2,700):

- **Existing feature categories are confirmed** as the dominant signals: purpose/psychology (39%),
  diet (32%), social (27%), physical activity (24%), sleep (15%), inflammation (12%), glucose (11%),
  lipids (11%), functional/epigenetic/APOE/hormones/microbiome/telomere/IGF-1/FOXO3 below that — all
  already represented.
- **Top non-modelled candidate: education / socioeconomic status** (~3.3% of the focused subset) — a
  well-established mortality determinant, self-reportable (Tier 2). Flagged for evidence grading; not
  auto-added.
- **Parental/offspring longevity** appears strongly (~2.7%) and is **already captured** by the Tier-2
  family-history-of-longevity item — a confirmation, not a gap.
- **Moderate candidates** for future evidence grading (not added): sleep apnea, oral/periodontal,
  vitamin D.
- **Spurious-correlate guard:** "hearing aid / prosthetic / wheelchair" — the kind of artefact a
  chronological-age regression throws up — is near-absent in the focused longevity literature (~0.2%),
  confirming the corpus-driven rule avoids those artefacts.

This is a screen (a strong signal is a candidate, not an automatic inclusion); it confirms the current
set and surfaces education/SES as the one construct worth grading next.

## 6. Feature-validity nuance: BMI and LDL

Each feature's alignment direction is set **a priori from clinical guidelines** (WHO BMI bands; NCEP
ATP III LDL cut-offs) and never sees the mortality outcome; the association test then measures
empirically whether that direction tracks survival. For BMI and LDL the data does not confirm the
guideline direction, for documented reasons:

- **BMI** reads ~null because the guideline U-shape (favouring 18.5–25) does not match the all-cause
  mortality shape in an all-age sample: low BMI is strongly lethal (frailty) while high BMI is not
  proportionately lethal (the obesity paradox), so the symmetric guideline penalty decorrelates from
  survival.
- **LDL** reads null/inverted because low LDL tracks higher all-cause mortality in older adults
  (illness lowers LDL; the elderly LDL paradox — Ravnskov 2016, PMID 27292972).

These are honest empirical outputs, not imposed: the analysis treats every feature identically and does
not special-case or fix these results. They are reported as a clinical-risk-vs-all-cause-mortality
validity nuance, not removed.

---

## 7. Reproduce

```bash
python scripts/validation/build_cohort_from_xpt.py --cycles 1999-2000,...,2015-2016 \
    --out data/processed/nhanes_cohort_feat_v2.csv      # cohort incl. WBC/grip/telomere
python scripts/validation/feature_association.py --cohort data/processed/nhanes_cohort_feat_v2.csv \
    --out reports/tier3_feature_assoc_v2                # per-feature association
python scripts/validation/validate.py --cohort data/processed/nhanes_cohort_feat_v2.csv \
    --ablate-cols score_selfreport,score_labs,score_full --out reports/tier_ablation_v2   # tiered AUC
python scripts/validation/phenoage_comparison.py --cohort data/processed/nhanes_cohort_feat_v2.csv \
    --cycles 2005-2006,...,2015-2016 --out reports/phenoage_comparison_v2                 # PhenoAge
python scripts/validation/build_epi_cohort.py --out data/processed/nhanes_epi_cohort.csv && \
python scripts/validation/feature_association.py --cohort data/processed/nhanes_epi_cohort.csv \
    --out reports/epi_clock_assoc                       # epigenetic clocks
```
