# Validation Plan — Centenarian Longevity Phenotype Model

*Status: in progress. A first powered NHANES mortality run and a held-out 10-year survival
calibration **have been executed** (§3b–3c) — a real but **preliminary** signal, **not** a validated
centenarian-prediction claim (see `MODEL_CARD.md` §10). Full validation — calibration to *reaching
specific ages*, large-scale subgroup fairness, ablation-guided re-weighting, and temporal/external
replication — remains outstanding. This plan defines the remaining work and the acceptance gates
before any "validated" claim.*

## 0a. Endpoint & validation standards

The model is evolving from "similarity to verified centenarians" toward a **relative
healthspan/longevity** statement: is this profile consistent with outliving the typical survival
trajectory for the person's own country/sex, with less age-related decline, and higher odds of
reaching 100 on the current trajectory (chronic-disease risk included)?

- **Validated anchor (already in the package):** population survival baselines by country × sex from
  HMD life tables (`longevity_baselines.yaml`). This is the demographic denominator and the
  calibration target.
- **Gold standard cohort:** an individual measured in a common age range (≈60–75) and followed to
  100+ — even sparse. This is what calibrates "phenotype at 65 → odds of reaching 100."
- **Platinum standard:** longitudinal data from youth to 100+ (rare today).
- **Interim anchor:** *reduced biological age at any chronological age* (clocks + age/sex-adjusted
  markers) plus exposomic/lifestyle patterns — measurable at any age without waiting decades.

## 0. Why a plan and not results

The deployed v1 scorer is an **evidence-weighted alignment** model assembled from a curated evidence
corpus; the four-class Naive Bayes posterior layer is implemented but its likelihoods are
heuristic/uncalibrated. Neither has been tested against held-out outcomes. This plan is the gate
between "internally consistent" (where we are) and "externally validated" (where a clinical/product
claim would require us to be).

## 1. Reference cohorts

| cohort | role | usability |
|---|---|---|
| Verified centenarian / supercentenarian records (LongeviQuest, GRG-style) | positive anchor | training/validation where licensing allows; else contextual |
| Nonagenarian references (90–99) | intermediate class | **gap** — corpus has none; must be sourced (HRS/ELSA/SHARE/UKB) |
| General-population baselines (NHANES) | negative/baseline | validation |
| Mortality-linked datasets (NHANES mortality linkage) | survival outcome | validation where legally usable |
| Healthy-aging / morbidity / function datasets (HRS/ELSA/SHARE/UKB, frailty/gait/grip cohorts) | functional endpoints | access/licensing dependent |

## 2. Metrics

- **Score distributions by class** — distributions of `score_pct` and `class_posteriors` for
  verified centenarians vs nonagenarians vs general population; expect monotone separation.
- **Calibration** — reliability curves for `centenarian_posterior` / `supercentenarian_posterior`
  against observed class membership; report ECE/Brier. (Required before posteriors can be called
  probabilities.)
- **Sensitivity analyses** — vary priors, likelihood centroids/σ, and feature weights; report
  ranking stability.
- **Subgroup performance** — by sex, ancestry, geography, and socioeconomic proxies; report gaps.
- **Ablation by feature class** — behavioral-only vs +clinical vs +genomic vs +epigenetic; quantify
  each tier's marginal contribution (validates the 30/50/80 depth ladder).
- **Missingness robustness** — score stability and `evidence_confidence_pct` behaviour under
  random and informative missingness; partial-survey degradation curves.
- **Temporal stability** — same profile across model versions; bounded drift per version bump.
- **External validation** — performance on a cohort not used in any sourcing/curation step.

## 3. Acceptance gates (before any "validated" claim)

1. Monotone class separation with non-overlapping CIs on the primary endpoint.
2. Calibrated posteriors (ECE below an agreed threshold) **before** posteriors are presented as
   probabilities.
3. No subgroup with materially degraded ranking performance without a documented mitigation.
4. Ablation confirms each tier adds signal in the claimed direction.
5. Documented external-validation result on a held-out cohort.

## 3a. Harness (runnable now)

`scripts/validation/` implements the metric engine and is exercised by `tests/test_validation_harness.py`:

- `metrics.py` — AUC (discrimination), reliability/ECE/Brier (calibration), a pure-Python logistic
  calibration model (score [+age/sex] → P(outcome)), score distributions, subgroup summaries.
- `validate.py` — runs the full report; `--synthetic N` self-tests end-to-end with no data.
- `parse_nhanes_lmf.py` — parses the NHANES Linked Mortality File (fixed-width, NCHS layout).
- `build_nhanes_cohort.py` — maps NHANES variables → model inputs via the versioned mappers, scores
  each participant, and joins the mortality outcome. **Already runs on the repo's NHANES data: 5,518
  participants scored**; add the LMF (`--lmf`) to attach the survival outcome.
- `FETCH_MORTALITY.md` — exact acquisition + DUC for the NHANES LMF and the nonagenarian sources.

First real run produces: AUC(score → survival), a fitted phenotype→mortality calibration with
reliability/ECE/Brier, and subgroup AUC by sex/age band — i.e. gates 1, 4 (partial), and the
calibration gate's machinery.

## 3b. First validation result (pooled NHANES 1999–2016, all-cause mortality)

*Run with `build_cohort_from_xpt.py --cycles 1999-2000,…,2015-2016` (follow-up to 2019-12-31, up to
~20 yr) + `validate.py --ablate-cols score_selfreport,score_labs,score_full`. Aggregate statistics
only; individual data not redistributed. Data: NCHS Continuous NHANES + Public-use Linked Mortality
File, 2019 (doi:10.15620/cdc:117142). Analysis/interpretation are the authors', not NCHS.*

- Cohort: **N = 53,255** scored adults, **9,106 deaths** (17.1%). ~15 of 31 Layer-2 questions mapped
  per subject + 8-marker lab panel (HDL, LDL, triglycerides, glucose, HbA1c, eGFR, CRP, BMI).
- **Discrimination, full score alone (no age): AUC(score → survival) = 0.687.**
- **Age/sex-adjusted model** (score + age + sex → P(deceased)): standardized weight on
  **score = −0.39 (protective)**, age +1.86 (dominant), sex_male +0.23; AUC 0.884, ECE 0.019.
- **Protective within every age band** (survival-AUC ≈ 0.54–0.66 across 18–49 / 50–64 / 65–74 / 75+)
  and **in both sexes** (F 0.683, M 0.694) — i.e. **not merely an age proxy**, and directionally fair.

**Ablation by feature class** (adjusted weight on the class score; more negative = more protective):

| feature class | n | AUC(→survival) | adj. weight |
|---|---:|---:|---:|
| self-report (~15 NHANES-mapped Layer-2 questions) | 53,255 | 0.660 | −0.32 |
| measured labs (HDL/LDL/TG/glucose/HbA1c/eGFR/CRP/BMI) | 50,541 | 0.652 | −0.27 |
| **full (combined)** | 53,255 | **0.687** | **−0.39** |

Self-report and labs are now **comparable and complementary** — the full score beats either alone.

**Progression (a real signal strengthens as information is added):** full-score AUC→survival rose
0.590 → 0.661 → **0.687** as the lab panel widened (5→8 markers) and the self-report mapping widened
(2→~15 questions). The behavioral/self-report block — including **PHQ-9 depression (mental
wellbeing)**, self-rated health, physical activity, alcohol, sleep, diet — carries signal on par with
the labs, consistent with the model's behavioral-first design and the product's top-of-funnel quiz.

**Mapping coverage:** ~15 of 31 Layer-2 questions are mapped from real NHANES variables; the remaining
~16 are constructs NHANES never measured (social ties, purpose/meaning, cognitive hobbies, faith,
family-history-of-longevity) and are left unmapped rather than fabricated — so the true full-survey
score would draw on *more* signal than measured here.

**What this is / isn't:** an *out-of-the-box* (untrained) signal that a higher phenotype score
is associated with **lower all-cause mortality** over up to ~20 years, independent of age and in both
sexes, in one US cohort. It is **not** centenarian attainment (a survival proxy), **not** trained on
this data, and **not** externally replicated. It satisfies the *machinery* of gates 1, 4, and the
subgroup gate; calibration of the trajectory band to reaching specific ages, nonagenarian-class NB
calibration, mortality-calibrated re-weighting (Part A), and external replication still stand.

**Power note:** 2017–2018 alone yields only ~127 deaths (1–2 yr follow-up, underpowered); pool earlier
cycles via `build_cohort_from_xpt.py --cycles ...`.

## 3c. Part A — held-out survival calibration (bundled)

*Run with `scripts/validation/calibrate.py` on the pooled cohort; artifact bundled at
`centenarian_phenotype/models/survival_calibration.yaml`. Aggregate coefficients only.*

A small logistic model calibrates the phenotype score to a **fixed 10-year all-cause mortality
horizon** (so differing cycle follow-up does not confound it): `P(die within 120 months) =
sigmoid(b0 + w·z(score, age, sex_male))`. Metrics are **out-of-sample** (70/30
train/test); coefficients then refit on the full eligible cohort for deployment.

- Eligible n = 32,082 (deaths ≤120mo, or known alive ≥120mo; censored-before-horizon excluded);
  10-yr event rate 18.3%.
- **Held-out (n=9,625): AUC 0.896, ECE 0.020, Brier 0.090** — well-calibrated out-of-sample.
- **Standardized score weight = −0.555 (protective, age/sex-adjusted)** — the calibrated, held-out
  effect of the phenotype score on 10-year mortality. (AUC is age-dominated; the score's contribution
  is the age-independent −0.555.)
- Wired into `longevity.relative_longevity()`: when age/sex are supplied, `longevity_context` now
  returns a **calibrated** `calibrated_mortality` block (10-yr mortality probability + ratio vs an
  average-phenotype peer of the same age/sex), replacing the illustrative multipliers. Example
  (70-yo F): score 90 → p≈0.17 (0.58× peer), score 40 → p≈0.83 (2.9× peer).

**Scope/limits:** ALL-CAUSE US 10-year mortality, single national cohort, not externally replicated,
**not centenarian attainment** (which remains the HMD population baseline). The four-class NB
likelihoods are still `heuristic_pending` (need the 90–99 band; see `docs/DATA_STRATEGY.md`).

## 3d. Per-feature association + reverse-causation check (pooled NHANES 1999–2016)

*`scripts/validation/feature_association.py` — age/sex-adjusted logistic of each feature's alignment
on all-cause mortality, with a **landmark** sensitivity that drops deaths < 24 months (a partial
reverse-causation guard). Coefficient on the standardized alignment; **negative = protective**.
Aggregate results only; NCHS-cited (doi:10.15620/cdc:117142).*

**Strongest age-independent protective signals (adj. coef; landmark in parens — persistence = robust):**
- functional mobility −0.39 (−0.35) · smoking −0.36 (−0.36) · self-rated health −0.35 (−0.32) ·
  **C-reactive protein / inflammation −0.31 (−0.28)** · depression −0.23 (−0.20) · prior CVD −0.22 ·
  **partnership/social −0.22 (−0.20)** · triglycerides −0.19 · eGFR −0.19 (−0.15) · moderate alcohol −0.17.

**Reverse-causation read:** the behavioral/functional/psychosocial/inflammatory signals **persist
after excluding early deaths** (e.g. smoking, self-rated health, social partnership barely move),
which argues they are *not* merely "baseline-sick people die soon." Kidney function (eGFR) attenuates
more under landmarking (its huge raw AUC 0.78 is largely age/illness), illustrating the guard working.

**Null and paradoxical associations (inputs to the weight review):**
- **BMI ≈ 0** linear coefficient — a *linear* term cannot detect a U-shaped relationship, so this is
  **consistent with, but does not prove,** a U-shape. The BMI mapper currently *imposes* a U-shape
  from established literature (obesity-paradox / late-life frailty); whether that shape actually holds
  in-cohort must be **tested empirically** (mortality by BMI band), **not assumed** — flagged for the
  data-derived shape review (§4).
- **LDL ("cholesterol") slightly positive** — the inverse LDL–mortality association reported in older
  adults (Ravnskov et al., BMJ Open 2016, PMID 27292972), attributed here to reverse causation
  (declining LDL with frailty and illness), not a protective effect of high LDL. A naïve "fit the
  data" model would wrongly learn "high LDL is protective"; this is exactly why shapes need causal
  care (landmarking, age-strata), not raw curve-fitting. Flags LDL direction for age-stratified review.
- `q_pa_frequency` underpowered here (only 2007+ cycles; 846 deaths) — treat as noisy.

> **Note on provenance (data vs imposed).** Per-feature *alignment shapes* in v1 are **curated from
> literature** (tagged by `basis`), not learned from our statistics. The data-driven goal (§4) is to
> **derive shapes empirically** where outcome data exists — with reverse-causation/confounding
> safeguards — and to label every shape as *data-derived*, *literature*, or *reasoned*, never imposing
> one silently. See §4.

**Implication:** measured mortality association **corroborates** the behavioral-first design and the
inflammatory axis, and **pinpoints** features whose curated weights diverge from measured signal
(LDL, linear-BMI) — the input to ablation-guided re-weighting (§4).

## 3e. Healthspan signal at 75+ and incremental input value (toward predictive-trajectory modeling)

*First steps of the documented "Toward Predictive Trajectory Modeling" extension (`docs/ROADMAP.md`),
now feasible via the NHANES mortality linkage. `incremental_value.py` + `feature_association.py
--min-age`. Aggregate, NCHS-cited. Survival proxy, single cohort.*

- **Incremental value (all ages):** age+sex alone discriminate mortality at AUC 0.872; adding the
  phenotype features reaches 0.906, and the first ~6 inputs (depression, smoking, functional mobility,
  bone health, self-rated health, eGFR) capture most of the gain. A sparse profile already carries
  most of this discrimination; the model uses all available features and gains confidence as more are added.
- **75+ stratum (the "healthspan" group):** age+sex discrimination falls to AUC 0.71 (age is far less
  informative once everyone is old), and **phenotype adds much more there** (→ ~0.84). The strongest
  age-independent protective signals at 75+ are **self-rated health, functional mobility, C-reactive
  protein (low inflammation), absence of prior CVD, and non-smoking** — robust to the early-death
  landmark guard.
- **Read:** these are precisely the **functional / inflammatory / behavioral centenarian-aligned
  traits**, and they carry *more* survival signal at 75+ than in the general population — i.e. the
  centenarian phenotype shows up as a measurable **healthspan signal in the oldest measurable group**.
  This motivates the predictive-trajectory model (time-to-event + interactions + aging-rate biomarkers).

## 3f. Evaluation against PhenoAge (clinical biological-age gold standard)

*`phenoage_comparison.py` on the subset of NHANES 2005–2010 with all nine PhenoAge inputs present
(N=7,964; 1,256 deaths) — a smaller, lab-complete cohort than §3b/§3e, so its baseline AUCs are not
directly comparable to those sections. PhenoAge computed per Levine et al. 2018 (Aging 10:573).
All-cause mortality; single national cohort; aggregate results (NCHS-cited).*

### Concurrent validity — does the phenotype track measured biological age?

The phenotype score correlates with **PhenoAge acceleration** (PhenoAge − chronological age) at
**Pearson −0.55, Spearman −0.56, age/sex-adjusted standardized β −0.57**: a higher score corresponds
to a biologically *younger* profile on the clinical gold standard. Per-feature associations with
PhenoAge acceleration are in the favourable direction, including features **not** part of PhenoAge —
self-rated health (β −0.24), functional mobility (−0.22), depression (−0.11), smoking (−0.11), diet
(−0.12) — establishing non-circular concurrent validity of the behavioral/self-report layer. LDL
("cholesterol") shows a positive coefficient, consistent with the inverse LDL–mortality association
reported in older adults and attributed here to reverse causation (declining LDL with frailty and
illness), not a protective effect of high LDL (Ravnskov et al., BMJ Open 2016, PMID 27292972; see §3d).

### Mortality discrimination and incremental value (held-out, 70/30)

Logistic regression predicting all-cause mortality. Rows 2–3 are **parallel alternatives** (PhenoAge
acceleration *vs.* the phenotype score, each added to the age/sex baseline — the head-to-head); rows
4–5 **add a phenotype feature block** on top of PhenoAge acceleration (the incremental test). Not a
cumulative sequence. The two feature blocks are:

- **All self-report features (17):** smoking, alcohol, diet, sleep, physical-activity frequency,
  depression, self-rated health, functional mobility, family/partnership, body-mass-index band, waist
  band, diabetes, hypertension, cholesterol, cardiovascular event, cancer history, bone health.
- **All non-PhenoAge features (22):** the 17 self-report items above plus the measured markers that
  are not PhenoAge inputs — HDL, triglycerides, LDL ("cholesterol"), BMI, HbA1c. The PhenoAge inputs
  glucose, C-reactive protein, and creatinine/eGFR are **excluded** to keep the test non-circular.

| logistic model (covariates) | held-out mortality AUC |
|---|---:|
| age, sex (baseline) | 0.874 |
| baseline + PhenoAge acceleration | 0.899 |
| baseline + phenotype score (single composite predictor) | 0.887 |
| baseline + PhenoAge acceleration + all self-report features (17) | 0.910 |
| baseline + PhenoAge acceleration + all non-PhenoAge features (22) | 0.910 |

- As a single age/sex-adjusted predictor, the composite phenotype score (0.887) approaches PhenoAge
  acceleration (0.899).
- **Incremental value:** entering a phenotype feature block as covariates alongside PhenoAge
  acceleration raises held-out AUC by **+0.011** (0.899 → 0.910). The increment is consistent across
  both block definitions (all self-report features +0.0109; all non-PhenoAge features +0.0115).
- PhenoAge, trained directly on NHANES mortality, is the stronger single clinical predictor; the
  phenotype panel is complementary to it.

Next: confidence intervals on the increment (DeLong / bootstrap); replication in an independent cohort.

## 4. Sequencing

1. **Data-derived feature shapes + provenance labels.** Replace *imposed* mapper shapes with shapes
   **estimated from outcome data** where it exists (e.g. nonparametric BMI→mortality by band to test
   whether the U-shape holds; age-stratified LDL to handle the late-life paradox), each tagged
   `data_derived` / `literature` / `reasoned`. Use causal safeguards (landmarking, age strata, and —
   from aggregate GWAS — Mendelian-randomization where feasible) so we do not learn confounded
   artifacts (e.g. "low LDL is bad"). Goal: no shape imposed silently.
2. Source a nonagenarian reference set (closes the largest gap; calibrates the missing NB class).
3. Calibrate NB likelihoods from labelled per-class feature distributions → lift
   `calibration` from `heuristic_pending` to `calibrated`.
4. Ablation-guided re-weighting: reconcile curated weights with measured per-feature association (§3d).
5. Subgroup + temporal + external validation; distribution + missingness suites.
6. Promote results into `MODEL_CARD.md` §10 and gate public claims on the acceptance gates above.
