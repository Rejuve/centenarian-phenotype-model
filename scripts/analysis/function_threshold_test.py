"""Endpoint design probe: should the ELC functional bar be FULL ADL/IADL independence, or is
'minimal assistance' (some difficulty, no much/unable) compatible with a well-rated life?

Decision rule (Jasmine): compare the lived-well proxy (self-rated health) between FULL independence
and MINIMAL assistance. If similar -> 'minimal assistance' can count as healthy; if a big gap ->
keep the bar at full independence.

NHANES has no direct life-satisfaction item, so self-rated health (HUQ010, 1=excellent..5=poor) is the
proxy (it is also the endpoint's self-report measure). ADL/IADL from PFQ061 difficulty items:
  ADL  = walk between rooms (H), stand from chair (I), in/out bed (J), dressing (K), eating (T)
  IADL = managing money (A), house chores (F), preparing meals (G)
Difficulty codes 1=none 2=some 3=much 4=unable; 5/7/9 = do-not-do/refused/DK (ignored per item).
  full       = no difficulty on all available items
  minimal    = some difficulty (max 2), none much/unable
  dependent  = any much difficulty or unable (>=3)

Reads cached cycle files (2007-2010); reports overall and for age>=70 (the endpoint-relevant band).
Usage: python scripts/analysis/function_threshold_test.py
"""
from __future__ import annotations

import glob
import os

import pandas as pd

CYCLES = ["2007-2008", "2009-2010", "2011-2012"]
ADL = ["PFQ061H", "PFQ061I", "PFQ061J", "PFQ061K", "PFQ061T"]
IADL = ["PFQ061A", "PFQ061F", "PFQ061G"]
ITEMS = ADL + IADL


def _xpt(cyc, prefix):
    d = os.path.join("data", "raw", "datasets", "nhanes_cycles", cyc)
    f = glob.glob(os.path.join(d, f"{prefix}*.xpt"))
    if not f:
        return None
    df = pd.read_sas(f[0], format="xport")
    return df.set_index(df["SEQN"].astype("int64"))


def classify(row):
    vals = [row[i] for i in ITEMS if i in row.index and row[i] in (1, 2, 3, 4)]
    if not vals:
        return None
    mx = max(vals)
    return "full" if mx == 1 else ("minimal" if mx == 2 else "dependent")


def main():
    frames = []
    for cyc in CYCLES:
        demo, pfq, huq = _xpt(cyc, "DEMO"), _xpt(cyc, "PFQ"), _xpt(cyc, "HUQ")
        if demo is None or pfq is None or huq is None:
            print(f"({cyc}: missing files, skipped)")
            continue
        idx = demo.index
        d = pd.DataFrame(index=idx)
        d["age"] = demo["RIDAGEYR"]
        d["sex"] = demo["RIAGENDR"].map({1: "M", 2: "F"})
        for it in ITEMS:
            d[it] = pfq[it] if it in pfq.columns else pd.NA
        d["huq010"] = huq["HUQ010"] if "HUQ010" in huq.columns else pd.NA
        frames.append(d)
    df = pd.concat(frames)
    df["indep"] = df.apply(classify, axis=1)
    df = df[df["indep"].notna()].copy()
    df["srh"] = pd.to_numeric(df["huq010"], errors="coerce")
    df = df[df["srh"].isin([1, 2, 3, 4, 5])]
    df["good"] = (df["srh"] <= 3).astype(int)  # good/very good/excellent

    def summarize(sub, label):
        print(f"\n== {label} (n={len(sub)}) ==")
        print(f"{'group':12} {'n':>6} {'%good_SRH':>10} {'mean_SRH':>9}")
        res = {}
        for g in ["full", "minimal", "dependent"]:
            cell = sub[sub["indep"] == g]
            if not len(cell):
                continue
            pct = 100 * cell["good"].mean()
            res[g] = (len(cell), pct, cell["srh"].mean())
            print(f"{g:12} {len(cell):6} {pct:10.1f} {cell['srh'].mean():9.2f}")
        if "full" in res and "minimal" in res:
            dg = res["full"][1] - res["minimal"][1]
            dm = res["minimal"][2] - res["full"][2]
            print(f"  -> FULL vs MINIMAL: %good gap {dg:+.1f} pts, mean-SRH gap {dm:+.2f} "
                  f"(SRH 1=excellent..5=poor)")
        return res

    summarize(df, "ALL AGES")
    summarize(df[df["age"] >= 70], "AGE >= 70 (endpoint-relevant)")
    summarize(df[df["age"] >= 80], "AGE >= 80")


if __name__ == "__main__":
    main()
