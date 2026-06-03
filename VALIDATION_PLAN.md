# Validation Plan — Centenarian Longevity Phenotype Model

*Status: planned. Nothing in this document has been executed yet; the model is **not yet validated**
(see `MODEL_CARD.md` §10). This plan defines how validation will be done and what evidence is
required before any "validated" claim can be made.*

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

## 4. Sequencing

1. Source a nonagenarian reference set (closes the largest gap; calibrates the missing NB class).
2. Calibrate NB likelihoods from labelled per-class feature distributions → lift
   `calibration` from `heuristic_pending` to `calibrated`.
3. Run distribution + ablation + missingness suites on NHANES (+ mortality linkage).
4. Subgroup + temporal + external validation.
5. Promote results into `MODEL_CARD.md` §10 and gate public claims on the acceptance gates above.
