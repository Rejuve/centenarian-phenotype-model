# Fetching mortality + nonagenarian data for validation

The validation harness (`scripts/validation/`) needs a survival outcome to calibrate the
phenotype → survival mapping. The lowest-effort, fully-open source is the **NHANES Public-use Linked
Mortality File (LMF)** — we already hold the NHANES survey data, so this just adds the outcome.

## 1. NHANES Public-use Linked Mortality File (open; no application)

- **Landing page:** https://www.cdc.gov/nchs/data-linkage/mortality-public.htm
- **Direct files:** https://ftp.cdc.gov/pub/Health_Statistics/NCHS/datalinkage/linked_mortality/
  - For the 2017–2018 cycle we score, fetch `NHANES_2017_2018_MORT_2019_PUBLIC.dat`.
  - (Each NHANES cycle has its own `.dat`; all share one record layout.)
- **License / DUC:** statistical reporting & analysis only; **no re-identification**; **do not link
  with other individually-identifiable data**. Cite NCHS (doi:10.15620/cdc:117142 for continuous
  NHANES). Vital status is real; some follow-up time / cause-of-death values are perturbed.
- **Key facts** (NCHS, *Public-use Linked Mortality Files*, May 2022):
  - Link key: `SEQN` (matches the NHANES survey files).
  - `ELIGSTAT`: 1=eligible, 2=under 18 (excluded), 3=ineligible.
  - `MORTSTAT`: 0=assumed alive, 1=assumed deceased (blank if not eligible).
  - `PERMTH_EXM`: person-months from exam to death/censor (follow-up through 2019-12-31).

### Run it

```bash
# 1. parse the fixed-width .dat -> csv (layout in parse_nhanes_lmf.py, verified against the NCHS PDF)
python scripts/validation/parse_nhanes_lmf.py \
    NHANES_2017_2018_MORT_2019_PUBLIC.dat data/processed/nhanes_lmf_2017_2018.csv

# 2. build the scored cohort (NHANES inputs -> model score) joined to the mortality outcome
python scripts/validation/build_nhanes_cohort.py --lmf data/processed/nhanes_lmf_2017_2018.csv

# 3. validate: AUC, fitted calibration (score [+age/sex] -> P(deceased)), reliability, subgroups
python scripts/validation/validate.py --cohort data/processed/nhanes_scored_cohort.csv \
    --score-col score_pct --outcome-col deceased --age-col age --sex-col sex \
    --out reports/validation_nhanes
```

What this validates: whether a higher phenotype score is associated with **lower all-cause
mortality** over follow-up, age/sex-adjusted. That is a *survival proxy*, not centenarian attainment
(few reach 100 within follow-up) — but it is the first real, defensible calibration of the
phenotype → survival signal. See `VALIDATION_PLAN.md`.

## 2. Closing the nonagenarian (90–99) gap — needed for four-class NB calibration

The corpus has no 90–99 subjects, so the Naive Bayes nonagenarian class is uncalibrated. Free options
(in ascending effort), all usable for research:

- **Health and Retirement Study (HRS)** — free registration: https://hrsdata.isr.umich.edu
  US 50+ panel with biomarkers, frailty, cognition, **the 90–99 band**, and linked mortality.
- **Gateway to Global Aging Data** — free registration: https://g2aging.org
  Harmonized HRS/ELSA/SHARE variables → cross-country subgroup validation with one schema.
- **MIDUS** — free registration: https://midus.wisc.edu (biomarkers + mortality).

Once a nonagenarian reference set is in hand, fit the NB likelihoods per class to flip
`naive_bayes.LIKELIHOOD_CALIBRATION` from `heuristic_pending` to `calibrated`.

## 3. External validation of the verified-centenarian registry

- **International Database on Longevity (IDL)** and **GRG** verified tables — research use; independent
  of LongeviQuest, for external validation of the registry.
