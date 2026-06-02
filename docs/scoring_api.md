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
```

- **`answers`** — maps a question `id` to the **index** of the chosen option (0-based, in listed order).
- **`clinical`** (Layer 3 only) — maps a measured feature (biomarker / disease flag / genomic variant /
  methylation clock) to an **alignment in `[0, 1]`** that the clinical/app layer computes from the raw
  value or genotype against the feature's reference. The engine only *weights* these; value→alignment
  mapping is the caller's responsibility (keeps invented reference math out of the scorer).

## Response (JSON-serializable dict)

| field | meaning |
|---|---|
| `score_pct` | similarity to verified centenarians, 0–100 |
| `ci_lower_pct`, `ci_upper_pct` | 95% interval (from weighted alignment dispersion) |
| `completeness_pct` / `confidence_pct` | model confidence in the estimate (L1 30 · L2 50 · L3 80). Same construct, rising confidence |
| `narrative` | human-readable one-liner |
| `subscores` | per-feature alignment ×100 |
| `pulling_up`, `pulling_down` | top features above / below the mean |
| `evidence_basis_pct` | share of the score by provenance `basis` (e.g. `measured`, `documented_positive`, `genomic`) |
| `gwas_corroborated_weight_share_pct` | genetic weight share (0 at L1/L2; >0 at L3) |
| `superseded_by_l3` | L2 self-report questions dropped because a deeper L3 measurement was supplied (deepest-layer-wins dedup) |
| `answered` | number of features scored |
| `layers_included` | which layers contributed |
| `model_version` | tier model versions used |

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
