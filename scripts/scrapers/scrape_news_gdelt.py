"""
================================================================================
REJUVE LONGEVITY APP — Centenarian Data Pipeline
FILE: scraper_gdelt.py
VERSION: 1.0
PURPOSE: Uses GDELT (Global Database of Events, Language, and Tone) to find
         centenarian/longevity articles from global news sources.

WHY GDELT:
  - Completely free, no registration, no API key, no rate limits
  - Indexes global news from 200+ countries in 100+ languages
  - DOC API returns article URLs + metadata for keyword searches
  - Coverage from ~2017 to present
  - Bypasses all bot detection issues since GDELT already crawled the articles

HOW IT WORKS:
  1. Queries GDELT DOC API with centenarian-related search terms
  2. Gets article URLs, titles, sources, dates, and preview text
  3. Fetches full article text from each URL where possible
  4. Falls back to GDELT preview text if full fetch fails (paywalls etc.)
  5. Extracts features using same pipeline as other scrapers
  6. Saves to same CSV as other news scrapers (deduplication built in)

OUTPUT: data/raw/news_articles.csv (same file, appends to existing data)

DEPENDENCIES: pip install requests beautifulsoup4 pandas
AUTHOR: Rejuve Longevity (open-source)
LICENSE: MIT
================================================================================
"""

import time, re, os, csv, json
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta

# ================================================================================
# CONFIGURATION
# ================================================================================

OUTPUT_DIR  = "data/raw"
OUTPUT_FILE = "news_articles.csv"

DELAY_BETWEEN_ARTICLES = 1.5
DELAY_BETWEEN_QUERIES  = 2.0

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}

# Minimum word count for full-text articles
MIN_WORD_COUNT_FULL = 150
# Minimum word count for GDELT preview-only articles (shorter but still useful)
MIN_WORD_COUNT_PREVIEW = 30

# GDELT DOC API base URL
GDELT_API = "https://api.gdeltproject.org/api/v2/doc/doc"

# GDELT returns max 250 articles per query.
# We use time-sliced queries to get more total coverage.
GDELT_MAX_RECORDS = 250

# ================================================================================
# SEARCH QUERIES
# ================================================================================
# GDELT searches across all indexed global news sources simultaneously.
# Each query returns up to 250 articles. We combine multiple queries
# with different terms and time windows to maximize coverage.
#
# GDELT query syntax:
#   - Regular words are AND by default
#   - Quotes for exact phrases
#   - OR for alternatives
#   - sourcelang: filters by language
#   - sourcecountry: filters by country code

QUERIES = [
    # ── English core terms ────────────────────────────────────────────────
    ("en_centenarian",          '"centenarian"'),
    ("en_supercentenarian",     '"supercentenarian"'),
    ("en_100_year_old_secret",  '"100-year-old" secret'),
    ("en_100_year_old_tips",    '"100-year-old" tips longevity'),
    ("en_100_year_old_life",    '"100 year old" long life'),
    ("en_oldest_person",        '"oldest person" alive'),
    ("en_oldest_woman",         '"oldest woman" world'),
    ("en_oldest_man",           '"oldest man" world'),
    ("en_longevity_secret",     'longevity secret centenarian'),
    ("en_blue_zone",            '"blue zone" longevity'),
    ("en_blue_zones",           '"blue zones"'),
    ("en_live_to_100",          '"live to 100"'),
    ("en_turned_100",           '"turned 100" birthday'),
    ("en_celebrated_100",       'celebrated 100th birthday'),
    ("en_101_years_old",        '"101 years old"'),
    ("en_102_years_old",        '"102 years old"'),
    ("en_103_years_old",        '"103 years old"'),
    ("en_104_years_old",        '"104 years old"'),
    ("en_105_years_old",        '"105 years old"'),
    ("en_106_plus",             '"106 years old" OR "107 years old" OR "108 years old"'),
    ("en_109_plus",             '"109 years old" OR "110 years old" OR "111 years old"'),
    ("en_112_plus",             '"112 years old" OR "113 years old" OR "114 years old"'),
    ("en_115_plus",             '"115 years old" OR "116 years old" OR "117 years old"'),
    ("en_longevity_habits",     'longevity habits healthy aging'),
    ("en_centenarian_diet",     'centenarian diet'),
    ("en_centenarian_exercise", 'centenarian exercise'),
    ("en_centenarian_secret",   'centenarian secret long life'),
    ("en_okinawa_longevity",    'Okinawa longevity'),
    ("en_sardinia_longevity",   'Sardinia longevity centenarian'),
    ("en_ikaria_longevity",     'Ikaria longevity'),
    ("en_nicoya_longevity",     'Nicoya longevity'),
    ("en_loma_linda_longevity", '"Loma Linda" longevity'),

    # ── French ────────────────────────────────────────────────────────────
    ("fr_centenaire",           'centenaire sourcelang:french'),
    ("fr_centenaire_secret",    'centenaire secret longévité sourcelang:french'),
    ("fr_doyenne",              'doyenne humanité sourcelang:french'),
    ("fr_100_ans",              '"100 ans" longévité sourcelang:french'),

    # ── Spanish ───────────────────────────────────────────────────────────
    ("es_centenario",           'centenario longevidad sourcelang:spanish'),
    ("es_centenaria",           'centenaria secreto sourcelang:spanish'),
    ("es_100_anos",             '"100 años" vida sourcelang:spanish'),

    # ── German ────────────────────────────────────────────────────────────
    ("de_hundertjaehrige",      'Hundertjährige Langlebigkeit sourcelang:german'),
    ("de_100_jahre",            '"100 Jahre" Geheimnis sourcelang:german'),

    # ── Italian ───────────────────────────────────────────────────────────
    ("it_centenario",           'centenario longevità sourcelang:italian'),
    ("it_centenaria",           'centenaria segreto sourcelang:italian'),
    ("it_sardegna",             'centenario Sardegna sourcelang:italian'),

    # ── Portuguese ────────────────────────────────────────────────────────
    ("pt_centenario",           'centenário longevidade sourcelang:portuguese'),
    ("pt_100_anos",             '"100 anos" segredo vida sourcelang:portuguese'),

    # ── Japanese ──────────────────────────────────────────────────────────
    ("ja_centenarian",          '百寿者 sourcelang:japanese'),
    ("ja_longevity",            '長寿 沖縄 sourcelang:japanese'),

    # ── Korean ────────────────────────────────────────────────────────────
    ("ko_centenarian",          '백세 장수 sourcelang:korean'),

    # ── Dutch ─────────────────────────────────────────────────────────────
    ("nl_honderdjarige",        'honderdjarige levensduur sourcelang:dutch'),

    # ── Swedish ───────────────────────────────────────────────────────────
    ("sv_hundraaring",          'hundraåring sourcelang:swedish'),

    # ── Danish ────────────────────────────────────────────────────────────
    ("da_hundredaarig",         'hundredårig sourcelang:danish'),

    # ── Greek ─────────────────────────────────────────────────────────────
    ("el_centenarian",          'εκατοντάρης sourcelang:greek'),

    # ── Arabic ────────────────────────────────────────────────────────────
    ("ar_centenarian",          'معمر sourcelang:arabic'),

    # ── Hindi ─────────────────────────────────────────────────────────────
    ("hi_centenarian",          'शतायु sourcelang:hindi'),

    # ── Chinese ───────────────────────────────────────────────────────────
    ("zh_centenarian",          '百岁老人 sourcelang:chinese'),

    # ── Russian ───────────────────────────────────────────────────────────
    ("ru_centenarian",          'долгожитель sourcelang:russian'),

    # ── Turkish ───────────────────────────────────────────────────────────
    ("tr_centenarian",          'asırlık sourcelang:turkish'),
]

# Time windows — GDELT returns max 250 per query, so we slice by year
# to get more total coverage
TIME_WINDOWS = [
    ("2017-2018", "20170101000000", "20181231235959"),
    ("2019",      "20190101000000", "20191231235959"),
    ("2020",      "20200101000000", "20201231235959"),
    ("2021",      "20210101000000", "20211231235959"),
    ("2022",      "20220101000000", "20221231235959"),
    ("2023",      "20230101000000", "20231231235959"),
    ("2024",      "20240101000000", "20241231235959"),
    ("2025-2026", "20250101000000", "20261231235959"),
]

# ================================================================================
# KEYWORD MAPS — identical to other scrapers
# ================================================================================

KW_PHYSICAL = [
    "exercise", "swim", "swimming", "walk", "walking", "gym", "workout",
    "yoga", "dance", "dancing", "active", "movement", "zumba", "cardio",
    "strength training", "cycling", "gardening", "hiking", "tai chi",
    "sedentary", "run", "running", "physical activity",
]
KW_DIET = [
    "vegetable", "vegetables", "plant-based", "plant based", "mediterranean",
    "olive oil", "legume", "legumes", "fruit", "fruits", "diet", "nutrition",
    "calorie", "alcohol", "smoking", "whole food", "processed food",
    "sugar", "red wine", "fasting", "protein", "fiber", "fibre",
    "antioxidant", "vegetarian", "vegan", "fermented", "probiotic", "omega-3",
]
KW_SOCIAL = [
    "social", "community", "family", "friend", "friends", "church", "faith",
    "religion", "volunteer", "moai", "belonging", "connection",
    "loneliness", "isolated", "marriage", "married",
]
KW_PURPOSE = [
    "purpose", "ikigai", "positive", "optimis", "grateful", "gratitude",
    "stress", "meaning", "passion", "attitude", "mindset", "resilience",
    "happiness", "humor", "laughter", "mental health", "cognitive",
    "curiosity", "retired", "retirement", "working",
]
KW_SLEEP = [
    "sleep", "rest", "nap", "siesta", "insomnia", "circadian", "melatonin",
]
KW_BIO_INFLAMMATION = [
    "inflammation", "inflammatory", "crp", "c-reactive", "il-6",
    "interleukin", "tnf", "cytokine", "inflammaging",
]
KW_BIO_GLUCOSE = [
    "glucose", "insulin", "hba1c", "blood sugar", "diabetes",
    "metabolic syndrome", "insulin resistance",
]
KW_BIO_LIPIDS = [
    "cholesterol", "triglyceride", "hdl", "ldl", "lipid", "lipids",
]
KW_BIO_IGF1 = [
    "igf-1", "igf1", "insulin-like growth factor", "growth hormone", "mtor",
]
KW_BIO_TELOMERES = ["telomere", "telomeres", "telomerase"]
KW_BIO_EPIGENETIC = [
    "epigenetic", "methylation", "dna methylation", "biological age",
    "epigenetic clock",
]
KW_BIO_MICROBIOME = ["microbiome", "gut bacteria", "gut microbiota"]
KW_BIO_HORMONES = [
    "cortisol", "testosterone", "estrogen", "dhea", "thyroid", "hormone",
]
KW_BIO_FUNCTIONAL = [
    "grip strength", "gait speed", "vo2 max", "frailty", "sarcopenia",
    "muscle mass",
]
KW_BIO_METABOLOMIC = [
    "metabolomics", "bile acid", "bile acids", "metabolite",
]
KW_GENE_APOE = ["apoe", "apolipoprotein e", "apoe4", "apoe2"]
KW_GENE_FOXO3 = ["foxo3", "foxo3a", "forkhead box"]
KW_GENE_CETP = ["cetp", "cholesteryl ester transfer"]
KW_GENE_KLOTHO = ["klotho", "kl-vs"]
KW_GENE_OTHER = [
    "sirt1", "sirtuin", "gwas", "genome-wide", "polymorphism", "snp",
    "genetic variant", "heritability",
]

STAT_PATTERNS = {
    "odds_ratio":          r'(?:OR|odds ratio)\s*[=:]?\s*(\d+\.?\d*)',
    "hazard_ratio":        r'(?:HR|hazard ratio)\s*[=:]?\s*(\d+\.?\d*)',
    "sample_size":         r'(?:n\s*=\s*|studied\s+|enrolled\s+|sample of\s+)(\d[\d,]+)',
    "percentage":          r'(\d+\.?\d*)\s*(?:%|percent)',
    "p_value":             r'p\s*[<=]\s*(0\.\d+)',
    "confidence_interval": r'(?:95%\s*CI|confidence interval)[^\d]*(\d+\.?\d*)[^\d]+(\d+\.?\d*)',
}

# ================================================================================
# HELPERS
# ================================================================================

def _has(tl, kws):
    return any(kw in tl for kw in kws)

def extract_columns(text):
    tl = text.lower()
    return {
        "trait_physical_activity":  _has(tl, KW_PHYSICAL),
        "trait_diet":              _has(tl, KW_DIET),
        "trait_social":            _has(tl, KW_SOCIAL),
        "trait_purpose_psychology": _has(tl, KW_PURPOSE),
        "trait_sleep":             _has(tl, KW_SLEEP),
        "biomarker_inflammation":  _has(tl, KW_BIO_INFLAMMATION),
        "biomarker_glucose":       _has(tl, KW_BIO_GLUCOSE),
        "biomarker_lipids":        _has(tl, KW_BIO_LIPIDS),
        "biomarker_igf1":          _has(tl, KW_BIO_IGF1),
        "biomarker_telomeres":     _has(tl, KW_BIO_TELOMERES),
        "biomarker_epigenetic":    _has(tl, KW_BIO_EPIGENETIC),
        "biomarker_microbiome":    _has(tl, KW_BIO_MICROBIOME),
        "biomarker_hormones":      _has(tl, KW_BIO_HORMONES),
        "biomarker_functional":    _has(tl, KW_BIO_FUNCTIONAL),
        "biomarker_metabolomic":   _has(tl, KW_BIO_METABOLOMIC),
        "gene_apoe":               _has(tl, KW_GENE_APOE),
        "gene_foxo3":              _has(tl, KW_GENE_FOXO3),
        "gene_cetp":               _has(tl, KW_GENE_CETP),
        "gene_klotho":             _has(tl, KW_GENE_KLOTHO),
        "gene_other":              _has(tl, KW_GENE_OTHER),
    }

def extract_stats(text):
    st = {}
    for nm, pat in STAT_PATTERNS.items():
        ms = re.findall(pat, text, re.IGNORECASE)
        if ms:
            fl = [str(m) if isinstance(m, str) else "|".join(m) for m in ms]
            st[nm] = "; ".join(fl[:5])
    return st

def extract_ages(text):
    raw = re.findall(r'\b(1[0-2][0-9]|[89][0-9])\b', text)
    u = sorted(set(int(a) for a in raw if 85 <= int(a) <= 130))
    return ",".join(str(a) for a in u) if u else ""

def extract_subject(title, body):
    c = title + " " + body[:800]
    name = ""
    m = re.search(r'([A-Z][a-z]+\s+[A-Z][a-z]+),?\s*(?:age\s*)?(\d{2,3})', c)
    if m and 85 <= int(m.group(2)) <= 130:
        name = m.group(1)
    else:
        m = re.search(r'(\d{3})-?year-?old\s+([A-Z][a-z]+\s+[A-Z][a-z]+)', c)
        if m and 85 <= int(m.group(1)) <= 130:
            name = m.group(2)
    age = ""
    am = re.findall(r'\b(1[0-2][0-9])\b', title)
    if am: age = am[0]
    city = country = ""
    lm = re.search(
        r'(?:of|from|in|lives? in|based in)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)'
        r'(?:,\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?))?', c)
    if lm:
        city = lm.group(1) or ""
        country = lm.group(2) or ""
    return {"subject_name":name, "subject_age":age,
            "subject_city":city, "subject_country":country}

CONTENT_KEYWORDS = [
    "centenarian", "supercentenarian", "100 year", "100-year",
    "longevity", "live to 100", "oldest living", "long life",
    "live longer", "blue zone", "exceptional longevity",
    # Non-English equivalents for basic filtering
    "centenaire", "centenario", "centenária", "hundertjährig",
    "百寿", "百岁", "백세", "долгожитель",
]

def content_ok(text):
    tl = text.lower()
    return any(kw in tl for kw in CONTENT_KEYWORDS)

# ================================================================================
# GDELT API
# ================================================================================

def gdelt_search(query, start_date=None, end_date=None):
    """
    Query GDELT DOC API. Returns list of article dicts.
    Each dict has: url, title, source_name, source_country, pub_date, preview
    """
    params = {
        "query": query,
        "mode": "artlist",
        "maxrecords": GDELT_MAX_RECORDS,
        "format": "json",
        "sort": "datedesc",
    }
    if start_date:
        params["startdatetime"] = start_date
    if end_date:
        params["enddatetime"] = end_date

    try:
        r = requests.get(GDELT_API, params=params, timeout=30)
        if r.status_code != 200:
            print(f"    ✗ GDELT returned status {r.status_code}")
            return []

        data = r.json()
        articles = data.get("articles", [])
        if not articles:
            return []

        results = []
        for art in articles:
            results.append({
                "url":            art.get("url", ""),
                "title":          art.get("title", ""),
                "source_name":    art.get("domain", ""),
                "source_country": art.get("sourcecountry", ""),
                "language":       art.get("language", ""),
                "pub_date":       art.get("seendate", ""),
                "preview":        art.get("title", ""),  # GDELT artlist mode gives title only
            })
        return results

    except json.JSONDecodeError:
        print(f"    ✗ GDELT returned non-JSON response")
        return []
    except Exception as e:
        print(f"    ✗ GDELT error: {e}")
        return []


def fetch_article_text(url):
    """
    Fetch full article text from URL using requests + BeautifulSoup.
    Returns (title, body_text) or ("", "") on failure.
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=12, allow_redirects=True)
        if r.status_code != 200:
            return "", ""

        soup = BeautifulSoup(r.text, "html.parser")

        # Remove script, style, nav elements
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()

        # Title
        title = ""
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)

        # Body — all paragraphs
        paragraphs = soup.find_all("p")
        body = " ".join(
            p.get_text(strip=True) for p in paragraphs
            if len(p.get_text(strip=True)) > 20  # skip tiny nav/footer paragraphs
        )

        return title, body

    except Exception:
        return "", ""


# ================================================================================
# COUNTRY CODE MAPPING
# ================================================================================
# GDELT returns 2-letter FIPS country codes, not country names.
# Map the most common ones to readable names.

FIPS_TO_COUNTRY = {
    "US": "USA", "UK": "UK", "CA": "Canada", "AS": "Australia",
    "NZ": "New Zealand", "IN": "India", "CH": "China", "JA": "Japan",
    "KS": "South Korea", "GM": "Germany", "FR": "France", "SP": "Spain",
    "IT": "Italy", "NL": "Netherlands", "SW": "Sweden", "DA": "Denmark",
    "FI": "Finland", "NO": "Norway", "PO": "Portugal", "GR": "Greece",
    "BE": "Belgium", "EI": "Ireland", "TU": "Turkey", "IS": "Israel",
    "SA": "Saudi Arabia", "AE": "UAE", "QA": "Qatar", "PK": "Pakistan",
    "SF": "South Africa", "NI": "Nigeria", "KE": "Kenya", "BR": "Brazil",
    "AR": "Argentina", "MX": "Mexico", "CI": "Chile", "CO": "Colombia",
    "PE": "Peru", "SN": "Singapore", "TH": "Thailand", "MY": "Malaysia",
    "ID": "Indonesia", "VM": "Vietnam", "RP": "Philippines",
    "RS": "Russia", "PL": "Poland", "HU": "Hungary", "RO": "Romania",
    "EZ": "Czech Republic", "AU": "Austria", "SZ": "Switzerland",
    "CU": "Cuba", "CS": "Costa Rica", "BL": "Bolivia",
    "HK": "Hong Kong", "TW": "Taiwan",
}

def fips_to_country(code):
    if not code: return "Unknown"
    return FIPS_TO_COUNTRY.get(code.strip().upper(), code)

# ================================================================================
# SAVE
# ================================================================================

def load_done(path):
    if not os.path.exists(path): return set()
    try: return set(pd.read_csv(path, usecols=["url"])["url"].dropna().tolist())
    except: return set()

def save_rec(rec, path, hdr):
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rec.keys())
        if hdr: w.writeheader()
        w.writerow(rec)

# ================================================================================
# MAIN
# ================================================================================

def run():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    done = load_done(out)
    hdr = len(done) == 0
    session_saved = 0
    full_text_count = 0
    preview_only_count = 0

    total_combos = len(QUERIES) * len(TIME_WINDOWS)

    print("="*70)
    print("  REJUVE LONGEVITY — GDELT News Scraper v1.0")
    print(f"  Queries:        {len(QUERIES)}")
    print(f"  Time windows:   {len(TIME_WINDOWS)}")
    print(f"  Total searches: {total_combos}")
    print(f"  Output:         {out}")
    print(f"  Resuming:       {len(done)} URLs already collected")
    print("="*70)

    combo_num = 0

    try:
        for qi, (label, query) in enumerate(QUERIES):
            for ti, (tw_label, tw_start, tw_end) in enumerate(TIME_WINDOWS):
                combo_num += 1
                print(f"\n{'─'*70}")
                print(f"[{combo_num}/{total_combos}] {label} | {tw_label}")
                print(f"{'─'*70}")

                articles = gdelt_search(query, tw_start, tw_end)
                print(f"  → {len(articles)} GDELT results")

                if not articles:
                    time.sleep(DELAY_BETWEEN_QUERIES)
                    continue

                batch_saved = 0
                for i, art in enumerate(articles):
                    url = art["url"]
                    if not url or url in done:
                        continue

                    print(f"  [{i+1}/{len(articles)}] ", end="", flush=True)

                    # Try to fetch full article text
                    title, body = fetch_article_text(url)
                    used_preview = False

                    # Use GDELT title if we didn't get one
                    if not title:
                        title = art["title"]

                    # If full text fetch failed or too short, use preview
                    if len(body.split()) < MIN_WORD_COUNT_FULL:
                        if art["preview"] and len(art["preview"].split()) >= MIN_WORD_COUNT_PREVIEW:
                            body = art["preview"]
                            used_preview = True
                        elif len(body.split()) < MIN_WORD_COUNT_PREVIEW:
                            print("✗ no text")
                            continue

                    # Content relevance check
                    if not content_ok(title + " " + body):
                        print("✗ not relevant")
                        continue

                    # Extract everything
                    full = title + " " + body
                    ages = extract_ages(full)
                    stats = extract_stats(body)
                    cols = extract_columns(body)
                    subj = extract_subject(title, body)
                    max_age = str(max(int(a) for a in ages.split(","))) if ages else ""

                    country = fips_to_country(art["source_country"])

                    rec = {
                        "source_name":    art["source_name"] or "Unknown",
                        "source_country": country,
                        "source_class":   "gdelt",
                        "url":            url,
                        "scraped_date":   datetime.now().strftime("%Y-%m-%d"),
                        "publish_date":   art["pub_date"],
                        "title":          title,
                        "word_count":     len(body.split()),
                        "full_text":      body,
                        "subject_name":   subj["subject_name"],
                        "subject_age":    subj["subject_age"],
                        "subject_city":   subj["subject_city"],
                        "subject_country":subj["subject_country"],
                        "ages_mentioned": ages,
                        "max_age":        max_age,
                        "stat_odds_ratio":         stats.get("odds_ratio",""),
                        "stat_hazard_ratio":       stats.get("hazard_ratio",""),
                        "stat_sample_size":        stats.get("sample_size",""),
                        "stat_percentage":         stats.get("percentage",""),
                        "stat_p_value":            stats.get("p_value",""),
                        "stat_confidence_interval":stats.get("confidence_interval",""),
                        "has_age":   bool(ages),
                        "has_stats": bool(stats),
                        "is_centenarian_profile": any(
                            kw in full.lower() for kw in
                            ["centenarian","100-year-old","100 year old",
                             "supercentenarian","lives to 100",
                             "centenaire","centenario","百寿","百岁"]),
                    }
                    rec.update(cols)

                    save_rec(rec, out, hdr)
                    hdr = False
                    done.add(url)
                    session_saved += 1
                    batch_saved += 1

                    if used_preview:
                        preview_only_count += 1
                    else:
                        full_text_count += 1

                    # Concise output
                    age_s = f"age={rec['subject_age']}" if rec['subject_age'] else (
                            f"max={rec['max_age']}" if rec['max_age'] else "no age")
                    nm = rec['subject_name'] or ""
                    pv = " 📋preview" if used_preview else ""
                    src = art['source_name'][:20] if art['source_name'] else ""
                    print(f"✓ [{src}] {title[:30]}... [{nm} {age_s}{pv}]")

                    time.sleep(DELAY_BETWEEN_ARTICLES)

                print(f"\n  ✓ {batch_saved} saved from this query+window")
                time.sleep(DELAY_BETWEEN_QUERIES)

    except KeyboardInterrupt:
        print("\n\n⚠ Interrupted — progress saved")

    # Summary
    print(f"\n{'='*70}")
    print(f"  DONE | Session: {session_saved} new articles")
    print(f"  Full text: {full_text_count} | Preview only: {preview_only_count}")
    print(f"{'='*70}")

    if os.path.exists(out):
        df = pd.read_csv(out)
        gd = df[df["source_class"] == "gdelt"]

        print(f"\n  TOTAL IN COMBINED CSV: {len(df)} articles")
        print(f"  From GDELT: {len(gd)}")

        if len(gd) > 0:
            print(f"\n  GDELT TOP SOURCES:")
            for s, c in gd["source_name"].value_counts().head(20).items():
                print(f"    {s:<40} {c}")
            print(f"\n  GDELT COUNTRIES:")
            for co, c in gd["source_country"].value_counts().head(20).items():
                print(f"    {co:<25} {c}")
            print(f"\n  GDELT CENTENARIAN PROFILES: {gd['is_centenarian_profile'].sum()}")
            print(f"  GDELT WITH AGE MENTIONS: {gd['has_age'].sum()}")

        print(f"\n  FILE: {out}")


if __name__ == "__main__":
    run()
