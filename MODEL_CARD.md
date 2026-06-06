# Model Card — Centenarian Longevity Phenotype Model

*Version 0.2.4 · model artifacts: tier1 v1.2, tier2 v1.1, tier3 v1.4 · last updated 2026-06-05.*

This card states plainly **what is implemented now, what is validated now, what is planned, and what
is not safe to claim**. It supersedes `docs/model_card_stub.md`.

---

## 1. Overview

- **Name:** Centenarian Longevity Phenotype Model (the score it produces: **Exceptional Longevity
  Concordance, ELC**).
- **Primary endpoint — Exceptional Longevity Concordance (ELC):** how closely a profile matches the
  multi-domain pattern of people who reach exceptional age in good health — scored on **age attained** and
  **self-rated/functional good health** (see §4). Output: "this profile is *X%* concordant with verified
  exceptional healthy longevity." Lower biological age and a slower pace of ageing are expected correlates
  of a high score.
- **Deployed scoring method (v1):** **evidence-weighted alignment** of per-feature signal (each
  feature → alignment in [0,1]; score = evidence-weighted mean). This is the user-facing number.
- **Experimental probabilistic layer (research-only, NOT a core output):** a four-class Naive Bayes
  posterior (general population / nonagenarian 90–99 / centenarian 100–109 / supercentenarian 110+).
  The math is implemented and tested, but the likelihoods are `calibration: "heuristic_pending"`:
  the class centroids are **declared monotone assumptions, not estimated from labelled per-class
  feature distributions**; there is **no 90–99 training data** (corpus age-floored at 100); and the
  centenarian-vs-supercentenarian split is not empirically delineated. It is **suppressed for sparse
  inputs** (`< 4` scored features) and is **not surfaced by the public API**. Treat as ordinal
  resemblance only, never as calibrated probability (see §7, §8, and the rebuild plan in §10).
- **Tiers (compounding; boundary = necessity of a biospecimen/assay, encoded per feature as an
  `access` tag):**
  - Tier 1 — 12-question behavioral teaser.
  - Tier 2 — standalone 32-item app survey (19 NHANES-aligned behavioral incl. loneliness + 13
    self-report clinical/health) **plus non-invasive measured features** (`access: anthropometric` —
    grip strength, BMI, calf, plus waist/BP; free/consumer-obtainable, assumed true for insights).
  - Tier 3 — Tier 2 + features needing a biospecimen/assay (`access: lab|genomic|epigenetic|microbiome`):
    13 lab biomarkers, 21 scored genomic variants (with an 80-variant direction-resolved reserve
    catalogue, not scored live) + open
    longevity polygenic scores (PGS Catalog), DNA-methylation clocks + telomere length, and
    gut-microbiome signatures (literature-grounded). Disease *diagnoses*
    are self-report at Tier 2 (no confirmed-vs-reported field exists in the data); Tier 3 does not
    re-score them but measures the underlying state (glucose/HbA1c, eGFR, CRP).
  - **Intended Tier-3 use:** the lab/molecular panel indicates whether a profile is on a trajectory
    consistent with exceptional, healthy longevity (cross-sectional mortality association validated).
    Repeated-measures use to evaluate whether an intervention shifts that trajectory is a future
    direction, not a current claim.

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

**Primary endpoint — Exceptional Longevity Concordance (ELC).** ELC measures how closely a profile
matches the multi-domain pattern of people who **reach exceptional age while functioning and rating
themselves in good health**. Two literal, outcome-based endpoints:
- **Reaching a longevity threshold** — attaining an age that is *exceptional relative to the person's own
  population*: beyond the life expectancy for their era, region and sex (HMD life-table anchor), set at the
  **upper tail** rather than merely above median — with absolute waypoints of **≥90 → 100+** toward the
  human limit for interpretability. This is a *threshold target*: ELC scores concordance with reaching it
  and produces no age estimate — there is no age regression and no biological-age output.
- **Lived-well at that age** — the person's own assessment that life is good/satisfying (self-rated health
  is among the strongest mortality signals in our own cohort, adj. coef −0.42), together with **functional
  independence**: independence in activities of daily living and instrumental ADL (shopping, cooking,
  finances, medication, transport), corroborated where measured by objective performance — gait speed
  ≥0.8 m/s and grip strength above the EWGSOP2 sex cut-offs (low: <27 kg men / <16 kg women).

"Concordance" is plain agreement with that demonstrated pattern (defined here to distinguish it from the
survival C-index). The endpoint is **joint** — a profile is concordant when it aligns with reaching
extreme age *and* doing so in good health.

A high-ELC profile will, as a natural consequence, tend to carry a lower biological age, a slower pace of
ageing, and fewer years lived in sickness. These are **expected molecular and temporal correlates of the
endpoint — supporting features and validation benchmarks**, while the target stays the lived outcome
(how long, how well). Anchoring on the lived outcome lets ELC recognise profiles that clock- or
diagnosis-based measures would miss: someone whose condition is managed well enough that it does not
constrain their function or satisfaction **scores high if they reach 90+ in good functional and subjective
health**. Such cases are treated as informative data on how a condition's biological impact varies across
individuals and management — the population-trained clocks predict the *average* outcome for a signature,
so a well-managed individual is a meaningful outlier to learn from.

Survivor/delayer/escaper subtypes and the interpretive `domain_scores` (cardiovascular, metabolic,
inflammatory, functional, cognitive, social, genetic, epigenetic, disease-escape) **enrich interpretation
but never replace** the endpoint.

**Construct scope (the ELC differentiator).** ELC spans the modifiable **exposome** (lifestyle, behaviour,
function) *and* the **molecular** domains, and quantifies the **coupling** between them — expressed in
terms of what the underlying biology *does* (DNA-repair capacity, inflammatory tone, methylation fidelity,
xenobiotic clearance) rather than gene identity. A first pass (`scripts/validation/exposome_molecular_coupling.py`)
shows inflammatory/lipid markers are lifestyle-coupled while renal function is age-locked. This coupling,
and the **modifiable-headroom vs fixed-ceiling** decomposition it supports, is what makes ELC actionable —
the basis on which it can speak to *moving* a trajectory, not only rating it.

**Methodological note.** Self-rated health and functional measures are part of the concordance pattern by
design and remain inputs (removing them would break the construct). Where ELC makes a *predictive* claim
about the healthspan outcome specifically, we assess the **incremental contribution of the molecular and
lifestyle domains beyond** the concurrent self-report, rather than crediting self-report for predicting
itself.

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

**On the news/obituary corpus:** validated 100+ individuals are rare, so published profiles, obituaries
and oral histories are a genuinely valuable (and hard-to-source) record of personal testimony and
incidental clinical detail on extreme-age individuals. It is used deliberately but conservatively —
direction/presence only, provenance-tagged (`documented_positive` vs `neutral_context`/`external_evidence`),
and **absence of a trait is scored as neutral, never as measured depletion** — to use the signal without
importing narrative selection bias as if it were measured prevalence.

Backbone: ~18,100 academic abstracts (incl. a foundational aging-biology backbone — hallmarks of
aging, geroscience, compression-of-morbidity) + 2,788 news/profile articles + validated
supercentenarian registry (LongeviQuest, 3,924) + NHANES/WHO/UN WPP/HMD/GWAS reference datasets. Full registry:
`data/processed/source_registry.csv` and `data/sources.md`; methodology in `METHODS.md` §2–§3.

## 6. Evidence grades & provenance

**Tier-3 alias:** the Tier-3 `cholesterol` feature is **LDL-directional** (lower value → higher
alignment, per NCEP ATP III); `ldl_cholesterol` is accepted as an explicit alias for it
(`CLINICAL_ALIASES`), so a supplied `ldl_cholesterol` scores against the `cholesterol` reference. HDL is
a separate feature (`hdl_cholesterol`, higher → favourable).

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
both sexes). The compounding tiers discriminate as: **Tier 2 (self-report + anthropometric) AUC→survival 0.655 →
Tier 3 (+ lab biomarkers) 0.686** (age/sex-adjusted score weight −0.333 → −0.410); the lab/molecular
layer adds over self-report.

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

- **Package** `__version__` (currently 0.2.4) + per-tier model `version` fields stamped into every
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
