"""Parse an NHANES Public-use Linked Mortality File (fixed-width ASCII .dat) into a CSV.

Layout follows the NCHS public-use LMF record format (the columns used by the official SAS/STATA/R
sample programs; all NCHS surveys share one layout, survey-specific fields blank elsewhere). Verify
against the sample program shipped with your download if a future release changes positions.

  field          cols (1-based)   meaning
  seqn           1-6              NHANES respondent sequence number (link key)
  eligstat       15               1=eligible, 2=under 18 (excluded), 3=ineligible
  mortstat       16               0=assumed alive, 1=assumed deceased (blank if not eligible)
  ucod_leading   17-19            leading underlying cause-of-death recode
  diabetes       20               diabetes contributing-cause flag (multiple cause)
  hyperten       21               hypertension contributing-cause flag
  permth_int     43-46            person-months, interview -> death/censor
  permth_exm     47-50            person-months, exam -> death/censor

Source: "Public-use Linked Mortality Files" (NCHS, updated May 2022),
https://www.cdc.gov/nchs/data-linkage/mortality-public.htm ; files at
https://ftp.cdc.gov/pub/Health_Statistics/NCHS/datalinkage/linked_mortality/

Usage:
  python scripts/validation/parse_nhanes_lmf.py NHANES_2017_2018_MORT_2019_PUBLIC.dat \
      data/processed/nhanes_lmf_2017_2018.csv
"""
from __future__ import annotations

import csv
import sys

# (name, start, end) 1-based inclusive
SPEC = [
    ("seqn", 1, 6),
    ("eligstat", 15, 15),
    ("mortstat", 16, 16),
    ("ucod_leading", 17, 19),
    ("diabetes", 20, 20),
    ("hyperten", 21, 21),
    ("permth_int", 43, 46),
    ("permth_exm", 47, 50),
]


def parse_line(line: str) -> dict:
    rec = {}
    for name, a, b in SPEC:
        val = line[a - 1:b].strip()
        rec[name] = "" if val in (".", "") else val
    return rec


def parse_file(path: str):
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            rows.append(parse_line(line))
    return rows


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: parse_nhanes_lmf.py <input.dat> <output.csv>")
    rows = parse_file(sys.argv[1])
    with open(sys.argv[2], "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[n for n, _, _ in SPEC])
        w.writeheader()
        w.writerows(rows)
    eligible = sum(1 for r in rows if r["eligstat"] == "1")
    deaths = sum(1 for r in rows if r["mortstat"] == "1")
    print(f"parsed {len(rows)} records ({eligible} eligible, {deaths} deaths) -> {sys.argv[2]}")


if __name__ == "__main__":
    main()
