# Scoring API — `centenarian_phenotype`

The deployable scoring package. Dependency-light (`pyyaml` only); the three tier models are
bundled as package data, so it has **no dependency on the research pipeline or the `data/` tree**.

```bash
pip install -e .          # from repo root (uses pyproject.toml)
```

## Entry point

```python
from centenarian_phenotype import score

# Layer 1 — teaser quiz. answers: {tier1_question_id: chosen_option_index}
score(1, {"q_physical_activity": 0, "q_diet": 1, "q_smoking": 0, ...})

# Layer 2 — standalone app survey. answers: {tier2_question_id: option_index}
score(2, {"q_pa_frequency": 0, "q_diabetes": 0, "q_self_rated_health": 1, ...})

# Layer 3 — Layer 2 answers in full + measured clinical/genomic/epigenetic alignments (0..1)
score(3, l2_answers, clinical={"hdl_cholesterol": 0.9, "grimage_2019": 0.85, "rs2069837": 1.0})

# strict=True (default) rejects unknown IDs / out-of-range values (raises ValidationError -> 422).
# strict=False downgrades them to a structured `warnings` block and drops the bad inputs.
score(1, answers, strict=False)
```

- **`answers`** — maps a question `id` to the **index** of the chosen option (0-based, in listed order).
- **`clinical`** (Layer 3 only) — maps a measured feature to an **alignment in `[0, 1]`**. The engine
  only *weights* these. To go from a **raw value** (e.g. HDL = 62 mg/dL) to an alignment safely, use
  the versioned mappers instead of hand-rolling cut-offs:

  ```python
  from centenarian_phenotype.mappers import map_panel
  panel = map_panel({"hdl_cholesterol": 62, "triglycerides": 90, "glucose": 95}, sex="M", age=72)
  score(3, l2_answers, clinical=panel["clinical"])   # panel["report"] carries provenance + warnings
  ```

  Each mapper cites an established public reference (NCEP ATP III, ADA, WHO, ACC/AHA, AHA/CDC,
  EWGSOP2, KDIGO), declares units / accepted range / sex-age adjustment / evidence grade / version,
  returns `alignment=None` for missing inputs, and clamps + warns on out-of-physiological-range
  values. `describe_mappers()` returns the full catalogue.

### Scoring method

The **user-facing number is `evidence_weighted_similarity`** (also `score_pct` /
`total_similarity_score`): an evidence-weighted mean of per-feature alignment. The engine also
returns a genuine **four-class Naive Bayes posterior** as a *derived, calibration-pending* output
(`class_posteriors` over general/nonagenarian/centenarian/supercentenarian). See `MODEL_CARD.md`.

## Response (JSON-serializable dict)

| field | meaning |
|---|---|
| `score_pct` / `total_similarity_score` / `evidence_weighted_similarity` | similarity to verified centenarians, 0–100 (the user-facing number) |
| `ci_lower_pct`, `ci_upper_pct` | 95% interval (from weighted alignment dispersion) |
| `class_posteriors` | four-class Naive Bayes posterior (general/nonagenarian/centenarian/supercentenarian), sums to 1 |
| `centenarian_posterior`, `supercentenarian_posterior` | marginals from `class_posteriors` |
| `calibration` | `heuristic_pending` — the NB likelihoods are not yet data-calibrated (see MODEL_CARD) |
| `model_depth_pct` | tier-based depth (L1 30 · L2 50 · L3 80) — how deep the *tier* is |
| `response_completeness_pct` | actually-answered/scored items ÷ expected items for the tier |
| `evidence_confidence_pct` | model depth × response completeness × provenance quality |
| `usable_score` | bool — enough valid coverage to be meaningful (≥50% response & ≥3 items) |
| `completeness_pct` / `confidence_pct` | **back-compat aliases of `model_depth_pct`** |
| `domain_scores` | secondary interpretive domains (cardiovascular, metabolic, inflammatory, functional, cognitive, social, genetic, epigenetic, disease-escape) — explain *why*, never redefine the endpoint |
| `top_positive_drivers`, `top_negative_drivers` | strongest signed contributors |
| `modifiable_drivers`, `non_modifiable_context` | actionable vs fixed (genomic/family) drivers |
| `missing_high_value_inputs` | ranked inputs that would most raise confidence |
| `next_best_data_action` | one concrete suggestion derived from the above |
| `pro_unlock_opportunities` | Tier-3 upsell hints (empty at L3) |
| `narrative` | human-readable one-liner |
| `subscores` | per-feature alignment ×100 |
| `pulling_up`, `pulling_down` | top features above / below the mean |
| `evidence_basis_pct` | share of the score by provenance `basis` |
| `gwas_corroborated_weight_share_pct` | genetic weight share (0 at L1/L2; >0 at L3) |
| `superseded_by_l3` | L2 self-report questions dropped because a deeper L3 measurement was supplied (deepest-layer-wins dedup) |
| `answered` | number of features scored |
| `layers_included` | which layers contributed |
| `warnings` | structured `{unknown_inputs, ignored_inputs, invalid_inputs, missing_required_inputs, out_of_range_values}` |
| `model_version` | tier model versions used |

### Validation & errors

`score(..., strict=True)` (default) and the API raise **HTTP 422** with body
`{"error": "input validation failed", "report": {...}}` for: unknown question IDs, unknown clinical
features, option index out of range, clinical alignment outside `[0,1]`, non-integer indices, and
empty/insufficient answers. `strict=False` returns 200 and surfaces the same issues under `warnings`.

### CORS hardening

The public Layer-1 widget may default to `*`. **Deployments serving Layer 2 or 3 never default to
wildcard**: set `CENTENARIAN_CORS_ORIGINS` (comma-separated) or pass `cors_origins=` to `create_app`;
otherwise CORS defaults to deny (empty allow-list) and a warning is logged.

## Invariants (enforced by `tests/test_scoring.py`)

- Layer 1 range **25.9–97.5%**; Layer 2 within bounds; all scores ∈ [0, 100].
- `gwas_corroborated` weight share: **0% at L1, 0% at L2, >0% at L3**.
- Completeness/confidence ladder: **30 / 50 / 80**.
- **L3 carries all L2 questions** (`answered` = 31 + L3 features), `layers_included == [2, 3]`.
- **Deepest layer wins**: supplying a measured construct supersedes its L2 self-report.
- Every option has `alignment ∈ [0,1]` + a `basis`; `evidence_basis_pct` sums to ~100.

## Notes for maintainers

- The bundled `centenarian_phenotype/models/*.yaml` are **copies** of the canonical `models/*.yaml` at
  repo root (the pipeline's source of truth). Keep them in sync when a model is re-versioned; the
  `version` field flows into `model_version` in every result.
- Run `python -m pytest tests/` after any model edit — the suite is the regression guard.
