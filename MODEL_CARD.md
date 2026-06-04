# Model Card — Centenarian Longevity Phenotype Model

*Version 0.2.2 · model artifacts: tier1 v1.2, tier2 v1.1, tier3 v1.2 · last updated 2026-06-04.*

This card states plainly **what is implemented now, what is validated now, what is planned, and what
is not safe to claim**. It supersedes `docs/model_card_stub.md`.

---

## 1. Overview

- **Name:** Centenarian Longevity Phenotype Model
- **Primary endpoint:** *similarity to verified centenarians* — people who **verifiably reached
  100+**. Output: "this profile is *X%* similar to verified centenarians."
- **Deployed scoring method (v1):** **evidence-weighted alignment** of per-feature signal (each
  feature → alignment in [0,1]; score = evidence-weighted mean). This is the user-facing number.
- **Derived probabilistic layer:** a genuine **four-class Naive Bayes posterior** (general
  population / nonagenarian 90–99 / centenarian 100–109 / supercentenarian 110+) computed on top of
  the same evidence. **The math is implemented and tested; the likelihoods are
  `calibration: "heuristic_pending"`** (declared monotone class centroids, not estimated from
  labelled per-class feature distributions — see §8 bias/limitations and §7 known failure modes).
- **Tiers (compounding; boundary = necessity of a biospecimen/assay, encoded per feature as an
  `access` tag):**
  - Tier 1 — 12-question behavioral teaser.
  - Tier 2 — standalone 32-item app survey (19 NHANES-aligned behavioral incl. loneliness + 13
    self-report clinical/health) **plus non-invasive measured features** (`access: anthropometric` —
    grip strength, BMI, calf, plus waist/BP; free/consumer-obtainable, assumed true for insights).
  - Tier 3 — Tier 2 + features needing a biospecimen/assay (`access: lab|genomic|epigenetic`): 14 lab
    biomarkers, 21 scored genomic variants (+ an 80-variant scoreable catalogue), DNA-methylation
    clocks + telomere length; microbiome pending. Disease *diagnoses* are self-report at Tier 2 (no
    confirmed-vs-reported field exists in the data); Tier 3 does not re-score them but measures the
    underlying state (glucose/HbA1c, eGFR, CRP).
  - **Intended Tier-3 use:** the lab/molecular panel, measured repeatedly, is a longevity-trajectory /
    therapeutic-efficacy instrument (cross-sectional mortality association validated; within-person
    sensitivity-to-change pending).

## 2. Intended use

- Educational / self-assessment: surface how an individual's lifestyle and biomarker profile aligns
  with phenotypic patterns observed in people who reach 100+.
- A funnel/product signal for the Rejuve tiered path (teaser → app survey → Pro biomarkers).
- Generating interpretable, modifiable-vs-non-modifiable drivers and a "next best data action."

## 3. NOT intended use (explicit non-claims)

- **Not a lifespan predictor.** Does not estimate age at death or probability of reaching a given age.
- **Not a diagnostic, prognostic, or actuarial tool.** No individual medical advice.
- Do **not** present the four-class posteriors as calibrated probabilities of *being* in a class —
  they are uncalibrated resemblance posteriors (see §7).
- Do **not** claim the model is "trained," "validated," or "clinically validated."

## 4. Endpoint definition

**Primary endpoint (now):** similarity to *verified* survival to 100+. Survivor/delayer/escaper
subtypes and the interpretive `domain_scores` (cardiovascular, metabolic, inflammatory, functional,
cognitive, social, genetic, epigenetic, disease-escape) **enrich interpretation but never replace**
the primary endpoint.

**Endpoint evolution (planned, in progress):** toward a **relative healthspan/longevity** statement —
whether a profile is consistent with *outliving the typical survival trajectory for the person's own
country and sex*, with less age-related decline and higher odds of reaching 100 **on their current
trajectory** (absent sudden lifestyle change/injury, and incorporating chronic-disease risk). The
unifying construct across ages is **reduced biological age at any chronological age** (clocks +
age/sex-adjusted markers), so the model need not always say "will reach 100" — it can say "this looks
younger/healthier than typical for your age and country."

This is split by evidence status (see `longevity.py` / `longevity_context`):
- **Validated anchor:** the population survival baseline by country × sex (HMD life tables — open
  demography, not modelled).
- **Calibration-pending:** the mapping from phenotype score → a personal survival/trajectory band.
  Converting the band into calibrated personal odds is the validation deliverable.

**Validation standards for the trajectory endpoint:**
- **Gold:** data from a person in a commonly-measured age range (≈60–75) followed to 100+, even if sparse.
- **Platinum:** longitudinal data from youth to 100+ (presently uncommon).
- Until those exist, we anchor on *reduced biological age at any age* + exposomic/lifestyle patterns
  and the validated demographic baseline.

## 5. Data & source registry

Backbone: ~18,100 academic abstracts (incl. a foundational aging-biology backbone — hallmarks of
aging, geroscience, compression-of-morbidity) + 2,788 news/profile articles + validated
supercentenarian registry (LongeviQuest, 3,924) + NHANES/WHO/UN WPP/HMD/GWAS reference datasets. Full registry:
`data/processed/source_registry.csv` and `data/sources.md`; methodology in `METHODS.md` §2–§3.

## 6. Evidence grades & provenance

Every option/feature carries a **`basis`** tag, and every result reports **`evidence_basis_pct`**
(share of the score by provenance) and **`evidence_confidence_pct`** (model depth × response
completeness × provenance quality). Bases, strongest→weakest: `measured` (Step-D
centenarian-vs-population ratio), `genomic`, `epigenetic`, `measured_clinical`, `heritability`,
`clinical_literature` / `disease_escape`, `academic_corroborated`, `documented_positive`,
`external_evidence`, `reasoned_gradient`, `neutral_context`. Biomarker references are graded A/B/C
with stratified DerSimonian-Laird pooling and a commensurability guardrail (ORs never pooled with
HRs). Tier-3 raw-value → alignment mappers cite established public cut-offs (NCEP ATP III, ADA, WHO,
ACC/AHA, AHA/CDC, EWGSOP2, KDIGO) and carry their own per-mapper evidence grade — see
`centenarian_phenotype/mappers.py` and `describe_mappers()`. Biological-age clocks are managed by an
extensible registry (`centenarian_phenotype/clocks.py`) that records each clock's tissue/sample,
platform/assay, availability (free_open / requires_coefficients / restricted), evidence grade, and
limitations, and **never mixes a clock into the score without a scoreable flag** (versioned
weighting); proteomic/metabolomic/microbiome clocks are registered but `pending`.

## 7. Known failure modes

- **Uncalibrated posteriors saturate.** With many features, the Naive Bayes softmax becomes sharply
  peaked (near 0/1). Treat `class_posteriors` as *ordinal resemblance*, not calibrated probability,
  until v2 calibration.
- **Nonagenarian class has no training data** (corpus subject age floored at 100), so the 90–99
  class is the weakest leg of the posterior.
- **Self-report tiers (1–2) are gameable** and subject to recall/social-desirability bias.
- **Garbage-in raw values**: Tier-3 mappers clamp out-of-range inputs and warn, but a wrong-unit
  value that lands *inside* the accepted range will score silently — verify units upstream.
- **Documentation bias** in the case corpus: absence of a trait among centenarians is scored as
  near-neutral, not measured depletion (see `basis: neutral_context`).

## 8. Bias risks, population coverage & limitations

- Academic corpus is abstract-only; ~half of control-group prevalence relies on NHANES/WHO fallback.
- Validated-supercentenarian registries are ~90% female and skew Western/high-income; geographic and
  ancestry representativeness is limited. Subgroup performance is **unmeasured** (see §10).
- TidyTuesday registry subset is male-skewed and down-weighted relative to LongeviQuest.
- Several biomarkers remain Grade C; NHANES has too few subjects aged 95+ to estimate centenarian-
  class biomarker distributions directly — literature + curation fill the gap.
- Naive Bayes assumes feature independence — a known simplification; correlated features
  (e.g. HDL/LDL/triglycerides) are effectively over-counted.
- Genetics is **architecturally under-weighted** at Layers 1–2 (weight 0.00) because it is not
  scoreable from behavioral input and the pipeline has a single GWAS source; reintroduced at Layer 3.

## 9. Clinical & regulatory disclaimer

This model is **not a medical device** and has **not** been evaluated by any regulator. Outputs are
population-level associations for educational use only and must not be used for diagnosis, treatment,
insurance/actuarial decisions, or any individual medical decision. **This is not medical advice.**

## 10. Validation status

**Preliminary signal only; not yet validated for any claim.** Pooled NHANES 1999–2016 linked mortality
(**N=53,255; 9,104 deaths; up to ~20-yr follow-up**) shows the *untrained* phenotype score is
associated with **lower all-cause mortality independent of age** (protective within every age band and
both sexes). The compounding tiers discriminate as: **Tier 2 (self-report) AUC→survival 0.660 →
Tier 3 (Tier 2 + measured) 0.692** (age/sex-adjusted score weight −0.318 → −0.439); self-report and
measured data are complementary.

Per-feature (age/sex-adjusted, reverse-causation landmark): self-report leaders are functional
mobility (−0.39), smoking (−0.36), self-rated health (−0.35); Tier-3 **lab biomarkers** CRP (−0.31),
WBC (−0.22), triglycerides (−0.19), eGFR (−0.19), telomere (−0.16), glucose, HbA1c, HDL are protective
and landmark-robust; the Tier-2 anthropometric grip strength (−0.17) likewise. BMI and LDL read null
for documented reasons (U-shape; the elderly LDL paradox). **DNA-methylation clocks** (NHANES DNAm
1999–2002, n=2,532) are the strongest signals — **GrimAge −0.65, DunedinPACE −0.47, PhenoAge −0.37**.
Against the clinical biological-age gold standard, the score shows **concurrent validity with PhenoAge**
(r −0.59) and adds **+0.02 AUC over PhenoAge + age + sex** (non-circular).

This is a **survival proxy, not centenarian attainment**, in a single US cohort, untrained and
unreplicated — encouraging but **not** a validated claim. A bundled **held-out** calibration
(`survival_calibration.yaml`; NHANES 1999–2016) maps the score to 10-year all-cause mortality
(out-of-sample AUC 0.896, ECE 0.020) and feeds `longevity_context.calibrated_mortality`. The genomic
layer is literature-grounded but **not** validated on linked individual-level mortality (needs an
external genotyped cohort). Trajectory-band calibration to *reaching specific ages*, within-person
sensitivity-to-change for the efficacy use, survey-design weighting, competing risks, and external
validation remain outstanding. Invariants are guarded by **91 unit tests**; the harness lives in
`scripts/validation/`. Full detail: [`VALIDATION_PLAN.md`](VALIDATION_PLAN.md) and
[`docs/TIER2_TIER3_EVALUATION.md`](docs/TIER2_TIER3_EVALUATION.md).

## 11. Versioning & update policy

- **Package** `__version__` (currently 0.2.2) + per-tier model `version` fields stamped into every
  result's `model_version`.
- Model YAML changes require a `version` bump and a passing `tests/` run (regression guard).
- Likelihood/mapper changes are versioned independently (`MAPPER_SET_VERSION`, NB
  `LIKELIHOOD_CALIBRATION`).
- Release artifacts should record: model version · data snapshot version · code version · changelog ·
  validation status (release process is **planned** — see `AUDIT_FIXES.md`).

## 12. Ethical & fairness considerations

Geographic/ancestry representativeness of the corpus is limited; risk of misinterpretation as a
lifespan prediction is mitigated by mandatory disclaimer language in every surface. The country
exposomic / Blue Zone adjustment is auditable configuration (specified, not yet wired into the
package).
