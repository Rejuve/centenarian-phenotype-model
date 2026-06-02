"""
TASK 2 (background) — centenarian gut-microbiome composition data acquisition.

Attempts programmatic, registration-free acquisition from public APIs/endpoints,
downloads any composition tables (csv/xlsx/tsv), and logs every outcome (success
or blocker) to data/raw/datasets/microbiome/acquisition_log.md. On a hard blocker
for a given source it logs and moves on; it never blocks or interrupts Task 1.

Sources attempted, in priority order:
  1. Biagi et al. 2016 (Current Biology) — via PMC open-access service
  2. Wilmanski et al. 2021 (Nature Metabolism) — supplementary
  3. Zenodo API search (centenarian/longevity microbiome)
  4. Figshare API search (centenarian/longevity microbiome)
"""
import json
import os
import time
import urllib.parse

import requests

OUT = "data/raw/datasets/microbiome"
LOG = os.path.join(OUT, "acquisition_log.md")
UA = {"User-Agent": "Mozilla/5.0 (research data acquisition; contact: jasmine@rejuve.ai)"}
DATA_EXT = (".csv", ".tsv", ".xlsx", ".xls", ".biom", ".txt")

os.makedirs(OUT, exist_ok=True)
_lines = ["# Microbiome data acquisition log", "",
          f"Run: {time.strftime('%Y-%m-%d %H:%M')}", ""]


def log(msg):
    _lines.append(msg)
    with open(LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines) + "\n")


def dl(url, fname):
    try:
        r = requests.get(url, headers=UA, timeout=40)
        if r.status_code != 200:
            log(f"  - BLOCKER: HTTP {r.status_code} for {url}")
            return False
        path = os.path.join(OUT, fname)
        with open(path, "wb") as f:
            f.write(r.content)
        log(f"  - ✅ downloaded `{fname}` ({len(r.content)//1024} KB) from {url}")
        return True
    except Exception as e:
        log(f"  - BLOCKER: {type(e).__name__} {e} for {url}")
        return False


def try_pmc(pmid, label):
    log(f"## {label} (PMID {pmid}) — PMC open-access")
    try:
        # Does an open-access PMC copy exist?
        conv = requests.get(
            f"https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?ids={pmid}&format=json",
            headers=UA, timeout=30).json()
        rec = conv.get("records", [{}])[0]
        pmcid = rec.get("pmcid")
        if not pmcid:
            log(f"  - BLOCKER: no PMC id for PMID {pmid} (likely not open access). Stop this source.")
            return
        oa = requests.get(
            f"https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id={pmcid}",
            headers=UA, timeout=30).text
        if "idDoesNotExist" in oa or "<error" in oa or "href" not in oa:
            log(f"  - BLOCKER: {pmcid} not in the PMC Open Access subset (supplementary not programmatically retrievable). Stop this source.")
            return
        log(f"  - {pmcid} is in the PMC OA subset; package link present in oa.fcgi response.")
        import re
        m = re.search(r'href="([^"]+\.tar\.gz)"', oa)
        if m:
            log(f"  - OA package: {m.group(1)} (tarball with supplementary; manual extract).")
    except Exception as e:
        log(f"  - BLOCKER: {type(e).__name__} {e}. Stop this source.")


def try_zenodo():
    log("## Zenodo API search")
    try:
        q = urllib.parse.quote("centenarian gut microbiome")
        r = requests.get(f"https://zenodo.org/api/records/?q={q}&size=10&type=dataset",
                         headers=UA, timeout=40)
        if r.status_code != 200:
            log(f"  - BLOCKER: Zenodo API HTTP {r.status_code}. Stop."); return
        hits = r.json().get("hits", {}).get("hits", [])
        log(f"  - {len(hits)} dataset hit(s).")
        got = 0
        for h in hits[:6]:
            title = h.get("metadata", {}).get("title", "")[:80]
            for f in h.get("files", []):
                key = f.get("key", "")
                if key.lower().endswith(DATA_EXT):
                    link = f.get("links", {}).get("self") or f.get("links", {}).get("download")
                    if link and dl(link, f"zenodo_{key}"):
                        got += 1
                        log(f"    (from: {title})")
        if got == 0:
            log("  - no directly-downloadable composition tables in top hits.")
    except Exception as e:
        log(f"  - BLOCKER: {type(e).__name__} {e}. Stop.")


def try_figshare():
    log("## Figshare API search")
    try:
        r = requests.post("https://api.figshare.com/v2/articles/search",
                          json={"search_for": "centenarian gut microbiome", "page_size": 10},
                          headers=UA, timeout=40)
        if r.status_code != 200:
            log(f"  - BLOCKER: Figshare API HTTP {r.status_code}. Stop."); return
        arts = r.json()
        log(f"  - {len(arts)} article hit(s).")
        got = 0
        for a in arts[:6]:
            det = requests.get(a["url"], headers=UA, timeout=40)
            if det.status_code != 200:
                continue
            for f in det.json().get("files", []):
                name = f.get("name", "")
                if name.lower().endswith(DATA_EXT):
                    if dl(f.get("download_url"), f"figshare_{name}"):
                        got += 1
            time.sleep(1)
        if got == 0:
            log("  - no directly-downloadable composition tables in top hits.")
    except Exception as e:
        log(f"  - BLOCKER: {type(e).__name__} {e}. Stop.")


def main():
    log("Attempting registration-free programmatic acquisition.\n")
    try_pmc("27185560", "Biagi et al. 2016 — Gut Microbiota and Extreme Longevity")
    log("")
    try_pmc("34663975", "Wilmanski et al. 2021 — gut microbiome & longevity")
    log("")
    try_zenodo()
    log("")
    try_figshare()
    log("")
    # summary
    files = [f for f in os.listdir(OUT) if f.lower().endswith(DATA_EXT)]
    log(f"## Summary\n  - data files retrieved: {len(files)}")
    for f in files:
        log(f"    - {f}")
    if not files:
        log("  - No composition tables retrieved programmatically. Remaining sources "
            "(Current Biology / Nature supplementary) sit behind publisher pages that "
            "require manual download — see FETCH.md. Flagged PENDING.")
    log("\nDONE.")
    print(f"microbiome acquisition done; {len(files)} files; log -> {LOG}")


if __name__ == "__main__":
    main()
