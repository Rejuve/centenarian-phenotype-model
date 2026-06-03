"""Step G — relative-longevity demographic baselines from Human Mortality Database life tables.

Reads `data/raw/datasets/hmd_life_tables.csv` (HMD, period life tables by country x sex x year) and
emits, for the **latest available year per country x sex**, a compact baseline of:

  * `ex60`, `ex65`           — remaining life expectancy at 60 / 65 (years)
  * `p_reach_90_from_65`     — P(survive to 90 | alive at 65)  = lx(90) / lx(65)
  * `p_reach_100_from_65`    — P(survive to 100 | alive at 65) = lx(100) / lx(65)
  * `p_reach_100_from_80`    — P(survive to 100 | alive at 80) = lx(100) / lx(80)
  * `quality_warning`        — HMD flagged data quality at any used age

These are **validated open demography** (no modelling): they are the population denominator that lets
the model express "longer than typical for your country/sex," and the survival anchor the phenotype
score will eventually be *calibrated against* (see VALIDATION_PLAN.md / MODEL_CARD §1, §10).

Outputs:
  * `data/processed/longevity_baselines.csv`                              (full, all countries)
  * `centenarian_phenotype/models/longevity_baselines.yaml`              (bundled package data)

Run from repo root:  python scripts/pipeline/step_g_longevity_baselines.py
"""
from __future__ import annotations

import csv
import os
from collections import defaultdict

import yaml

RAW = os.path.join("data", "raw", "datasets", "hmd_life_tables.csv")
OUT_CSV = os.path.join("data", "processed", "longevity_baselines.csv")
OUT_YAML = os.path.join("centenarian_phenotype", "models", "longevity_baselines.yaml")

# Friendlier names for HMD "(total)" series so the bundled table reads cleanly.
NAME_FIXUPS = {
    "Germany (total)": "Germany", "France (total)": "France",
    "United Kingdom (total)": "United Kingdom", "New Zealand (total)": "New Zealand",
}
CODE_FIXUPS = {"DEUTNP": "DEU", "FRATNP": "FRA", "GBR_NP": "GBR", "NZL_NP": "NZL"}


def _load():
    rows = []
    with open(RAW, encoding="utf-8", errors="replace") as f:
        for x in csv.DictReader(f):
            if x.get("age") and x.get("lx"):
                rows.append(x)
    return rows


def build():
    rows = _load()
    # latest year per (code, sex)
    latest = defaultdict(int)
    for x in rows:
        latest[(x["country_code"], x["sex"])] = max(latest[(x["country_code"], x["sex"])], int(x["year"]))
    # index lx/ex by (code, sex, year, age)
    lx = {}
    ex = {}
    warn = defaultdict(bool)
    for x in rows:
        key = (x["country_code"], x["sex"], int(x["year"]))
        try:
            age = round(float(x["age"]))
        except ValueError:
            continue
        lx[(key, age)] = float(x["lx"])
        ex[(key, age)] = x["ex"]
        if str(x.get("has_quality_warning", "")).lower() == "true":
            warn[key] = True

    out = []
    for (code, sex), yr in sorted(latest.items()):
        if sex not in ("female", "male", "both"):
            continue
        key = (code, sex, yr)

        def ratio(a, b):
            la, lb = lx.get((key, a)), lx.get((key, b))
            return round(la / lb, 5) if la is not None and lb else None

        name = next((r["country_name"] for r in rows if r["country_code"] == code), code)
        out.append({
            "country_code": CODE_FIXUPS.get(code, code),
            "country_name": NAME_FIXUPS.get(name, name),
            "sex": sex,
            "year": yr,
            "ex60": ex.get((key, 60)),
            "ex65": ex.get((key, 65)),
            "p_reach_90_from_65": ratio(90, 65),
            "p_reach_100_from_65": ratio(100, 65),
            "p_reach_100_from_80": ratio(100, 80),
            "quality_warning": bool(warn[key]),
        })
    return out


def main():
    out = build()
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    # Bundled YAML keyed by "CODE|sex" for O(1) lookup; small (~120 rows).
    table = {f"{r['country_code']}|{r['sex']}": {k: r[k] for k in (
        "country_name", "year", "ex60", "ex65", "p_reach_90_from_65",
        "p_reach_100_from_65", "p_reach_100_from_80", "quality_warning")} for r in out}
    doc = {
        "source": "Human Mortality Database (mortality.org) period life tables",
        "license": "HMD free for research/educational use (registration); see data/raw/datasets/hmd_DOWNLOAD_INSTRUCTIONS.txt",
        "method": "latest available year per country x sex; survival ratios from lx; ex at 60/65",
        "n_country_sex": len(out),
        "version": "1.0",
        "baselines": table,
    }
    with open(OUT_YAML, "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, sort_keys=True, allow_unicode=True)
    print(f"wrote {OUT_CSV} ({len(out)} rows) and {OUT_YAML} ({len(table)} keys)")


if __name__ == "__main__":
    main()
