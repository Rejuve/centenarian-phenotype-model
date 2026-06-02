"""
================================================================================
REJUVE LONGEVITY APP — Centenarian Data Pipeline
FILE: scraper_search.py
VERSION: 1.0
PURPOSE: Searches the web for centenarian/longevity articles using DuckDuckGo,
         exactly like a human would — search, get results, follow links, read.

WHY THIS APPROACH:
  Every other approach failed or underperformed:
    - Selenium: blocked by bot detection on most sites
    - Google News RSS: redirect URLs couldn't be resolved
    - GDELT API: only 2017+ coverage, many "no text" failures
    - BigQuery: complex setup, poor results for our use case

  This scraper does what a human does:
    1. Search DuckDuckGo for centenarian-related queries
    2. Get real article URLs from results
    3. Visit each URL and extract the text
    4. Save structured data

  DuckDuckGo doesn't block automated searches and returns
  quality results from all major global news sources.

OUTPUT: data/raw/news_articles.csv (same file, appends to existing)
DEPENDENCIES: pip install duckduckgo-search requests beautifulsoup4 pandas
AUTHOR: Rejuve Longevity (open-source)
LICENSE: MIT
================================================================================
"""

import time, re, os, csv
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
try:
    from ddgs import DDGS                  # new package name (>=9.x)
except ImportError:
    from duckduckgo_search import DDGS    # legacy fallback

# ================================================================================
# CONFIGURATION
# ================================================================================

OUTPUT_DIR  = "data/raw"
OUTPUT_FILE = "news_articles.csv"

DELAY_BETWEEN_ARTICLES = 1.5
DELAY_BETWEEN_SEARCHES = 3.0

# Max results per search query — DuckDuckGo returns up to ~200-300 per query
MAX_RESULTS_PER_QUERY = 200

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}

MIN_WORD_COUNT = 150

# ================================================================================
# SEARCH QUERIES
# ================================================================================
# Designed to catch every variation of how centenarian articles are written.
# Each query is a tuple: (label, search_string, region)
# region: "wt-wt" = worldwide, or specific like "us-en", "uk-en", "au-en"
#
# DuckDuckGo supports standard search operators:
#   "exact phrase"
#   OR between terms
#   site:domain.com
# ================================================================================

QUERIES = [

    # ── Core centenarian searches — worldwide ────────────────────────────

    ("centenarian",                 "centenarian",                              "wt-wt"),
    ("centenarian_secret",          "centenarian secret long life",             "wt-wt"),
    ("centenarian_tips",            "centenarian tips longevity",               "wt-wt"),
    ("centenarian_interview",       "centenarian interview habits",             "wt-wt"),
    ("centenarian_diet",            "centenarian diet what they eat",           "wt-wt"),
    ("centenarian_exercise",        "centenarian exercise routine daily",       "wt-wt"),
    ("supercentenarian",            "supercentenarian",                         "wt-wt"),
    ("supercentenarian_interview",  "supercentenarian interview life",          "wt-wt"),

    # ── Age-specific searches ────────────────────────────────────────────
    # These catch the "Woman, 103, shares her secrets" headline format

    ("100_year_old_secrets",     '"100-year-old" secrets longevity',          "wt-wt"),
    ("100_year_old_tips",        '"100-year-old" tips long life',             "wt-wt"),
    ("100_year_old_diet",        '"100-year-old" diet exercise',              "wt-wt"),
    ("100_year_old_still",       '"100-year-old" still works active',         "wt-wt"),
    ("101_year_old",             '"101-year-old" longevity secret',           "wt-wt"),
    ("102_year_old",             '"102-year-old" OR "103-year-old" secret',   "wt-wt"),
    ("104_year_old",             '"104-year-old" OR "105-year-old"',          "wt-wt"),
    ("106_year_old",             '"106-year-old" OR "107-year-old" OR "108-year-old"', "wt-wt"),
    ("109_year_old",             '"109-year-old" OR "110-year-old"',          "wt-wt"),
    ("111_year_old",             '"111-year-old" OR "112-year-old" OR "113-year-old"', "wt-wt"),
    ("114_plus",                 '"114-year-old" OR "115-year-old" OR "116-year-old"', "wt-wt"),
    ("117_plus",                 '"117-year-old" OR "118-year-old" OR "119-year-old"', "wt-wt"),
    ("120_year_old",             '"120-year-old"',                            "wt-wt"),

    # ── Birthday/celebration format ──────────────────────────────────────

    ("turned_100",               '"turned 100" birthday celebration',         "wt-wt"),
    ("celebrates_100th",         '"celebrates 100th birthday"',               "wt-wt"),
    ("celebrates_101st",         '"celebrates 101st birthday" OR "celebrates 102nd birthday"', "wt-wt"),
    ("celebrates_105th",         '"celebrates 105th birthday" OR "celebrates 110th birthday"', "wt-wt"),
    ("100th_birthday_secret",    '"100th birthday" secret long life',         "wt-wt"),

    # ── "Oldest" format ──────────────────────────────────────────────────

    ("oldest_person",            '"oldest person" world alive',               "wt-wt"),
    ("oldest_person_secret",     '"oldest person" secret tips',               "wt-wt"),
    ("oldest_woman",             '"oldest woman" world shares',               "wt-wt"),
    ("oldest_man",               '"oldest man" world shares',                 "wt-wt"),
    ("oldest_living",            '"oldest living" person tips secret',        "wt-wt"),

    # ── Longevity / Blue Zone ────────────────────────────────────────────

    ("blue_zones",               '"blue zones" longevity secrets',            "wt-wt"),
    ("blue_zone_diet",           '"blue zone" diet centenarian',              "wt-wt"),
    ("live_to_100",              '"live to 100" tips habits',                 "wt-wt"),
    ("live_to_100_science",      '"live to 100" science research',            "wt-wt"),
    ("longevity_secrets",        "longevity secrets centenarians share",      "wt-wt"),
    ("longevity_habits",         "longevity habits people who live to 100",   "wt-wt"),
    ("ikigai_longevity",         "ikigai longevity purpose Okinawa",          "wt-wt"),
    ("okinawa_centenarian",      "Okinawa centenarian longevity diet",        "wt-wt"),
    ("sardinia_centenarian",     "Sardinia centenarian longevity blue zone",  "wt-wt"),
    ("nicoya_centenarian",       "Nicoya Costa Rica longevity centenarian",   "wt-wt"),
    ("loma_linda_longevity",     "Loma Linda Adventist longevity centenarian","wt-wt"),
    ("ikaria_centenarian",       "Ikaria Greece longevity centenarian",       "wt-wt"),

    # ── Regional searches — English ──────────────────────────────────────
    # Same core queries but region-locked to surface local outlets

    ("au_centenarian",           "centenarian Australia oldest secret",        "au-en"),
    ("au_100_year_old",          '"100-year-old" Australia',                   "au-en"),
    ("ca_centenarian",           "centenarian Canada oldest secret",           "ca-en"),
    ("ca_100_year_old",          '"100-year-old" Canada',                      "ca-en"),
    ("uk_centenarian",           "centenarian UK oldest secret",               "uk-en"),
    ("uk_100_year_old",          '"100-year-old" UK Britain',                  "uk-en"),
    ("in_centenarian",           "centenarian India oldest",                   "in-en"),
    ("in_100_year_old",          '"100-year-old" India longevity',             "in-en"),
    ("nz_centenarian",           "centenarian New Zealand oldest",             "nz-en"),
    ("sg_centenarian",           "centenarian Singapore longevity",            "sg-en"),
    ("za_centenarian",           "centenarian South Africa oldest",            "za-en"),
    ("ie_centenarian",           "centenarian Ireland oldest",                 "ie-en"),
    ("ng_centenarian",           "centenarian Nigeria oldest",                 "wt-wt"),
    ("ke_centenarian",           "centenarian Kenya oldest",                   "wt-wt"),
    ("ph_centenarian",           "centenarian Philippines oldest",             "wt-wt"),
    ("hk_centenarian",           "centenarian Hong Kong oldest longevity",     "wt-wt"),
    ("jp_centenarian_en",        "centenarian Japan Okinawa oldest English",   "wt-wt"),
    ("kr_centenarian_en",        "centenarian Korea oldest longevity",         "wt-wt"),
    ("il_centenarian_en",        "centenarian Israel oldest longevity",        "wt-wt"),
    ("cu_centenarian",           "centenarian Cuba oldest longevity",          "wt-wt"),

    # ── Non-English searches ─────────────────────────────────────────────

    ("fr_centenaire",            "centenaire secret longévité",               "fr-fr"),
    ("fr_centenaire_doyenne",    "doyenne humanité centenaire",               "fr-fr"),
    ("fr_100_ans",               '"100 ans" secret longévité',                "fr-fr"),
    ("de_hundertjaehrige",       "Hundertjährige Geheimnis langes Leben",     "de-de"),
    ("de_100_jahre",             '"100 Jahre alt" Langlebigkeit',             "de-de"),
    ("es_centenario",            "centenario secreto longevidad",             "es-es"),
    ("es_centenaria",            "centenaria secreto larga vida",             "es-es"),
    ("es_100_anos",              '"100 años" secreto longevidad',             "es-es"),
    ("it_centenario",            "centenario segreto longevità",              "it-it"),
    ("it_centenaria",            "centenaria Sardegna longevità",             "it-it"),
    ("pt_centenario",            "centenário segredo longevidade",            "pt-pt"),
    ("pt_br_centenario",         "centenário segredo longevidade Brasil",     "br-pt"),
    ("ja_centenarian",           "百寿者 長寿 秘訣",                            "jp-jp"),
    ("ja_okinawa",               "沖縄 長寿 百歳",                              "jp-jp"),
    ("ko_centenarian",           "백세인 장수 비결",                             "kr-kr"),
    ("nl_honderdjarige",         "honderdjarige geheim lang leven",           "nl-nl"),
    ("sv_hundraaring",           "hundraåring hemlighet långt liv",           "se-sv"),
    ("da_hundredaarig",          "hundredårig hemmelighed langt liv",         "dk-da"),
    ("el_centenarian",           "εκατοντάρης μακροζωία μυστικό",             "gr-el"),
    ("ar_centenarian",           "معمر سر طول العمر",                         "xa-ar"),
    ("zh_centenarian",           "百岁老人 长寿 秘诀",                          "cn-zh"),
    ("ru_centenarian",           "долгожитель секрет долголетия",              "ru-ru"),
    ("hi_centenarian",           "शतायु दीर्घायु रहस्य",                      "in-hi"),
    ("tr_centenarian",           "asırlık uzun yaşam sırrı",                 "tr-tr"),

    # ── Specific high-value site searches ────────────────────────────────
    # Target the richest centenarian archives directly

    ("site_today",        "centenarian OR 100-year-old site:today.com",        "wt-wt"),
    ("site_bluezones",    "centenarian OR longevity OR blue zone site:bluezones.com", "wt-wt"),
    ("site_bbc",          "centenarian OR 100-year-old site:bbc.com",          "wt-wt"),
    ("site_guardian",     "centenarian OR longevity site:theguardian.com",     "wt-wt"),
    ("site_cnn",          "centenarian OR 100-year-old site:cnn.com",          "wt-wt"),
    ("site_aarp",         "centenarian OR 100-year-old site:aarp.org",         "wt-wt"),
    ("site_dailymail",    "centenarian OR 100-year-old site:dailymail.co.uk",  "wt-wt"),
    ("site_people",       "centenarian OR 100-year-old site:people.com",       "wt-wt"),
    ("site_rd",           "centenarian OR 100-year-old site:rd.com",           "wt-wt"),
    ("site_prevention",   "centenarian OR longevity site:prevention.com",      "wt-wt"),
    ("site_nyt",          "centenarian OR 100-year-old site:nytimes.com",      "wt-wt"),
    ("site_wapo",         "centenarian OR longevity site:washingtonpost.com",  "wt-wt"),
    ("site_time",         "centenarian OR 100-year-old site:time.com",         "wt-wt"),
    ("site_fox",          "centenarian OR 100-year-old site:foxnews.com",      "wt-wt"),
    ("site_abc_au",       "centenarian OR 100-year-old site:abc.net.au",       "wt-wt"),
    ("site_smh",          "centenarian OR 100-year-old site:smh.com.au",       "wt-wt"),
    ("site_cbc",          "centenarian OR 100-year-old site:cbc.ca",           "wt-wt"),
    ("site_scmp",         "centenarian OR 100-year-old site:scmp.com",         "wt-wt"),
    ("site_japantimes",   "centenarian OR 100-year-old site:japantimes.co.jp", "wt-wt"),
    ("site_toi",          "centenarian OR 100-year-old site:timesofindia.indiatimes.com", "wt-wt"),
    ("site_independent",  "centenarian OR 100-year-old site:independent.co.uk","wt-wt"),
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
    "centenaire", "centenario", "centenária", "hundertjährig",
    "百寿", "百岁", "백세", "долгожитель",
]

def content_ok(text):
    tl = text.lower()
    return any(kw in tl for kw in CONTENT_KEYWORDS)

# ================================================================================
# ARTICLE FETCHER
# ================================================================================

def fetch_article(url):
    """Fetch and extract article text from a URL."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=12, allow_redirects=True)
        if r.status_code != 200:
            return "", ""

        soup = BeautifulSoup(r.text, "html.parser")

        # Remove non-content elements
        for tag in soup(["script", "style", "nav", "header", "footer",
                         "aside", "form", "iframe"]):
            tag.decompose()

        # Title
        title = ""
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)

        # Body — all substantial paragraphs
        paragraphs = soup.find_all("p")
        body = " ".join(
            p.get_text(strip=True) for p in paragraphs
            if len(p.get_text(strip=True)) > 20
        )

        return title, body

    except Exception:
        return "", ""

# ================================================================================
# SEARCH ENGINE
# ================================================================================

def search_ddg(query, region="wt-wt", max_results=MAX_RESULTS_PER_QUERY):
    """
    Search DuckDuckGo and return list of result dicts.
    Each dict has: title, url, body (snippet)
    """
    try:
        with DDGS() as ddgs:
            # ddgs (new package) doesn't accept backend="lite"; let it use defaults.
            results = list(ddgs.text(
                query,
                region=region,
                max_results=max_results,
            ))
        return results
    except Exception as e:
        print(f"    ✗ Search error: {e}")
        return []

# ================================================================================
# COUNTRY DETECTION
# ================================================================================

DOMAIN_COUNTRY = {
    ".com.au": "Australia", ".co.nz": "New Zealand", ".ca": "Canada",
    ".co.uk": "UK", ".co.za": "South Africa", ".co.ke": "Kenya",
    ".com.ng": "Nigeria", ".co.in": "India", ".com.sg": "Singapore",
    ".co.jp": "Japan", ".co.kr": "South Korea", ".com.hk": "Hong Kong",
    ".com.ph": "Philippines", ".co.th": "Thailand", ".com.my": "Malaysia",
    ".fr": "France", ".de": "Germany", ".es": "Spain", ".it": "Italy",
    ".pt": "Portugal", ".nl": "Netherlands", ".se": "Sweden",
    ".dk": "Denmark", ".no": "Norway", ".fi": "Finland", ".gr": "Greece",
    ".ie": "Ireland", ".be": "Belgium", ".ch": "Switzerland",
    ".pl": "Poland", ".cz": "Czech Republic", ".hu": "Hungary",
    ".ro": "Romania", ".tr": "Turkey", ".ru": "Russia",
    ".br": "Brazil", ".ar": "Argentina", ".mx": "Mexico",
    ".cl": "Chile", ".co": "Colombia", ".pe": "Peru",
    ".il": "Israel", ".ae": "UAE", ".sa": "Saudi Arabia",
    ".qa": "Qatar", ".cu": "Cuba", ".cr": "Costa Rica",
    "bbc.com": "UK", "theguardian.com": "UK", "dailymail.co.uk": "UK",
    "cnn.com": "USA", "nytimes.com": "USA", "washingtonpost.com": "USA",
    "today.com": "USA", "foxnews.com": "USA", "nbcnews.com": "USA",
    "aarp.org": "USA", "people.com": "USA", "time.com": "USA",
    "bluezones.com": "USA",
    "reuters.com": "International", "apnews.com": "International",
    "aljazeera.com": "Qatar", "scmp.com": "Hong Kong",
}

def detect_country(url):
    """Detect source country from article URL domain."""
    url_lower = url.lower()
    # Check specific domains first
    for domain, country in DOMAIN_COUNTRY.items():
        if domain in url_lower:
            return country
    # Default for .com
    if ".com" in url_lower:
        return "USA"  # most .com news sites are US-based
    return "Unknown"

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
    full_text_ok = 0
    full_text_fail = 0

    print("="*70)
    print("  REJUVE LONGEVITY — DuckDuckGo Search Scraper v1.0")
    print(f"  Queries:   {len(QUERIES)}")
    print(f"  Output:    {out}")
    print(f"  Resuming:  {len(done)} URLs already collected")
    print("="*70)

    try:
        for qi, (label, query, region) in enumerate(QUERIES):
            print(f"\n{'─'*70}")
            print(f"[{qi+1}/{len(QUERIES)}] {label} ({region})")
            print(f"  Query: {query}")
            print(f"{'─'*70}")

            # Search DuckDuckGo
            results = search_ddg(query, region)
            print(f"  → {len(results)} search results")

            if not results:
                time.sleep(DELAY_BETWEEN_SEARCHES)
                continue

            batch_saved = 0
            for i, result in enumerate(results):
                url = result.get("href", "") or result.get("url", "")
                search_title = result.get("title", "")
                search_snippet = result.get("body", "")

                if not url or url in done:
                    continue

                # Skip non-article URLs
                skip_domains = [
                    "youtube.com", "facebook.com", "twitter.com", "instagram.com",
                    "linkedin.com", "pinterest.com", "reddit.com", "tiktok.com",
                    "amazon.com", "ebay.com", "wikipedia.org",
                ]
                if any(d in url.lower() for d in skip_domains):
                    continue

                print(f"  [{i+1}/{len(results)}] ", end="", flush=True)

                # Fetch full article
                title, body = fetch_article(url)

                # Use search title/snippet as fallback
                if not title:
                    title = search_title
                if len(body.split()) < MIN_WORD_COUNT:
                    # Try using search snippet combined with whatever we got
                    if search_snippet:
                        body = body + " " + search_snippet if body else search_snippet

                # Quality gates
                if len(body.split()) < 50:
                    full_text_fail += 1
                    print("✗ no text")
                    continue

                if not content_ok(title + " " + body):
                    print("✗ not relevant")
                    continue

                full_text_ok += 1

                # Extract everything
                full = title + " " + body
                ages = extract_ages(full)
                stats = extract_stats(body)
                cols = extract_columns(body)
                subj = extract_subject(title, body)
                max_age = str(max(int(a) for a in ages.split(","))) if ages else ""

                source_country = detect_country(url)

                # Extract domain name as source
                from urllib.parse import urlparse
                domain = urlparse(url).netloc.replace("www.", "")

                rec = {
                    "source_name":    domain,
                    "source_country": source_country,
                    "source_class":   "search_ddg",
                    "url":            url,
                    "scraped_date":   datetime.now().strftime("%Y-%m-%d"),
                    "publish_date":   "",  # DuckDuckGo doesn't provide dates
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

                # Output
                age_s = f"age={rec['subject_age']}" if rec['subject_age'] else (
                        f"max={rec['max_age']}" if rec['max_age'] else "no age")
                nm = rec['subject_name'] or ""
                st = " 📊" if rec['has_stats'] else ""
                ct = " 👤" if rec['is_centenarian_profile'] else ""
                print(f"✓ [{domain[:20]}] {title[:30]}... [{nm} {age_s}{st}{ct}]")

                time.sleep(DELAY_BETWEEN_ARTICLES)

            print(f"\n  ✓ {batch_saved} saved from this query")
            time.sleep(DELAY_BETWEEN_SEARCHES)

    except KeyboardInterrupt:
        print("\n\n⚠ Interrupted — progress saved")

    # Summary
    hit_rate = f"{full_text_ok/(full_text_ok+full_text_fail)*100:.0f}%" if (full_text_ok+full_text_fail) > 0 else "N/A"
    print(f"\n{'='*70}")
    print(f"  DONE | Session: {session_saved} new articles")
    print(f"  Full text success: {full_text_ok} | Failed: {full_text_fail} | Hit rate: {hit_rate}")
    print(f"{'='*70}")

    if os.path.exists(out):
        df = pd.read_csv(out)
        ddg = df[df["source_class"] == "search_ddg"]

        print(f"\n  TOTAL IN CSV: {len(df)} articles")
        print(f"  From DuckDuckGo: {len(ddg)}")

        if len(ddg) > 0:
            print(f"  Centenarian profiles: {ddg['is_centenarian_profile'].sum()}")
            print(f"  With age mentions:    {ddg['has_age'].sum()}")

            print(f"\n  TOP SOURCES:")
            for s, c in ddg["source_name"].value_counts().head(20).items():
                print(f"    {s:<40} {c}")

            print(f"\n  BY COUNTRY:")
            for co, c in ddg["source_country"].value_counts().head(15).items():
                print(f"    {co:<25} {c}")

        print(f"\n  FILE: {out}")


if __name__ == "__main__":
    run()
