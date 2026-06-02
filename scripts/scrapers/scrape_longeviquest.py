"""Scrape the full LongeviQuest atlas (validated supercentenarians) into a CSV.

The atlas at https://longeviquest.com/atlas/world paginates via ?page=N (100 rows
per page, ~40 pages / 3941 entries). Each list row carries:
  rank, name, birth_date, death_date, age_years, age_days, gender, country, _, status

Profile pages (/supercentenarian/<slug>/) are Cloudflare-protected (403 to plain
curl); list pages return 200. We scrape the list pages here.
"""
import csv
import re
import subprocess
import sys
import time

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
BASE = "https://longeviquest.com/atlas/world?page={}"
OUT = "data/raw/datasets/longeviquest_atlas.csv"


def fetch(url):
    r = subprocess.run(["curl", "-s", "-A", UA, url], capture_output=True, text=True,
                       encoding="utf-8", errors="ignore")
    return r.stdout


def iso(d):
    d = d.strip()
    if not d or d.lower() in ("living", "alive", "-", "n/a"):
        return ""
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", d)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def parse_rows(html):
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        tds = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)
        cells = [re.sub(r"<[^>]+>", " ", c).strip() for c in tds]
        cells = [re.sub(r"\s+", " ", c) for c in cells]
        if len(cells) < 8 or not cells[0].isdigit():
            continue  # header / malformed
        rank, name, bd, dd, ay, ad, gender, country = cells[:8]
        status = cells[9] if len(cells) > 9 else (cells[-1] if len(cells) > 8 else "")
        if name.startswith("N/A") or not name:
            continue  # anonymous, no merge key
        g = "M" if gender.strip().lower().startswith("m") else "F" if gender.strip().lower().startswith("f") else ""
        ay_num = int(ay) if ay.isdigit() else None
        out.append(dict(rank=int(rank), name=name, gender=g, birth_date=iso(bd),
                        death_date=iso(dd), age_years=ay_num, country=country,
                        still_alive=(dd.strip().lower() in ("living", "alive")),
                        status=status, dataset_source="longeviquest"))
    return out


def main():
    last = int(sys.argv[1]) if len(sys.argv) > 1 else 41
    rows, seen = [], set()
    for p in range(1, last + 1):
        html = fetch(BASE.format(p))
        page_rows = parse_rows(html)
        if not page_rows:
            print(f"  page {p}: 0 rows (stop)")
            break
        new = 0
        for r in page_rows:
            key = (r["name"], r["birth_date"])
            if key in seen:
                continue
            seen.add(key)
            rows.append(r)
            new += 1
        print(f"  page {p}: {len(page_rows)} rows ({new} new), running total {len(rows)}")
        time.sleep(0.5)  # be polite

    cols = ["rank", "name", "gender", "birth_date", "death_date", "age_years",
            "country", "still_alive", "status", "dataset_source"]
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    nm = sum(r["gender"] == "M" for r in rows)
    nf = sum(r["gender"] == "F" for r in rows)
    nx = len(rows) - nm - nf
    print(f"\nWrote {len(rows)} rows -> {OUT}")
    print(f"gender: M={nm} F={nf} missing/other={nx} | %F_known={100*nf/(nm+nf):.1f}%")


if __name__ == "__main__":
    main()
