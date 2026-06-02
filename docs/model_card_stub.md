# Model Card (stub) — superseded

> **This stub is superseded by the complete [`MODEL_CARD.md`](../MODEL_CARD.md) at the repo root.**
> The full card states what is implemented now, validated now, planned, and not-yet-safe-to-claim,
> and includes intended/non-intended use, endpoint definition, evidence grades, bias risks,
> known failure modes, regulatory disclaimer, and versioning/update policy. The historical seed
> notes below are retained for provenance only.

---

*Seed document (historical). Limitations and parameters accumulated here as the model was built.*

## Overview
- **Name:** Centenarian Longevity Phenotype Model
- **Type:** Naive Bayes classifier over four age-stratified reference classes (general population, nonagenarian 90–99, centenarian 100–109, supercentenarian 110+).
- **Output:** a **percentage phenotype-similarity score** — "this profile is *X%* similar to verified centenarians" — with a 95% confidence interval and per-feature subscores.
- **Tiers:** Tier 1 — 12-question behavioral teaser quiz across 11 domains, the ad/funnel entry point (`models/tier1_model.yaml`); Tier 2 — a **standalone ~31-item mobile app survey**: 18 NHANES-aligned behavioral questions (re-asked at depth, mapped to the top-ranked centenarian features) + 13 self-report clinical/health items; the L1 teaser does **not** carry over — L2 **re-captures every variable fresh** at finer granularity (`tier2_model.yaml`); Tier 3 — Tier 2 + blood biomarkers, 21 scored genomic variants (from a 508-variant curated catalogue), DNA-methylation clocks + telomere length, and microbiome (pending) (`tier3_model.yaml`).

## Intended use
- Educational and self-assessment context: surface how an individual's lifestyle/biomarker profile aligns with phenotypic patterns observed in people who reach 100+.
- **Not** a diagnostic, prognostic, or actuarial tool.

## Out of scope / explicit non-claims
- **Not a lifespan predictor.** The model does not estimate age at death or probability of reaching a given age.
- No individual medical advice; population-level associations only.

## Data
See `METHODS.md` §2 and `data/sources.md`. Backbone: 10,105 academic abstracts + 2,788 news/profile articles + validated supercentenarian registry (LongeviQuest, 3,924) + NHANES/WHO/UN/HMD/GWAS reference datasets.

## Scoring engine & provenance
Scored by `scripts/pipeline/step_f_scoring.py` (`score_profile`): an evidence-weighted mean of per-feature alignment (0–1), expressed as a % similarity with a 95% interval and per-feature subscores. Every option/feature carries a **`basis`** tag recording the provenance of its alignment value — `measured` (Step-D centenarian-vs-population ratio), `academic_corroborated`, `documented_positive`, `reasoned_gradient`, `neutral_context`, `external_evidence`, `clinical_literature`, `heritability`, `disease_escape`, `epigenetic`, `genomic` — and every result reports **`evidence_basis_pct`**, the share of the score resting on each basis. This keeps scores mapped to data reality rather than authoring judgment (e.g. only ~8% of a typical Layer-1 score is `measured` gold; the rest is documented-presence signal and disclosed reasoning).

Key scoring rules:
- **`gwas_corroborated` weight = 0.00 at Layers 1–2**, reintroduced at **Layer 3** (additive ~0.15 bonus to corroborated features; up to ~50% weight share when a full genomic panel is supplied). It is a known limitation, not a finding, that genetics is under-weighted at the behavioral layers — see below.
- **Physical activity is scored on regularity, not intensity**, and **diet is near-flat** (case corpus is context_dependent; only a mild plant-forward/moderation lean from the academic corpus) — both reflect what the data does and does not distinguish.
- **Body composition is U-shaped** (obesity *and* late-life underweight/weight-loss both adverse). **Note: BMI is a crude proxy. Waist circumference and body composition (muscle/fat mass) are stronger signals and are captured at Layer 2 when self-reported by the user.** Of these, `waist_circumference` is present in the corpus and scored at Layer 2 (self-report). `muscle_mass`, `fat_mass`, and `hip_circumference` are **not in the current corpus and are therefore not features** — the Layer-2 schema is designed to ingest them if/when sourced (e.g. UK Biobank body composition), and nothing is fabricated in the interim.
- **Deepest layer wins:** Layer-2 self-report items are coarse versions of Layer-3 measured constructs; in a combined run the measured value supersedes the self-report (construct-level dedup, reported via `superseded_by_l3`).

The Layer-3 genomic panel is curated from `gwas_longevity.csv` into `data/processed/genomic_panel_curated.csv` (508 genome-wide-significant longevity variants across 426 genes; 80 with interpretable effect direction, of which 21 are scored). Candidate corroboration against our own centenarian-vs-control WGS (`cent_WGS.txt`) currently matches only **2 variants by position** — this is a **genome-build mismatch (a pipeline / data-engineering issue, resolved by lifting `cent_WGS.txt` to GRCh38), not a scientific error**. The **21 scored variants remain fully valid**: their effect directions are read from the GWAS Catalog (`gwas_longevity.csv`), independent of the WGS check, which provides optional confirmation rather than primary evidence. (Small centenarian n in the WGS — ~27 — further limits it to candidate corroboration, not discovery.) DNA-methylation clocks (Horvath, Hannum, SkinBlood, PhenoAge, GrimAge, DunedinPACE) and telomere length sit at Layer 3; `nhanes_methylation.csv` provides a population baseline making epigenetic age acceleration **gold-eligible** (the quantified centenarian delta is deferred, not invented).

## Known limitations (carried from `docs/audit_report.md`)
- Academic corpus is abstract-only; ~half of control-group prevalence relies on NHANES/WHO fallback.
- Nonagenarian class is unpopulated from the current corpus (subject-age floor at 100).
- TidyTuesday registry subset is male-skewed (non-representative); down-weighted relative to LongeviQuest.
- Several biomarkers remain Grade C (values in main-text tables, not abstracts).
- Naive Bayes assumes feature independence — a known simplification; interaction modeling is planned (see `docs/ROADMAP.md`).
- NHANES has too few subjects aged 95+ to estimate centenarian-class biomarker distributions directly; literature + curation fill the gap.

## Evidence accumulation model

The three-layer model is designed so that **evidence accumulates as data is added** — each layer adds signal; none replaces the others.

**The layers measure the *same* similarity construct at *rising confidence*, not different similarities.** `completeness_pct` (exposed as `confidence_pct` in the score output) is the model's confidence in the estimate: Layer 2 reports the similarity at ~50% confidence; Layer 3 reports the **same** similarity at ~80% confidence (higher). The **score** answers "how centenarian-like is this profile?"; the **confidence/completeness** answers "how sure are we?" — and each tier carries all of the previous tier's questions into its score, then adds deeper evidence on top.

| layer | inputs | score narrative | confidence_completeness |
|---|---|---|---|
| **Layer 1** | behavioral / lifestyle signal only (quiz) | "Your lifestyle shares X% similarity with verified centenarians" | **~30%** |
| **Layer 2** | Layer 1 + self-reported clinical (diabetes, hypertension, BMI, waist) + family history of longevity | adds self-reported clinical | **~50%** |
| **Layer 3** | Layer 2 + blood biomarkers + genomic variants (+ epigenetic, microbiome) | "Your lifestyle, blood, and genomic markers share X% similarity with verified centenarians statistically" | **~80%** |

**Grounding of the completeness percentages (heritability literature):**
- The heritability of human longevity is estimated at **~20–50%** of variance — e.g. Herskind et al. 1996 (Danish twins, ~0.23–0.33); Sebastiani & Perls 2012 (heritability rises at the most extreme ages); Ruby et al. 2018 (Ancestry/Calico — pedigree estimates revised downward to ~0.07–0.16 after correcting for assortative mating, but still non-zero and rising at extreme ages). The balance (~50–80%) is non-genetic: lifestyle, environment, and stochastic factors.
- Hence **Layer 1 (behavioral) ≈ 30%**: lifestyle/behavioral factors capture a large but partial share of modifiable longevity signal. **Layer 1+2 ≈ 50%**: adding self-reported clinical state. **Layer 1+2+3 ≈ 80%**: adding measured blood + genomics captures most *measurable* variance.
- **100% is theoretical** — even complete multi-omics cannot explain all longevity variance (stochastic and unmeasured environmental components remain).

**Genetic contribution is architecturally significant but currently under-represented in scoring.** Genetics is estimated at 20–50% of longevity variance, yet `gwas_corroborated` carries weight **0.00 in the Layer-1/2 behavioral score** — not because genetics matters less, but because (a) genetic factors are not scoreable from behavioral/self-report inputs, and (b) we currently have a **single GWAS source** (`gwas_longevity.csv`). This is a **known limitation, not a finding**. Genetic factors will increase their contribution proportionally as more GWAS sources and individual genomic data are integrated, and `gwas_corroborated` is reintroduced with appropriate weight in the **Layer 3** scoring (Step F).

Gene→biomarker pathways linking Layer-3 genomics to the Layer-3 blood panel (e.g. APOE→LDL cholesterol, TCF7L2→glucose, CETP→HDL, LPA→Lp(a)) are documented in `data/processed/gwas_biomarker_pathways.csv`, so a user's genomic result can inform interpretation of their blood panel and vice versa.

## Evidence grading
Biomarkers are graded A/B/C with cross-validation against NHANES and GWAS; pooled effects use stratified DerSimonian-Laird meta-analysis with a commensurability guardrail (odds ratios are never pooled with hazard ratios). See `METHODS.md` §3.4.

## Ethical & fairness considerations *(to be completed at Step F)*
- Geographic/ancestry representativeness of the corpus.
- Risk of misinterpretation as a lifespan prediction.
- Country exposomic adjustment and its assumptions (Blue Zone bonus is auditable configuration).
