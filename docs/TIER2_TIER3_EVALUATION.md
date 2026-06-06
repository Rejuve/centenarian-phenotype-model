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

### 3a. Lab biomarkers (blood draw + assay, 13) — NHANES-testable

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
| thyroid TSH (longevity-shifted) | 9,199 | 0.452 | −0.080 | −0.069 | protective adjusted; strengthens to −0.099 at 65+ (thyroid paradox) |
| testosterone (sex-specific) | 10,693 | 0.579 | −0.040 | −0.035 | weakly protective, confounded → conservative 0.40 weight |
| LDL cholesterol | 22,032 | 0.493 | +0.025 | +0.018 | **null/inverted** — see §6 |

Nine of eleven NHANES-testable lab biomarkers show protective age/sex-adjusted associations robust to
landmarking (LDL is the documented paradox). **TSH and testosterone** were added in the 2007–2016 cycles
that carry those assays: both are weakly protective after adjustment, and TSH's signal concentrates in
the 65+ stratum exactly as the thyroid paradox of longevity predicts (its sub-0.5 univariate AUC is
age-confounding — TSH rises with age — not an inverted direction). The two remaining lab features —
**IL-6 and cortisol** — are not measured in standard NHANES; they carry literature-grounded direction
(`validation_status: literature_only`) rather than a cohort result.

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

**Empirical oldest-old anchor (the clock direction, measured not declared).** The corpus is age-floored
at 100 and NHANES tops out at 80, so the centenarian-favourable clock direction was previously a declared
assumption. It is now measured on AI-permissible public methylomes containing **verified 89–103-year-olds**
(GEO GSE30870 + GSE40279; biolearn clock implementations; `epi_oldest_old_anchor.py`). Mean epigenetic age
acceleration (clock age − chronological) deepens monotonically with survival to extreme age:

| age band | n | mean acceleration (yr) | % biologically younger |
|---|---:|---:|---:|
| <60 | 247 | +1.1 | 38% |
| 60–79 | 309 | −2.8 | 78% |
| 80–89 | 91 | −6.8 | 96% |
| 90–99 | 26 | −10.1 | **100%** |
| 100+ | 3 | −13.7 | **100%** |

All 29 individuals aged 90+ show negative acceleration — survival selection for a slow epigenetic clock.
The 90+ per-clock centroid (Horvath −12.8, PhenoAge −15.4, SkinBlood −12.2) is the **measured**
exceptional-longevity molecular profile that anchors the Tier-3 epigenetic layer (`epigenetic_population_anchor`
in `tier3_model.yaml`). Small-n and cross-sectional; it grounds the *direction*, not yet a calibrated
within-person trajectory (that needs the longitudinal/interventional methylation milestone).

### 3c. Genomic variants — NOT NHANES-testable

21 inlined longevity variants (the live genomic panel) with an 80-variant direction-resolved reserve
catalogue (documented, not scored by the engine), plus open longevity
**polygenic scores** from the PGS Catalog (`pgs_longevity` PGS000906; `pgs_parental_lifespan`,
Timmers 2019; trait EFO:0004300) applied when a user's genotype yields the score. The genomic layer is
literature-grounded (GWAS/PGS Catalog effect directions); validating it on linked individual-level
mortality is the next step and requires a genotyped, outcome-linked cohort (UK Biobank / dbGaP) — a
collaborator-dependent item.

### 3d-bis. Gut microbiome — NOT NHANES-testable

**Plan:** move from literature-direction to data-grounded by deriving a centenarian-vs-control taxa
reference from open datasets (Zenodo 6579480; SRA centenarian metagenomes — PRJNA895352/PRJNA772518)
and seeking an outcome-linked cohort for validation; until then it is a documented, conservative-weight
placeholder.

Two scoreable features (`access: microbiome`): alpha-diversity and centenarian-associated-taxa
enrichment (Akkermansia muciniphila, Christensenellaceae, Bifidobacterium, SCFA-producers), with
direction from consistent cross-population centenarian signatures (Gut Microbes 2024 PMC11364081;
Biagi; Hainan cohort). Literature-grounded and conservative-weighted; NHANES has no microbiome, so this
layer is **not validated on our mortality cohort** — like genomics, it needs an outcome-linked cohort.

---

## 3d. Intended use: Tier 3 as a longevity-trajectory indicator

The model's initial goal is to indicate, with reproducible and reputable certainty, whether a profile is
on an aging trajectory **consistent with reaching an exceptional, healthy old age** — and which modifiable
features could move it toward that trajectory. The Tier-3 lab/molecular panel is the deepest, most
objective layer of that indicator, and is the natural instrument for clinical and aging-research use.

A future milestone — **not a claim of this model** — is repeated-measures use to evaluate whether a
therapeutic or protocol shifts a person's trajectory; that requires longitudinal/interventional data and
is out of scope here. Features that are both mortality-predictive (§3a–b) **and responsive to change**
position the panel for that future use:

- **DunedinPACE** — pace of ageing per calendar year; designed to detect intervention effects in trials.
- **Epigenetic age acceleration** (GrimAge/PhenoAge/Hannum/Horvath) — the strongest mortality signals
  here, and shift with sustained exposures.
- **CRP / WBC** (inflammatory load), **HbA1c / glucose** (glycaemic control), **grip strength**
  (function), **HDL / triglycerides** (lipids) — established, modifiable, repeatable markers.

The cross-sectional mortality association in this document establishes that the panel **tracks survival**
(the trajectory-indicator claim). The future intervention-efficacy direction would additionally require
**within-person sensitivity-to-change** evidence from longitudinal/interventional data — out of scope
here and explicitly not claimed.

## 4. Tiered score → mortality discrimination (compounding)

Each tier's score (evidence-weighted mean of its features' alignments, partitioned by `access`) as a
predictor of all-cause survival, age/sex-adjusted (negative weight = higher score lowers modelled
mortality; 24-month landmark in parentheses). Reproduced by `tier_ablation_by_access.py`:

| tier | features | AUC→survival | age/sex-adj weight |
|---|---|---:|---:|
| **Tier 2** | self-report + anthropometric | 0.655 | −0.333 (−0.303) |
| **Tier 3** | + lab biomarkers | **0.686** | **−0.410 (−0.378)** |
| *(reference)* self-report only | quiz | 0.660 | −0.318 |
| *(reference)* lab only | blood/lab | 0.677 | −0.362 |

n = 53,255 (9,104 deaths). The layers **compound**: adding the lab/molecular block lifts discrimination
and the protective weight over Tier 2. The anthropometric features contribute little on their own
(BMI is the documented null of §6; grip has limited cycle coverage), so the lift is carried by the lab
layer. The full-cohort composite above does not include the §3b epigenetic clocks (available only in the
1999–2002 DNAm subsample); their contribution is quantified in §4a. The deployed composite scorer (with
its gwas-corroboration bonus) gives a held-out Tier-3 AUC of ~0.69, consistent with the above.

Calibration of the composite (held-out): ECE 0.018, Brier 0.090.

### 4a. Composite + epigenetic clocks (DNAm subsample)

On the 1999–2002 DNAm subsample (n = 2,532, 1,361 deaths), folding the clocks into the composite
Tier-3 score (`composite_with_clocks.py`):

| composite | AUC→survival | age/sex-adj weight |
|---|---:|---:|
| Tier 3, no clocks | 0.617 | −0.499 (−0.488) |
| **Tier 3 + clocks** | 0.568 | **−0.652 (−0.632)** |

Adding the clocks **substantially strengthens the age/sex-adjusted protective signal** (−0.50 → −0.65,
landmark-robust) — the strongest in the model. The raw AUC dips because clock *acceleration* is
age-confounded (the same pattern documented for individual clocks in §3b), so for an age-independent
score the **age-adjusted coefficient is the correct read**. This confirms the clocks belong in the
composite where a methylation array is available.

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
- **Most-mentioned non-modelled construct: education / socioeconomic status** (~3.3% of the focused
  subset). Examined and **not included**: it is a general mortality/SES determinant, not a
  centenarian-specific trait, and is era-confounded (many of today's centenarians had limited formal
  schooling), so it does not meet the centenarian-linkage bar the model requires.
- **Parental/offspring longevity** appears strongly (~2.7%) and is **already captured** by the Tier-2
  family-history-of-longevity item — a confirmation, not a gap.
- **Other constructs** screened and not included: sleep apnea, oral/periodontal, vitamin D.
- **Spurious-correlate guard:** "hearing aid / prosthetic / wheelchair" — the kind of artefact a
  chronological-age regression throws up — is near-absent in the focused longevity literature (~0.2%),
  confirming the corpus-driven rule avoids those artefacts.

This is a screen (a strong corpus signal is a candidate, not an automatic inclusion); it **confirms the
current feature set** — no screened construct met the centenarian-linkage bar for inclusion.

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

## 7. Whole-endpoint (ELC) validation

The ELC endpoint is the triple **(1) exceptional age attained · (2) full functional independence ·
(3) high self-reported satisfaction**. NHANES validates two faces of it; the table separates *external*
from *concurrent* outcomes because they carry different strengths of claim.

| face of the endpoint | outcome | AUC | n | circularity |
|---|---|---:|---:|---|
| **Survival** (prospective) | dies in follow-up | **0.71** raw / **0.88** age-sex-adj (ECE 0.012) | 24,678 | none — mortality is not a model input |
| **Healthspan** (concurrent) | functional independence + good self-rated health | **0.63** (objective lab score) / 0.75 (full) | 5,632 | full score partly circular (below) |
| Healthspan + depression-controlled | + PHQ-9 < 10 | 0.73 (suggestive) | 172 | small PHQ-9 subsample |

(`validate.py`, `endpoint_validation.py`. Function is graded — see §7a. Depression is a separate control
axis, not a gate, per Keyes' dual-continua.)

**Circular vs non-circular.** Self-rated health and functional items are model *inputs* and also build the
healthspan *outcome*, so `score_full → healthspan` (0.75) is partly tautological — shared-method variance
between a self-report input and a self-report-containing outcome. The honest figures are therefore (a) the
**objective-only** lab score against the composite (**0.63**, no input↔outcome overlap) and (b) the
**external** mortality outcome (**0.71 / 0.88**, where nothing is a model input). Validity claims rest on
these, not on the circular full-score healthspan number.

**Correlate vs driver (the "self-referential clock" guard).** A high objective↔subjective correlation — a
clinical/omic panel that tracks the subjective endpoint — would be a genuine and exciting biological
*readout* of wellbeing, but a **correlate, not evidence of causal driving**. Distinguishing a model that
merely *shifts with* the targets from one that *explains or moves* them requires the non-circular and
external validation above, plus the multi-domain (omics/genomic/exposome) + longitudinal + causal
(MR/intervention) programme. The concurrent figures identify who is a healthy ager **now** — a proxy for
the prospective "reaches exceptional age functional and satisfied" target, which only longitudinal/app
data can test. ELC is anchored on external outcomes and carries objective domains beyond self-report
precisely to avoid collapsing into a self-referential clock.

### 7a. Functional bar — graded, from data

Whether the functional bar should be full independence or allow minimal assistance was tested by comparing
self-rated health between groups (`function_threshold_test.py`, NHANES PFQ ADL/IADL):

| % good self-rated health | full independence | minimal assistance | dependent |
|---|---:|---:|---:|
| all ages | 79.6 | 58.9 | 34.4 |
| 70+ | 83.1 | 66.3 | 40.6 |
| 80+ | 82.9 | 72.5 | 43.8 |

The full-vs-minimal gap is real but **narrows with age** (21 → 17 → 10 pts), and minimal-assistance 80+
still rate health good 72.5% of the time. So the endpoint **grades** function rather than gating it:
**full** = full functional concordance; **minimal assistance** = partial credit (compatible with a
well-rated life at advanced age); **dependent** (much difficulty / unable) = excluded. Self-rated health is
the lived-well proxy here; NHANES lacks a validated life-satisfaction/eudaimonic instrument, so the deeper
wellbeing axis is **app-collected** (SWLS / Ryff purpose / Flourishing Scale, depression-controlled) and
**MIDUS-grounded** (published scale algorithms + wellbeing↔biomarker associations; microdata not used).

> The healthspan AUC dips slightly with age (0.63 → 0.61 at 75+) from survivor selection / restriction of
> range: by the oldest ages the community-dwelling sample is a narrower, more robust band, and common
> biomarkers — reflecting mid-life risk trajectory — lose discriminating power (the same attenuation seen
> for classic risk factors in the very old).

## 8. Internal validation (optimism-corrected) — calibration layer

Bootstrap optimism correction (200 resamples) of the deployed calibration model (ELC score + age + sex →
P(death)) on the pooled NHANES cohort (n = 53,255, 9,104 deaths; `internal_validation.py`):

- **Discrimination** — apparent AUC 0.884 → optimism **0.000** → **optimism-corrected AUC 0.884**.
  Negligible optimism: a 3-parameter model on 53k subjects has little room to overfit.
- **Calibration slope** — apparent 0.996 → **optimism-corrected 0.995** (1.0 = no shrinkage needed):
  well-calibrated, not overfit.
- **Decision-curve analysis** — the model adds **net benefit over treat-all and treat-none across the full
  0.02–0.50 risk-threshold range**, i.e. useful for flagging elevated-mortality (low-ELC) individuals.

**Scope.** This validates the *calibration layer* (score → outcome) as non-overfit and clinically useful on
NHANES. It does **not** validate the upstream feature *weights* (literature-grounded; assessed by the
per-feature association analyses, §3–§5), and it is *internal* (same population) — **external** validation
on an independent genotyped/longitudinal cohort remains the collaborator-gated step. Per §7, validity is
anchored on this external mortality outcome, not the circular concurrent self-report.

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
