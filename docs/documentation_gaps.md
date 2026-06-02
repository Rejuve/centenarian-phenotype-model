# DOCUMENTATION GAPS

*Generated 2026-06-01 (pre-Step-D audit). What top-level documentation exists vs. what a public/partnership-ready open-source repo needs.*

## Present

| file | status | notes |
|---|---|---|
| `README.md` | ✅ created 2026-06-01 | entry point: pitch, % similarity framing, quickstart, pipeline run order, data sources, doc links. |
| `METHODS.md` | ✅ created 2026-06-01 | formal third-person methods (replaces PROJECT_BRIEF.md): project statement, data sources, methodology, decisions, limitations, changelog. |
| `requirements.txt` | ✅ created 2026-06-01 | pinned direct deps + spaCy model note. |
| `LICENSE` | ✅ created 2026-06-01 | MIT, © 2026 Rejuve.AI. |
| `.gitignore` | ✅ created 2026-06-01 | excludes large raw/derived data, `_*` scratch, `*.bak`, `__pycache__`. |
| `data_dictionary.md` | ✅ | per-file schema for `data/processed/`. |
| `audit_report.md` | ✅ | living status document. |
| `source_registry.csv` | ✅ | formal dataset-source registry. |

## Still missing

| file | priority | why it matters | recommendation |
|---|---|---|---|
| **git repository** | 🔴 high | Project is **not yet version-controlled** (`git: false`). `.gitignore` is in place and ready. | `git init` and make the first commit. The `.gitignore` already excludes the ~600 MB of large data and scratch files. |
| **CONTRIBUTING.md** | 🟡 medium | Named for the "partnership discussed" with LongeviQuest and external collaborators. | Short doc: env setup, pipeline run order (link README), "run scripts from repo root", how to add a data source (→ update `source_registry.csv`). |
| **model card** | 🟡 medium (Phase 3) | The % similarity framing, evidence grades, and data-quality limitations must ship with the model. | Defer to Phase 3 (Step F+); stub now so limitations accumulate in one place. METHODS.md §5 is the seed. |

## Remaining quick win
1. `git init` + first commit (`.gitignore` already prevents a 600 MB+ accidental commit).
