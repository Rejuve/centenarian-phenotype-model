# Data Strategy — toward a comprehensive, reputable long-life phenotype

*Proposed design, not yet built. Captures the plan for (a) a tiered source-quality ranking, (b)
filling the missing Layer-2 constructs with public data / supportable proxies, (c) nonagenarian and
public-figure centenarian data, (d) early-life factors, and (e) the ultimate goal: decomposing the
phenotype into behaviour/mindset vs genetics vs uncontrollable experience. Nothing here is a
commitment; it is the menu and the rationale.*

## 1. Tiered source-quality ranking

Attach a `source_tier` to every piece of evidence, orthogonal to the existing `basis`/evidence-grade
(A/B/C). Tier governs **what a source may be used for** (train / validate / describe / context):

| tier | sources | individual-level? | outcome-linked? | use |
|---|---|---|---|---|
| **S — research cohorts** | NHANES+Linked Mortality (no AI clause → full use); HRS/MIDUS (**aggregate-only for us**, §1a); ELSA/SHARE (screen first); UK Biobank/LLFS/NECS (application) | yes | yes (mortality/health) | **train + validate** — but only where the AI/LLM policy permits (§1a) |
| **A — validated longevity registries** | LongeviQuest, GRG, IDL (gerontology-validated 110+/100+) | yes | age verified, no contrast | validate age; descriptive |
| **B — curated structured biography** | Wikidata/Wikipedia verified 100+ public figures (politicians, artists, scientists) with documented traits | yes | no | **descriptive enrichment only** |
| **C — news / obituary / oral-history** | current corpus (10k academic, 2.8k news/obit) | yes (named) | no | descriptive; documentation-biased |
| **D — population / context** | WHO, UN WPP, HMD, GWAS Catalog summary stats | aggregate | n/a | context, priors, baselines |

Key rule: **only Tier S can validate survival or train survival weights**; Tiers A–C describe *what
long-lived people look like* (trait frequencies, co-occurrence) but cannot establish that a trait
*predicts* longevity (no comparison group, heavy selection bias). This keeps descriptive enrichment
from being mistaken for causal/predictive evidence.

## 1a. AI/LLM-use policy — a first-class access screen

Several cohorts now publish **AI/LLM-use policies** that must be screened *before* any acquisition,
because this repository is built and run by an **AI coding agent** — that counts as "LLM use."

**HRS (and MIDUS/ICPSR, same taxonomy) — the governing rule:**
- **Person-level (micro) data: prohibited with *any* LLM** — Type 1 (retains data, e.g. GPT/Llama),
  Type 2 (institution-licensed, no retention), and even Type 3 (isolated/offline). Not accepted for
  Public-Use *or* Restricted-Use. Feeding their microdata to an LLM counts as redistribution and
  violates the Data Use Agreement.
- **Permitted with LLMs/AI:** "public-facing documentation, codebooks, and study-level metadata,
  **including group or population estimates**." (Taxonomy credit: ICPSR / S. Karcher, Syracuse.)

**What this means for us (the compliant boundary):**
- ❌ We never run HRS/MIDUS **microdata** through this AI-operated pipeline (no `build_*_cohort` on it).
- ✅ We *may* use their **published aggregate/population estimates, codebooks, and metadata** — this is
  the basis of `docs/EVIDENCE_LONGEVITY_FACTORS.md`.
- ✅ We *may* use **open-source packages that distribute only aggregate insights** (coefficients/
  algorithms, no names/data) — a permitted population-level artifact (see §1b).
- 🔁 Microdata validation (if ever needed) is a **human + standard-package** job done *outside* this
  environment, returning only aggregate artifacts (the shape of `survival_calibration.yaml`).

Screening status of candidate sources: **NHANES/NCHS** — no AI/LLM clause → full pipeline use (proven).
**HRS, MIDUS** — aggregate/metadata-only for us. **ELSA, SHARE** — screen each before use (TBD).

## 1b. Open-source aggregate-coefficient packages (permitted, high value)

Packages that ship the *insight* (model coefficients / algorithms) derived from cohorts but containing
**no microdata** are population-level artifacts — usable here, and they often save reimplementation:

| package | provides | use |
|---|---|---|
| `methylclock`, `dnaMethyAge` (R) | DNAm clock coefficients (Horvath/Hannum/PhenoAge/…); GrimAge restricted | operationalize Tier-3 epigenetic clocks (`clocks.py`) |
| `BioAge` (R, Kwon & Crimmins) | Klemera-Doubal biological age + clinical PhenoAge from routine labs | a clinical-chemistry "clock" feature |
| published risk equations (ASCVD, SCORE2, Framingham, CKD-EPI) | open coefficient tables | cardiovascular / kidney sub-scores (CKD-EPI already used) |
| frailty-index algorithms (deficit accumulation) | computation rule | functional-age feature |

These are aggregate coefficients (like the clock references already cited in `clocks.py`), not data —
verify each package's own licence, but none requires cohort microdata.

## 2. Filling the missing Layer-2 constructs

NHANES covers ~15 of 31; the gaps are psychosocial/purpose. Best public fills (all Tier S):

| construct | source | variable / proxy |
|---|---|---|
| social connectedness | HRS/ELSA/SHARE psychosocial; NHANES SSQ (2005-06 only) | social participation, loneliness (UCLA-3) |
| purpose / meaning | HRS Leave-Behind, ELSA | Ryff purpose-in-life scale |
| cognitive engagement | HRS, ELSA | activities inventory; cognitive battery |
| faith / religion | HRS religiosity module | attendance, importance |
| diet (objective) | NHANES dietary recall (DR1T*) | compute **Healthy Eating Index (HEI-2015)** — a supportable proxy stronger than self-rating |
| physical activity (objective) | NHANES accelerometry (PAXMIN, 2003-06 / 2011-14) | objective MVPA minutes |

**Supportable proxies** (when a direct measure is absent) should be (i) documented, (ii) validated
against the construct in literature, (iii) tagged with a lower evidence grade, and (iv) never
silently substituted — same discipline as the clinical mappers.

## 3. Nonagenarian (90–99) data — the four-class NB gap

The corpus has no 90–99 subjects. Caveat: **NHANES public-use top-codes age at 80** (≥80 → 80), so
NHANES cannot supply the 90–99 band directly. Better sources:
- **HRS / ELSA / SHARE** — longitudinal, include 90–99 with biomarkers + mortality (Tier S).
- **The 90+ Study** (UC Irvine), **New England Centenarian Study** offspring — oldest-old (restricted).
- **Gateway to Global Aging** — harmonized HRS/ELSA/SHARE for cross-country 90–99 + subgroup fairness.

Acquiring a 90–99 reference set is the prerequisite to flip the Naive Bayes `LIKELIHOOD_CALIBRATION`
from `heuristic_pending` to `calibrated`.

## 4. Public-figure centenarians (your idea) — yes, with guardrails

Querying **Wikidata** (SPARQL, CC0) for humans with age-at-death ≥100 or living age ≥100, plus
occupation/nationality/birth-death, would yield thousands of named 100+ individuals beyond the news
corpus — the same *class* as obituaries but broader and machine-structured.

- **Useful for:** enriching the **descriptive** phenotype and trait co-occurrence (Tier B), reducing
  the "only remarkable obituaries" slice, adding geographic/occupational breadth.
- **Not useful for:** survival validation or training weights — public figures carry strong **fame
  selection bias** and have **no comparison group**; trait/habit data is anecdotal and sparse.
- **Guardrails:** Wikidata ages are **not gerontology-validated** → cross-check against LongeviQuest/
  GRG/IDL where possible and flag `age_validation: unverified`; deduplicate against the existing
  registry; store occupation to model (and adjust for) the fame bias.

Verdict: worth scraping as a Tier-B descriptive layer with an explicit age-validation flag; keep it
out of the survival-validation path.

## 5. Early-life factors (childhood diagnoses, trauma / ACEs)

A high-value, under-explored axis. Sources:
- **HRS Life History** / **ELSA life-history** modules — childhood health, SES, adversity (Tier S,
  outcome-linked → can actually estimate how much early life matters).
- **BRFSS ACE module** — ACE score + adult health (population, not longitudinal to 100).
- Birth-cohort studies (Dunedin, 1946 British cohort) — deep but restricted.

Add an **early-life / life-course domain** to the phenotype decomposition (childhood illness,
adversity score, early-life SES). With an outcome-linked cohort carrying these, we can estimate their
association with later biological age / mortality — directly answering "how much does it matter."

## 6. The ultimate goal — variance decomposition

Decompose the long-life phenotype into three blocks and quantify each:
1. **Modifiable** — behaviour + mindset (lifestyle, psychosocial, diet, activity).
2. **Genetic** — heritability ~20–50%, FOXO3/APOE/etc. (rises at extreme ages).
3. **Uncontrollable / stochastic** — early-life adversity & disease, injury, environment, chance.

Method (extends the existing feature-class ablation): in an outcome-linked cohort carrying all three
blocks (UK Biobank is the natural fit; HRS partially), fit a **block-wise variance partition**
(hierarchical partitioning / commonality analysis, or nested models) and report each block's
contribution to explained variance in lifespan/healthspan, plus their overlap. The model already
exposes interpretive `domain_scores` and per-feature-class ablation — this is the formalisation.

Output target: a defensible statement like "in this cohort, modifiable behaviour explains ~X%,
genetics ~Y%, and uncontrollable early-life/stochastic factors ~Z% of the explainable variance in
[healthspan / survival], with overlap W%" — with all the usual caveats (cohort-specific, explained-
not-total variance, associational).

## 7. Sequencing (suggested)

1. Acquire HRS (Tier S) → fills psychosocial constructs + 90–99 band + early-life (HRS Life History)
   in one cohort; enables NB calibration and the first variance decomposition.
2. Add NHANES HEI (diet) + accelerometry (activity) as objective proxies (low effort, data in hand).
3. Scrape Wikidata 100+ as a Tier-B descriptive layer (age-validation flagged).
4. Add the early-life/life-course domain; extend ablation to a 3-block variance partition.
5. UK Biobank (application) for the definitive multi-omic + early-life + outcome decomposition.
