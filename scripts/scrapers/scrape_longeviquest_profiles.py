"""Scrape LongeviQuest supercentenarian profile pages as 'database_profile' rows.

LongeviQuest is a validated-supercentenarian DATABASE; each profile blurb is a
single-subject biographical text in the same data-class family as an obituary
(retrospective, subject-centric) rather than topical news. We mine the blurb as an
article-equivalent and tag traits with the existing keyword pipeline.

Two stages, decoupled so a ~2h scrape is crash-safe and resumable:
  scrape : fetch profile pages -> append row-by-row to a STAGING csv
           (data/raw/datasets/longeviquest_profiles.csv). Resume skips any URL
           already in news_articles.csv OR the staging file.
  merge  : append staging rows (not already present by URL) into news_articles.csv.

Cloudflare is satisfied by a real browser UA (no selenium needed). Rate limit 1 req/2s.

Usage:
  python scrape_longeviquest_profiles.py scrape all        # all atlas entries (default)
  python scrape_longeviquest_profiles.py scrape verified   # only ~201 already-in-news
  python scrape_longeviquest_profiles.py scrape all 25     # cap 25 (smoke test)
  python scrape_longeviquest_profiles.py merge             # staging -> news_articles.csv
"""
import csv
import os
import re
import sys
import time
import unicodedata

import pandas as pd
import requests

# extract_layer1_traits lives in scripts/pipeline/ — add it to the import path.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import extract_layer1_traits as E

NEWS = "data/raw/news_articles.csv"
ATLAS = "data/raw/datasets/longeviquest_atlas.csv"
VERIFIED = "data/processed/_verified_in_news.csv"
STAGING = "data/raw/datasets/longeviquest_profiles.csv"
PROFILE_URL = "https://longeviquest.com/supercentenarian/{}/"
TODAY = "2026-06-01"
DELAY = 2.0

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
}

CAT_COL = {
    "physical_activity": "trait_physical_activity",
    "diet": "trait_diet",
    "social": "trait_social",
    "purpose_psychology": "trait_purpose_psychology",
    "sleep": "trait_sleep",
}


def slugify(name):
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def extract_bio(html):
    out = []
    for p in re.findall(r"<p[^>]*>(.*?)</p>", html, re.S):
        t = re.sub(r"<[^>]+>", " ", p)
        t = re.sub(r"\s+", " ", t).strip()
        if len(t) < 40:
            continue
        low = t.lower()
        if low.startswith("(source") or low.startswith("source:"):
            continue
        if re.match(r"^in \d{4},? aged", low) and len(t) < 90:
            continue
        if "(source:" in low and len(t) < 90:
            continue
        out.append(t)
    seen, uniq = set(), []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return " ".join(uniq)


def tag_traits(full_text):
    cats = set()
    for rx, _label, cat in E.KEYWORD_TRAITS:
        if rx.search(full_text):
            cats.add(cat)
    return {col: (cat in cats) for cat, col in CAT_COL.items()}


def news_columns():
    return list(pd.read_csv(NEWS, nrows=0).columns)


def build_row(cols, dtypes, atlas_row, url, full_text, traits):
    row = {}
    for c in cols:
        dt = str(dtypes.get(c, "object"))
        row[c] = False if dt == "bool" else ("" if dt == "object" else "")
    name = atlas_row["name"]
    age = atlas_row.get("age_years")
    has_age = pd.notna(age)
    row.update({
        "source_name": "LongeviQuest",
        "source_country": "international",
        "source_class": "database_profile",
        "url": url,
        "scraped_date": TODAY,
        "publish_date": "",
        "title": f"{name} – LongeviQuest validated supercentenarian profile",
        "word_count": len(full_text.split()),
        "full_text": full_text,
        "subject_name": name,
        "subject_age": (float(age) if has_age else ""),
        "subject_city": "",
        "subject_country": atlas_row.get("country", ""),
        "ages_mentioned": (str(int(age)) if has_age else ""),
        "max_age": (float(age) if has_age else ""),
        "has_age": bool(has_age),
        "has_stats": False,
        "is_centenarian_profile": True,
    })
    row.update(traits)
    return row


def load_done_urls():
    done = set()
    if os.path.exists(NEWS):
        done |= set(pd.read_csv(NEWS, usecols=["url"], low_memory=False)["url"].dropna().astype(str))
    if os.path.exists(STAGING):
        done |= set(pd.read_csv(STAGING, usecols=["url"], low_memory=False)["url"].dropna().astype(str))
    return done


def scrape(mode, cap):
    cols = news_columns()
    dtypes = pd.read_csv(NEWS, nrows=200, low_memory=False).dtypes.to_dict()
    done = load_done_urls()

    atlas = pd.read_csv(ATLAS, low_memory=False)
    atlas["slug"] = atlas["name"].map(slugify)
    atlas = atlas.drop_duplicates("slug")

    if mode == "verified" and os.path.exists(VERIFIED):
        want = list(dict.fromkeys(pd.read_csv(VERIFIED)["slug"].tolist()))
        order = {s: i for i, s in enumerate(want)}
        targets = atlas[atlas["slug"].isin(want)].sort_values(
            by="slug", key=lambda s: s.map(lambda x: order.get(x, 1e9)))
    else:
        targets = atlas
    if cap:
        targets = targets.head(cap)

    staging_exists = os.path.exists(STAGING)
    fh = open(STAGING, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(fh, fieldnames=cols)
    if not staging_exists:
        writer.writeheader()
        fh.flush()

    sess = requests.Session()
    sess.headers.update(HEADERS)
    total = len(targets)
    n_fetch = n_skip = n_fail = n_404 = 0
    for i, (_, a) in enumerate(targets.iterrows(), 1):
        url = PROFILE_URL.format(a["slug"])
        if url in done:
            n_skip += 1
            continue
        # Pace so request *starts* are >=DELAY apart (1 req / 2s exactly), rather
        # than DELAY + fetch_time apart -- honors the rate limit without the
        # per-request fetch latency stacking on top.
        t_start = time.time()
        try:
            r = sess.get(url, timeout=25)
        except Exception as e:
            n_fail += 1
            print(f"  [{i}/{total}] {a['slug']}: ERROR {e}", flush=True)
            time.sleep(max(0, DELAY - (time.time() - t_start))); continue
        if r.status_code == 404:
            n_404 += 1
            time.sleep(max(0, DELAY - (time.time() - t_start))); continue
        if r.status_code != 200:
            n_fail += 1
            print(f"  [{i}/{total}] {a['slug']}: HTTP {r.status_code}", flush=True)
            time.sleep(max(0, DELAY - (time.time() - t_start))); continue
        bio = extract_bio(r.text)
        if len(bio.split()) < 20:
            n_fail += 1
            time.sleep(max(0, DELAY - (time.time() - t_start))); continue
        row = build_row(cols, dtypes, a, url, bio, tag_traits(bio))
        writer.writerow(row)
        fh.flush()
        done.add(url)
        n_fetch += 1
        if n_fetch % 25 == 0:
            print(f"  [{i}/{total}] fetched {n_fetch} (last: {a['name']}, {len(bio.split())}w)", flush=True)
        time.sleep(max(0, DELAY - (time.time() - t_start)))
    fh.close()
    print(f"\nSCRAPE DONE mode={mode}: fetched={n_fetch} skipped={n_skip} 404={n_404} failed={n_fail}", flush=True)
    print(f"Staging file: {STAGING}", flush=True)


def merge():
    news = pd.read_csv(NEWS, low_memory=False)
    stage = pd.read_csv(STAGING, low_memory=False)
    have = set(news["url"].dropna().astype(str))
    add = stage[~stage["url"].astype(str).isin(have)].copy()
    add = add.reindex(columns=news.columns)
    combined = pd.concat([news, add], ignore_index=True)
    combined.to_csv(NEWS, index=False, encoding="utf-8")
    print(f"MERGE: staging={len(stage)} new={len(add)} -> {NEWS} now {len(combined)} rows")


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "scrape"
    if action == "merge":
        merge(); return
    mode = sys.argv[2] if len(sys.argv) > 2 else "all"
    cap = int(sys.argv[3]) if len(sys.argv) > 3 else None
    scrape(mode, cap)


if __name__ == "__main__":
    main()
