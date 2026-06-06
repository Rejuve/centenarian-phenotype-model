"""Scan biolearn's public methylation datasets for individual-level 90-99 (nonagenarian)
and 100+ samples. Loads each candidate's age metadata and counts the oldest-old band.

Purpose: establish what FREE, no-DUA, individual-level oldest-old molecular phenotype data
is actually reachable for grounding the epigenetic layer / making the age posteriors real.

Usage: python scripts/analysis/biolearn_age_harvest.py
"""
from __future__ import annotations

import sys

from biolearn.data_library import DataLibrary

# Human blood/tissue methylation sets that plausibly reach old age (from the catalogue scan).
CANDIDATES = [
    "GSE30870", "GSE40279", "GSE52588", "GSE41169", "GSE42861", "GSE69270",
    "GSE41037", "GSE20236", "GSE49904", "GSE51057", "GSE73103", "GSE53740",
    "GSE50660", "GSE106648", "GSE19711", "GSE68194", "GSE58888", "GSE33233",
    "GSE50498", "GSE87571", "GSE55763", "GSE72774", "GSE72775", "GSE36064",
]


def main():
    lib = DataLibrary()
    rows = []
    for ds in CANDIDATES:
        try:
            src = lib.get(ds)
        except Exception as e:  # noqa: BLE001
            print(f"{ds}: not in catalogue ({e})", flush=True)
            continue
        try:
            d = src.load()
            md = d.metadata
            if md is None or "age" not in md.columns:
                print(f"{ds}: loaded, no age column", flush=True)
                continue
            a = md["age"].dropna()
            n90 = int(((a >= 90) & (a < 100)).sum())
            n100 = int((a >= 100).sum())
            n80 = int(((a >= 80) & (a < 90)).sum())
            title = (getattr(src, "title", "") or "")[:55]
            rows.append((ds, len(a), int(a.min()), int(a.max()), n80, n90, n100, title))
            print(f"{ds}: n={len(a)} age {int(a.min())}-{int(a.max())} | "
                  f"80-89={n80} 90-99={n90} 100+={n100} | {title}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"{ds}: load failed ({type(e).__name__}: {str(e)[:80]})", flush=True)

    rows.sort(key=lambda r: (r[5] + r[6]), reverse=True)
    print("\n==== RANKED BY 90+ SAMPLE COUNT ====", flush=True)
    print(f"{'dataset':12} {'N':>5} {'min':>4} {'max':>4} {'80-89':>6} {'90-99':>6} {'100+':>5}  title")
    for ds, n, lo, hi, n80, n90, n100, title in rows:
        print(f"{ds:12} {n:5} {lo:4} {hi:4} {n80:6} {n90:6} {n100:5}  {title}")
    tot90 = sum(r[5] for r in rows)
    tot100 = sum(r[6] for r in rows)
    print(f"\nTOTAL individual nonagenarian (90-99) samples reachable: {tot90}")
    print(f"TOTAL individual centenarian (100+) samples reachable:   {tot100}")


if __name__ == "__main__":
    sys.exit(main())
