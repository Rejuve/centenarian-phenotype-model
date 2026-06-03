# Reproducibility entry points. See README "Reproducibility & release".
.PHONY: install test lint build manifest manifest-check validate longevity-baselines clean

install:            ## editable install with test + api extras
	pip install -e ".[test,api]"

test:               ## run the test suite
	python -m pytest -q

lint:               ## ruff (package + validation harness + tests; config in pyproject)
	python -m ruff check

build:              ## build the wheel (bundles model YAMLs as package data)
	python -m build --wheel

manifest:           ## (re)write the bundled model-artifact checksum manifest
	python scripts/make_manifest.py

manifest-check:     ## verify bundled artifacts match the manifest (deterministic-artifact gate)
	python scripts/make_manifest.py --check

longevity-baselines: ## rebuild HMD survival baselines (needs data/raw/datasets/hmd_life_tables.csv)
	python scripts/pipeline/step_g_longevity_baselines.py

validate:           ## harness self-test on a synthetic cohort (no data needed)
	python scripts/validation/validate.py --synthetic 4000 --out reports/validation_synthetic

clean:              ## remove build/test caches
	rm -rf build dist *.egg-info .pytest_cache && find . -name __pycache__ -type d -prune -exec rm -rf {} +
