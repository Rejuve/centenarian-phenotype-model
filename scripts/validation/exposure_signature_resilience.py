"""Smoking molecular signature + the resilience/escaper decoupling (NHANES 1999-2002 DNAm subsample).

Reframes "smoking is bad" into the questions that matter for longevity medicine:
  A. COUPLING   — how much does smoking move the epigenetic clocks (vs the weak clinical-lab coupling)?
  B. SIGNATURE  — WHICH molecular features co-move with smoking (the defined cluster it induces)?
  C. RESILIENCE — does the molecular CONSEQUENCE (clock state), not the behaviour, carry the mortality
                  risk? i.e. do "resilient smokers" (smoke + clean clock) survive like non-smokers, and
                  do favourable-lifestyle / adverse-clock people still die early? If conditioning on the
                  clock ATTENUATES smoking's own mortality coefficient, the molecular layer captures the
                  risk — the empirical case for ELC reading molecular state over a lifestyle checklist.

Merges the lifestyle/clinical cohort (build_cohort_from_xpt.py) with the clock cohort (build_epi_cohort.py)
on subject_id. Clocks are ALIGNMENTS (higher = younger/favourable = lower acceleration); molecular
favourability = mean of the mortality-relevant clock alignments. Cross-sectional; NHANES shows the
phenotypic decoupling, not the genetic "why" of resilience (that needs genotype). Modest cells flagged.

Usage: python scripts/validation/exposure_signature_resilience.py
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
import pandas as pd

CLOCKS = ["f_clock_grimage", "f_clock_grimage2", "f_clock_phenoage", "f_clock_dunedinpace",
          "f_clock_hannum", "f_clock_horvath", "f_clock_skinblood"]  # exclude dnam_telomere (scale)
SMOKE_LABEL = {1.0: "never", 0.5: "former", 0.15: "current"}


def _logit(X, y, iters=600, lr=0.5, l2=1e-4):
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    Xs = (X - mu) / sd
    w, b = np.zeros(Xs.shape[1]), 0.0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(Xs @ w + b)))
        e = p - y
        w -= lr * (Xs.T @ e / len(y) + l2 * w)
        b -= lr * e.mean()
    return w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--life", default="data/processed/nhanes_cohort_9902_lifestyle.csv")
    ap.add_argument("--epi", default="data/processed/nhanes_epi_cohort.csv")
    ap.add_argument("--out", default="reports/exposure_signature_resilience")
    args = ap.parse_args()

    life = pd.read_csv(args.life, low_memory=False)
    epi = pd.read_csv(args.epi, low_memory=False)
    clk = [c for c in CLOCKS if c in epi.columns]
    df = life.merge(epi[["subject_id"] + clk], on="subject_id", how="inner")
    df["age"] = pd.to_numeric(df["age"], errors="coerce")
    df["deceased"] = pd.to_numeric(df["deceased"], errors="coerce")
    df["sex_m"] = (df["sex"] == "M").astype(float)
    df["mol_fav"] = df[clk].mean(axis=1)        # higher = younger/favourable clock state
    df["smoke"] = df["f_q_smoking"].map(SMOKE_LABEL)
    out = {"n": int(len(df)), "deaths": int((df["deceased"] == 1).sum()), "clocks": clk}

    # ---- A. smoking -> clock coupling (dR2 beyond age/sex), per clock ----
    couple = []
    for c in clk + ["mol_fav"]:
        d = df[[c, "age", "sex_m", "f_q_smoking"]].dropna()
        if len(d) < 200:
            continue
        y = d[c].to_numpy(float)
        def R2(names):
            A = d[names].to_numpy(float)
            A = (A - A.mean(0)) / np.where(A.std(0) == 0, 1, A.std(0))
            Ai = np.column_stack([np.ones(len(A)), A])
            beta, *_ = np.linalg.lstsq(Ai, y, rcond=None)
            pred = Ai @ beta
            ssr = ((y - pred) ** 2).sum()
            sst = ((y - y.mean()) ** 2).sum()
            return (1 - ssr / sst) if sst else 0.0
        couple.append({"clock": c.replace("f_clock_", "").replace("f_", ""),
                       "r2_age_sex": round(R2(["age", "sex_m"]), 4),
                       "r2_plus_smoking": round(R2(["age", "sex_m", "f_q_smoking"]), 4),
                       "smoking_dR2": round(R2(["age", "sex_m", "f_q_smoking"]) - R2(["age", "sex_m"]), 4)})
    couple.sort(key=lambda r: -r["smoking_dR2"])
    out["A_smoking_clock_coupling"] = couple

    # ---- B. signature: which molecular features co-move with smoking (Pearson r) ----
    sig = {}
    for c in clk + [col for col in df.columns if col.startswith("f_") and col not in ("f_q_smoking",)]:
        d = df[["f_q_smoking", c]].dropna()
        if len(d) < 200 or d[c].std() == 0:
            continue
        r = float(np.corrcoef(d["f_q_smoking"], d[c])[0, 1])
        sig[c.replace("f_clock_", "clock:").replace("f_", "")] = round(r, 3)
    # smoking alignment is high=never; positive r => feature favourable when NOT smoking (smoking lowers it)
    out["B_smoking_comovers"] = dict(sorted(sig.items(), key=lambda kv: -abs(kv[1]))[:12])

    # ---- C. resilience decoupling ----
    d = df[["deceased", "age", "sex_m", "f_q_smoking", "mol_fav", "smoke"]].dropna()
    d = d[d["smoke"].notna()]
    # death rate by smoking x molecular-favourability tertile
    d["mol_tertile"] = pd.qcut(d["mol_fav"], 3, labels=["adverse", "mid", "favourable"])
    grid = {}
    for sm in ["never", "former", "current"]:
        for mt in ["adverse", "mid", "favourable"]:
            cell = d[(d["smoke"] == sm) & (d["mol_tertile"] == mt)]
            if len(cell):
                grid[f"{sm}/{mt}"] = {"n": int(len(cell)), "death_rate": round(float(cell["deceased"].mean()), 3)}
    out["C_death_rate_by_smoking_x_clock"] = grid

    # formal: does conditioning on the clock attenuate smoking's own mortality coefficient?
    base = d[["f_q_smoking", "age", "sex_m"]].to_numpy(float)
    full = d[["f_q_smoking", "mol_fav", "age", "sex_m"]].to_numpy(float)
    y = d["deceased"].to_numpy(float)
    w_base = _logit(base, y)
    w_full = _logit(full, y)
    # f_q_smoking is high=never (protective), so coefficient should be NEGATIVE (more 'never' -> less death)
    out["C_smoking_coef_alone"] = round(float(w_base[0]), 4)
    out["C_smoking_coef_given_clock"] = round(float(w_full[0]), 4)
    out["C_clock_coef_given_smoking"] = round(float(w_full[1]), 4)
    out["C_smoking_attenuation_pct"] = round(
        100 * (1 - abs(w_full[0]) / abs(w_base[0])) if w_base[0] else 0.0, 1)

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "signature_resilience.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    print(f"# Smoking molecular signature + resilience (NHANES 1999-2002 DNAm, n={out['n']}, "
          f"{out['deaths']} deaths)\n")
    print("A. smoking -> clock coupling (dR2 beyond age/sex):")
    for r in couple:
        print(f"   {r['clock']:14} dR2={r['smoking_dR2']:.4f}  "
              f"(age/sex {r['r2_age_sex']:.3f} -> +smk {r['r2_plus_smoking']:.3f})")
    print("\nB. smoking co-movers (|r| desc; +r = feature favourable in non-smokers):")
    for k, v in out["B_smoking_comovers"].items():
        print(f"   {k:26} r={v:+.3f}")
    print("\nC. death rate by smoking x clock tertile:")
    for k, v in grid.items():
        print(f"   {k:20} n={v['n']:4}  death={v['death_rate']:.3f}")
    print(f"\nC. smoking mortality coef: alone={out['C_smoking_coef_alone']:+.3f}  "
          f"given clock={out['C_smoking_coef_given_clock']:+.3f}  "
          f"(attenuation {out['C_smoking_attenuation_pct']}%);  "
          f"clock coef given smoking={out['C_clock_coef_given_smoking']:+.3f}")
    print("wrote", os.path.join(args.out, "signature_resilience.json"))


if __name__ == "__main__":
    main()
