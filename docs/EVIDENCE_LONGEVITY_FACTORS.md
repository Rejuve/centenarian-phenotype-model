# Evidence — longevity/healthspan factors (curated, cited)

*Compliant, aggregate-only literature backbone for the model's domains — especially the psychosocial
constructs NHANES does not measure, plus nonagenarian-cohort findings. Every entry is a **published
group/population-level estimate** (meta-analysis or cohort result), never microdata. This satisfies
the HRS/ICPSR AI-use rule (population estimates + documentation are permitted; person-level data is
not — see `docs/DATA_STRATEGY.md`). Seed list; expand via the academic scrapers.*

Columns: factor → strongest published effect → source (tier S = research-cohort/meta-analysis) →
evidence grade → how it maps into the model.

## Psychosocial domains (the gap NHANES can't fill)

| factor | published effect (all-cause mortality unless noted) | source | grade | model mapping |
|---|---|---|---|---|
| Social relationships (strength) | **OR 1.50** (95% CI 1.42–1.59) greater survival with stronger ties; 148 studies, n=308,849 | Holt-Lunstad, Smith & Layton 2010, *PLoS Med* 7(7):e1000316 (PMID 20668659) | A (meta) | `q_social_friends`, `q_social_community`, `q_family_*` weights |
| Social isolation / loneliness / living alone | **OR 1.29 / 1.26 / 1.32** increased mortality; n>3.4M | Holt-Lunstad et al. 2015, *Perspect Psychol Sci* 10(2):227–237 (PMID 25910392) | A (meta) | corroborates social/family domain; supports a future loneliness item |
| Purpose in life | pooled **RR 0.83** (0.75–0.90) lower mortality; 10 studies, n=136,265 | Cohen, Bavishi & Rozanski 2016, *Psychosom Med* (PMID 26630073) | A (meta) | `q_purpose_sense`, `q_purpose_engagement` weights |
| Purpose in life (HRS-specific) | lowest vs highest purpose **HR 2.43** (1.57–3.75), adults >50 | Alimujiang et al. 2019, *JAMA Netw Open* (PMC6632139) | B (single cohort) | purpose domain; HRS *aggregate* result (no microdata) |

## Nonagenarian / oldest-old cohorts (the 90–99 band the corpus lacks)

| finding | source | grade | model mapping |
|---|---|---|---|
| Moderate alcohol & coffee, and even ~15 min/day activity, associate with longer survival in the oldest-old; **being overweight in one's 70s associated with longer life** (late-life low BMI adverse); supplements no benefit | The 90+ Study (Kawas, UCI MIND), ~1,800 nonagenarians | B (cohort, descriptive) | corroborates U-shaped/late-life BMI (`body_mass_index`), measured-moderate-alcohol (`q_alcohol`), activity-regularity-not-intensity (`q_pa_*`) |
| Cohort of the oldest old (health/function/living conditions), successful-aging prevalence at 90+ | Vitality 90+ Study, Tampere (PMC3479972; PMC9906174) | B (cohort) | nonagenarian reference framing; functional-preservation domain |

*Note:* these are **descriptive** oldest-old findings (no comparison group / selection into survival),
so they corroborate direction and weighting but are not used to *train* survival models. The
calibrated survival signal remains the NHANES mortality work (`VALIDATION_PLAN.md` §3b–3c).

## Cross-references to our own validation (already in-repo)

- Self-rated health and depression (PHQ-9) as mortality predictors are **directly confirmed in our
  NHANES 1999–2016 run** (`VALIDATION_PLAN.md` §3b) — no external HR needed here.
- Biological-age acceleration / pace as mortality predictors: Marioni 2015, Levine 2018 (PhenoAge),
  Lu 2019 (GrimAge), Belsky 2022 (DunedinPACE) — already cited in `clocks.py` / `METHODS.md`.

## How this feeds the model (compliant path)

1. These aggregate effects **justify and sanity-check the weights** of the social/family/purpose
   domains (currently set from the news corpus) — flagged for a weight review, not auto-applied.
2. They support **adding a loneliness/social-isolation item** to Tier 2 (strong, consistent signal).
3. Open-source **aggregate-coefficient packages** (e.g. `methylclock`/`dnaMethyAge` for DNAm clocks,
   `BioAge` for KDM/PhenoAge) may supply algorithm coefficients — population-level artifacts, no
   microdata — to operationalize Tier-3 clocks (see `docs/DATA_STRATEGY.md`).
