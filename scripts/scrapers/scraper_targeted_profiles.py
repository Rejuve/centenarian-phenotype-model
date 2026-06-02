"""
Targeted news collection — three passes to improve centenarian profile diversity.

  1. Obituary scraper       — 9 DuckDuckGo queries targeting obit sources
  2. Oral history archives  — Library of Congress JSON + StoryCorps HTML + 100yearoldclub
  3. Local/regional search  — 3 query templates × 4 region codes (au, ca, uk, us)

All results append to data/raw/news_articles.csv with source_class set to one of:
  "obituary", "oral_history", "regional_local"

Reuses search_ddg / fetch_article / extract_* helpers from scraper_search.py
so the row schema matches the existing news_articles.csv exactly.

Run:  PYTHONIOENCODING=utf-8 python -u scraper_targeted_profiles.py
"""
import os
import sys
import csv
import time
import json
from datetime import datetime
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
import pandas as pd

sys.path.insert(0, ".")
from scraper_search import (
    search_ddg, fetch_article, save_rec, load_done, detect_country,
    extract_ages, extract_stats, extract_columns, extract_subject,
    content_ok, HEADERS, OUTPUT_DIR, OUTPUT_FILE, MIN_WORD_COUNT,
)

OUT_PATH = os.path.join(OUTPUT_DIR, OUTPUT_FILE)

# Cap per-query result count so a single targeted run doesn't take all day.
RESULTS_PER_QUERY = 30
DELAY_BETWEEN_ARTICLES = 1.0
DELAY_BETWEEN_SEARCHES = 2.5

# ─────────────────────────────────────────────────────────────────────────────
# Query sets
# ─────────────────────────────────────────────────────────────────────────────

OBITUARY_QUERIES = [
    ("ny_times_obit_100",   '"obituary" "100 years old" site:nytimes.com',                "us-en"),
    ("guardian_obit",       '"obituary" "centenarian" site:theguardian.com',              "uk-en"),
    ("wapo_obit_100",       '"obituary" "100 years old" site:washingtonpost.com',         "us-en"),
    ("legacy_obit",         '"obituary" "centenarian" site:legacy.com',                   "us-en"),
    ("obit_101_103",        '"obituary" "101 years old" OR "102 years old" OR "103 years old"', "wt-wt"),
    ("obit_104_106",        '"obituary" "104 years old" OR "105 years old" OR "106 years old"', "wt-wt"),
    ("obit_aus",            '"obituary" centenarian (site:smh.com.au OR site:abc.net.au OR site:theage.com.au)', "au-en"),
    ("obit_can",            '"obituary" centenarian (site:cbc.ca OR site:globeandmail.com)', "ca-en"),
    ("obit_japan",          '"obituary" centenarian site:japantimes.co.jp',               "wt-wt"),
]

REGIONAL_QUERY_TEMPLATES = [
    ("patch_oldest",        '"years old" "oldest resident" "secret" longevity site:patch.com'),
    ("local_centenarian",   '"years old" "birthday" "centenarian"'),
    ("birthday_secret",     '"100th birthday" "secret long life" -syndicated'),
]
REGIONAL_REGIONS = ["au-en", "ca-en", "uk-en", "us-en"]


# ─────────────────────────────────────────────────────────────────────────────
# Article saver (shared schema with scraper_search.py)
# ─────────────────────────────────────────────────────────────────────────────

def build_record(url, title, body, source_class):
    domain = urlparse(url).netloc.replace("www.", "")
    full   = (title or "") + " " + (body or "")
    ages   = extract_ages(full)
    stats  = extract_stats(body or "")
    cols   = extract_columns(body or "")
    subj   = extract_subject(title or "", body or "")
    max_age = str(max(int(a) for a in ages.split(","))) if ages else ""

    rec = {
        "source_name":    domain,
        "source_country": detect_country(url),
        "source_class":   source_class,
        "url":            url,
        "scraped_date":   datetime.now().strftime("%Y-%m-%d"),
        "publish_date":   "",
        "title":          title,
        "word_count":     len(body.split()) if body else 0,
        "full_text":      body or "",
        "subject_name":   subj["subject_name"],
        "subject_age":    subj["subject_age"],
        "subject_city":   subj["subject_city"],
        "subject_country":subj["subject_country"],
        "ages_mentioned": ages,
        "max_age":        max_age,
        "stat_odds_ratio":          stats.get("odds_ratio", ""),
        "stat_hazard_ratio":        stats.get("hazard_ratio", ""),
        "stat_sample_size":         stats.get("sample_size", ""),
        "stat_percentage":          stats.get("percentage", ""),
        "stat_p_value":             stats.get("p_value", ""),
        "stat_confidence_interval": stats.get("confidence_interval", ""),
        "has_age":   bool(ages),
        "has_stats": bool(stats),
        "is_centenarian_profile": any(
            kw in full.lower() for kw in
            ["centenarian", "100-year-old", "100 year old",
             "supercentenarian", "lives to 100",
             "centenaire", "centenario", "百寿", "百岁"]),
    }
    rec.update(cols)
    return rec


def process_url(url, search_title, search_snippet, source_class, out_path,
                done, hdr_ref, counts):
    if not url or url in done:
        return False
    skip_domains = [
        "youtube.com", "facebook.com", "twitter.com", "instagram.com",
        "linkedin.com", "pinterest.com", "reddit.com", "tiktok.com",
        "amazon.com", "ebay.com", "wikipedia.org",
    ]
    if any(d in url.lower() for d in skip_domains):
        return False

    title, body = fetch_article(url)
    if not title:
        title = search_title
    if body and len(body.split()) < MIN_WORD_COUNT and search_snippet:
        body = body + " " + search_snippet

    if not body or len(body.split()) < 50:
        counts["no_text"] += 1
        return False
    if not content_ok((title or "") + " " + body):
        counts["not_relevant"] += 1
        return False

    rec = build_record(url, title, body, source_class)
    save_rec(rec, out_path, hdr_ref[0])
    hdr_ref[0] = False
    done.add(url)
    counts["saved"] += 1
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Pass 1: obituary scraper
# ─────────────────────────────────────────────────────────────────────────────

def pass_obituary(done, hdr_ref, counts):
    print("\n" + "=" * 76)
    print("  PASS 1: OBITUARY SCRAPER — 9 targeted queries")
    print("=" * 76)
    for qi, (label, query, region) in enumerate(OBITUARY_QUERIES, 1):
        print(f"\n[{qi}/{len(OBITUARY_QUERIES)}] {label} ({region})")
        print(f"  Q: {query}")
        try:
            results = search_ddg(query, region, max_results=RESULTS_PER_QUERY)
        except Exception as e:
            print(f"  ! search error: {e}")
            results = []
        print(f"  -> {len(results)} results")
        before = counts["saved"]
        for i, r in enumerate(results, 1):
            url = r.get("href", "") or r.get("url", "")
            ok  = process_url(
                url, r.get("title", ""), r.get("body", ""),
                "obituary", OUT_PATH, done, hdr_ref, counts,
            )
            if ok:
                print(f"    [{i}] saved: {url[:80]}")
            time.sleep(DELAY_BETWEEN_ARTICLES)
        print(f"  +{counts['saved'] - before} new")
        time.sleep(DELAY_BETWEEN_SEARCHES)


# ─────────────────────────────────────────────────────────────────────────────
# Pass 2: oral history archives
# ─────────────────────────────────────────────────────────────────────────────

def pass_oral_history(done, hdr_ref, counts):
    print("\n" + "=" * 76)
    print("  PASS 2: ORAL HISTORY ARCHIVES")
    print("=" * 76)

    # 2a. Library of Congress JSON API
    print("\n  2a. Library of Congress (loc.gov JSON API)")
    try:
        loc_resp = requests.get(
            "https://www.loc.gov/search/",
            params={"q": "centenarian", "fo": "json", "c": "100"},
            headers=HEADERS, timeout=60,
        )
        loc_resp.raise_for_status()
        loc_data = loc_resp.json()
        items = loc_data.get("results", [])
        print(f"     {len(items)} items returned by LOC search")
        for i, item in enumerate(items, 1):
            url = item.get("id") or item.get("url") or ""
            title = item.get("title", "")
            descs = item.get("description") or []
            if isinstance(descs, list):
                body = " ".join(d for d in descs if isinstance(d, str))
            else:
                body = str(descs or "")
            body = body.strip()
            if not body or len(body.split()) < 30:
                # Try to enrich by fetching the item page
                fetched_title, fetched_body = fetch_article(url) if url else ("", "")
                if fetched_body and len(fetched_body.split()) >= 50:
                    title = fetched_title or title
                    body  = fetched_body
            ok = process_url(
                url, title, body, "oral_history",
                OUT_PATH, done, hdr_ref, counts,
            )
            if ok:
                print(f"     [{i}] LOC saved: {url[:80]}")
            time.sleep(0.5)
    except Exception as e:
        print(f"     ! LOC error: {e}")

    # 2b. StoryCorps HTML scrape — search page lists story snippets
    print("\n  2b. StoryCorps (storycorps.org HTML)")
    try:
        sc_resp = requests.get(
            "https://storycorps.org/stories/",
            params={"s": "centenarian"},
            headers=HEADERS, timeout=30,
        )
        sc_resp.raise_for_status()
        sc_soup = BeautifulSoup(sc_resp.text, "html.parser")
        # Story cards typically link to /stories/{slug}/
        story_links = set()
        for a in sc_soup.find_all("a", href=True):
            href = a["href"]
            if "/stories/" in href and href != "/stories/" and not href.startswith("#"):
                if href.startswith("/"):
                    href = "https://storycorps.org" + href
                story_links.add(href)
        story_links.discard("https://storycorps.org/stories/")
        print(f"     {len(story_links)} story links discovered")
        for i, url in enumerate(sorted(story_links)[:30], 1):
            title, body = fetch_article(url)
            ok = process_url(
                url, title, body, "oral_history",
                OUT_PATH, done, hdr_ref, counts,
            )
            if ok:
                print(f"     [{i}] StoryCorps saved: {url[:80]}")
            time.sleep(1.0)
    except Exception as e:
        print(f"     ! StoryCorps error: {e}")

    # 2c. 100yearoldclub.com — try to fetch homepage and discover article URLs
    print("\n  2c. 100yearoldclub.com")
    try:
        r = requests.get("https://www.100yearoldclub.com",
                         headers=HEADERS, timeout=30)
        if r.status_code != 200:
            print(f"     site returned HTTP {r.status_code} — skipping")
        else:
            soup = BeautifulSoup(r.text, "html.parser")
            urls = set()
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("/"):
                    href = "https://www.100yearoldclub.com" + href
                if "100yearoldclub.com" in href and href != "https://www.100yearoldclub.com/":
                    urls.add(href)
            print(f"     {len(urls)} internal links discovered")
            for i, url in enumerate(sorted(urls)[:30], 1):
                title, body = fetch_article(url)
                ok = process_url(
                    url, title, body, "oral_history",
                    OUT_PATH, done, hdr_ref, counts,
                )
                if ok:
                    print(f"     [{i}] 100yearoldclub saved: {url[:80]}")
                time.sleep(1.0)
    except Exception as e:
        print(f"     ! 100yearoldclub error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Pass 3: regional/local search
# ─────────────────────────────────────────────────────────────────────────────

def pass_regional(done, hdr_ref, counts):
    print("\n" + "=" * 76)
    print(f"  PASS 3: REGIONAL/LOCAL SEARCH — "
          f"{len(REGIONAL_QUERY_TEMPLATES)} queries x {len(REGIONAL_REGIONS)} regions")
    print("=" * 76)
    for region in REGIONAL_REGIONS:
        for qi, (label, query) in enumerate(REGIONAL_QUERY_TEMPLATES, 1):
            print(f"\n[{region}] [{qi}/{len(REGIONAL_QUERY_TEMPLATES)}] {label}")
            print(f"  Q: {query}")
            try:
                results = search_ddg(query, region, max_results=RESULTS_PER_QUERY)
            except Exception as e:
                print(f"  ! search error: {e}")
                results = []
            print(f"  -> {len(results)} results")
            before = counts["saved"]
            for i, r in enumerate(results, 1):
                url = r.get("href", "") or r.get("url", "")
                ok = process_url(
                    url, r.get("title", ""), r.get("body", ""),
                    "regional_local", OUT_PATH, done, hdr_ref, counts,
                )
                if ok:
                    print(f"    [{i}] saved: {url[:80]}")
                time.sleep(DELAY_BETWEEN_ARTICLES)
            print(f"  +{counts['saved'] - before} new")
            time.sleep(DELAY_BETWEEN_SEARCHES)


# ─────────────────────────────────────────────────────────────────────────────
# Driver
# ─────────────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Output:   {OUT_PATH}")

    done = load_done(OUT_PATH)
    print(f"Existing URLs in news_articles.csv: {len(done):,}")
    hdr_ref = [len(done) == 0]
    counts  = {"saved": 0, "no_text": 0, "not_relevant": 0}

    try:
        pass_obituary(done, hdr_ref, counts)
        pass_oral_history(done, hdr_ref, counts)
        pass_regional(done, hdr_ref, counts)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user — progress saved")

    print("\n" + "=" * 76)
    print(f"  SUMMARY")
    print("=" * 76)
    print(f"  Saved this run: {counts['saved']:,}")
    print(f"  Skipped (no text):   {counts['no_text']:,}")
    print(f"  Skipped (off-topic): {counts['not_relevant']:,}")
    if os.path.exists(OUT_PATH):
        df = pd.read_csv(OUT_PATH, low_memory=False)
        print(f"  Total news_articles.csv rows now: {len(df):,}")
        if "source_class" in df.columns:
            print(f"  By source_class:")
            for cls, n in df["source_class"].value_counts().items():
                print(f"    {cls:<22} {n:>6}")


if __name__ == "__main__":
    main()
