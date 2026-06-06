"""Empirical epigenetic anchor for the Tier-3 clock layer — grounded on real oldest-old methylomes.

The Tier-3 epigenetic mapper assumes negative epigenetic age acceleration (biological age <
chronological) is the centenarian-favourable direction. This script REPLACES that declared assumption
with a measurement: it loads public, AI-permissible DNA-methylation datasets that contain verified
nonagenarians/centenarians (GEO, via biolearn), computes the standard validated clocks on them, and
reports the age-acceleration distribution by age band. The 90-99 / 100+ bands are the empirical
"exceptional-longevity" molecular centroid that a user's clocks are scored against.

This is the AI-safe route to a real (if small-n) molecular grounding for the longevity-trajectory
posterior: corpus is age-floored at 100, NHANES tops out at 80, but open methylation deposits carry
real 89-103-year-olds. See memory: data-access-ai-constraints.

Usage: python scripts/validation/epi_oldest_old_anchor.py
Deps: biolearn (optional 'omics' extra). Clocks are validated published instruments (Horvath 2013,
Hannum 2013, Levine PhenoAge 2018, Horvath SkinBlood 2018).
"""
from __future__ import annotations

import json
import os

import pandas as pd

# Datasets with verified oldest-old individuals (confirmed this session). Whole blood / PBMC, 450K.
DATASETS = ["GSE30870", "GSE40279", "GSE33233"]
# Linear, array-computable clocks (skip neural/EPIC-only ones that need CpGs a 450K set may lack).
CLOCKS = ["Horvathv1", "Hannum", "PhenoAge", "Horvathv2"]
BANDS = [(0, 60, "<60"), (60, 80, "60-79"), (80, 90, "80-89"), (90, 100, "90-99"), (100, 200, "100+")]


def band(a):
    for lo, hi, name in BANDS:
        if lo <= a < hi:
            return name
    return "unknown"


def main():
    from biolearn.data_library import DataLibrary
    from biolearn.model_gallery import ModelGallery
    lib, gallery = DataLibrary(), ModelGallery()

    frames = []
    for ds in DATASETS:
        try:
            d = lib.get(ds).load()
        except Exception as e:  # noqa: BLE001
            print(f"{ds}: load failed ({str(e)[:70]})", flush=True)
            continue
        md = d.metadata
        if md is None or "age" not in md.columns:
            print(f"{ds}: no age column", flush=True)
            continue
        out = pd.DataFrame({"dataset": ds, "age": pd.to_numeric(md["age"], errors="coerce")})
        for clk in CLOCKS:
            try:
                pred = gallery.get(clk).predict(d)["Predicted"]
                out[f"accel_{clk}"] = pred.values - out["age"].values
            except Exception as e:  # noqa: BLE001
                print(f"  {ds}/{clk}: predict failed ({str(e)[:60]})", flush=True)
        frames.append(out)
        print(f"{ds}: scored {len(out)} samples, ages {out['age'].min():.0f}-{out['age'].max():.0f}",
              flush=True)

    if not frames:
        raise SystemExit("no datasets scored")
    df = pd.concat(frames, ignore_index=True)
    df = df[df["age"].notna()].copy()
    df["band"] = df["age"].map(band)
    accel_cols = [c for c in df.columns if c.startswith("accel_")]
    df["accel_mean"] = df[accel_cols].mean(axis=1)

    # Age-acceleration by band: the oldest-old bands are the empirical longevity-favourable centroid.
    summary = {}
    print("\n==== epigenetic age acceleration (clock age - chronological) by band ====")
    print(f"{'band':8} {'n':>4} {'mean accel':>11} {'median':>8} {'% negative':>11}")
    for _, _, name in BANDS:
        sub = df[df["band"] == name]
        if not len(sub):
            continue
        a = sub["accel_mean"].dropna()
        rec = {"n": int(len(sub)), "mean_accel": round(float(a.mean()), 2),
               "median_accel": round(float(a.median()), 2),
               "pct_negative_accel": round(float((a < 0).mean() * 100), 1),
               "sd_accel": round(float(a.std()), 2)}
        summary[name] = rec
        print(f"{name:8} {rec['n']:4} {rec['mean_accel']:11} {rec['median_accel']:8} "
              f"{rec['pct_negative_accel']:10}%")

    # Empirical centroid for the exceptional-longevity (90+) molecular profile, per clock.
    old = df[df["age"] >= 90]
    centroid = {c.replace("accel_", ""): {"mean_accel": round(float(old[c].mean()), 2),
                                          "sd_accel": round(float(old[c].std()), 2),
                                          "n": int(old[c].notna().sum())}
                for c in accel_cols}
    n90 = int((df["age"] >= 90).sum())
    n100 = int((df["age"] >= 100).sum())

    os.makedirs("reports/epi_oldest_old_anchor", exist_ok=True)
    payload = {"datasets": DATASETS, "clocks": CLOCKS, "n_total": int(len(df)),
               "n_nonagenarian_plus": n90, "n_centenarian_plus": n100,
               "acceleration_by_band": summary, "longevity_centroid_90plus": centroid}
    with open("reports/epi_oldest_old_anchor/anchor.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"\nverified 90+ individuals scored: {n90}  (100+: {n100})")
    print("longevity centroid (mean accel, 90+):",
          {k: v["mean_accel"] for k, v in centroid.items()})
    print("wrote reports/epi_oldest_old_anchor/anchor.json")


if __name__ == "__main__":
    main()
