"""
================================================================================
REJUVE LONGEVITY APP — Centenarian Data Pipeline
FILE: scraper_google_news.py
VERSION: 1.0
PURPOSE: Uses Google News RSS feeds to find centenarian/longevity articles
         from hundreds of global news sources simultaneously.

WHY THIS EXISTS:
  The Selenium-based news scraper (scraper_news.py) gets blocked by many
  sites' bot detection. Google News RSS bypasses this entirely because
  Google has already aggregated the articles. One RSS query pulls results
  from Le Monde, CBC, Sydney Morning Herald, Der Spiegel, and hundreds
  more outlets simultaneously.

WRITES TO THE SAME CSV as scraper_news.py (data/raw/news_articles.csv).
  Uses the same column schema and same URL deduplication, so articles
  already collected by the Selenium scraper are automatically skipped.

NO Selenium, NO Chrome needed. Uses requests + BeautifulSoup only.

DEPENDENCIES: pip install requests beautifulsoup4 pandas
AUTHOR: Rejuve Longevity (open-source)
LICENSE: MIT
================================================================================
"""

import time, re, os, csv
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime

# ================================================================================
# CONFIGURATION
# ================================================================================

OUTPUT_DIR  = "data/raw"
OUTPUT_FILE = "news_articles.csv"  # SAME file as scraper_news.py

DELAY_BETWEEN_ARTICLES = 2.0
DELAY_BETWEEN_QUERIES  = 3.0

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}
MIN_WORD_COUNT = 50

# ================================================================================
# GOOGLE NEWS RSS QUERIES
# ================================================================================
# Each query searches Google News across ALL indexed sources globally.
# Region codes ensure we get results from different parts of the world.
#
# Format: (label, search_term, language, country_code)
# Google News RSS URL pattern:
#   https://news.google.com/rss/search?q={term}&hl={lang}&gl={country}&ceid={country}:{lang}

QUERIES = [
    # ── English language, multiple regions ────────────────────────────────
    # Core centenarian terms
    ("en_us_centenarian",       "centenarian",                  "en", "US"),
    ("en_us_supercentenarian",  "supercentenarian",             "en", "US"),
    ("en_us_100_year_old",      '"100 year old" longevity',     "en", "US"),
    ("en_us_oldest_person",     "oldest person alive",          "en", "US"),
    ("en_us_longevity_secrets", "longevity secrets centenarian", "en", "US"),
    ("en_us_blue_zones",        "blue zones longevity",         "en", "US"),
    ("en_us_live_to_100",       '"live to 100" tips',           "en", "US"),

    ("en_uk_centenarian",       "centenarian",                  "en", "GB"),
    ("en_uk_100_year_old",      '"100 year old"',               "en", "GB"),
    ("en_uk_longevity",         "longevity secrets",            "en", "GB"),

    ("en_au_centenarian",       "centenarian",                  "en", "AU"),
    ("en_au_100_year_old",      '"100 year old"',               "en", "AU"),
    ("en_au_longevity",         "longevity healthy aging",      "en", "AU"),

    ("en_ca_centenarian",       "centenarian",                  "en", "CA"),
    ("en_ca_100_year_old",      '"100 year old"',               "en", "CA"),

    ("en_in_centenarian",       "centenarian India",            "en", "IN"),
    ("en_in_100_year_old",      '"100 year old" India',         "en", "IN"),

    ("en_sg_centenarian",       "centenarian Singapore",        "en", "SG"),
    ("en_sg_longevity",         "longevity Singapore",          "en", "SG"),

    ("en_nz_centenarian",       "centenarian",                  "en", "NZ"),

    ("en_ie_centenarian",       "centenarian Ireland",          "en", "IE"),

    ("en_za_centenarian",       "centenarian South Africa",     "en", "ZA"),

    ("en_ng_centenarian",       "centenarian Nigeria",          "en", "NG"),

    ("en_ke_centenarian",       "centenarian Kenya",            "en", "KE"),

    # ── Non-English regions (articles may be in local language) ───────────
    # Trait keywords won't tag non-English text but we still capture
    # the source, country, title, and URL for Phase 2 processing.

    ("fr_centenaire",       "centenaire longévité",         "fr", "FR"),
    ("de_hundertjaehrige",  "Hundertjährige Langlebigkeit",  "de", "DE"),
    ("es_centenario",       "centenario longevidad",        "es", "ES"),
    ("it_centenario",       "centenario longevità",         "it", "IT"),
    ("pt_centenario",       "centenário longevidade",       "pt", "BR"),
    ("ja_centenarian",      "百寿者 長寿",                    "ja", "JP"),
    ("ko_centenarian",      "백세인 장수",                    "ko", "KR"),
    ("nl_honderdjarige",    "honderdjarige levensduur",     "nl", "NL"),
    ("sv_hundraaring",      "hundraåring långlivad",        "sv", "SE"),
    ("da_hundredaarig",     "hundredårig levetid",          "da", "DK"),
    ("el_centenarian",      "εκατοντάρης μακροζωία",        "el", "GR"),
]

# ================================================================================
# KEYWORD MAPS — identical to scraper_news.py for consistent tagging
# ================================================================================

KW_PHYSICAL = [
    "exercise", "swim", "swimming", "walk", "walking", "gym", "workout",
    "yoga", "dance", "dancing", "active", "movement", "zumba", "cardio",
    "strength training", "weightlifting", "cycling", "gardening", "hiking",
    "tai chi", "sedentary", "run", "running", "physical activity",
]
KW_DIET = [
    "vegetable", "vegetables", "plant-based", "plant based", "mediterranean",
    "olive oil", "legume", "legumes", "fruit", "fruits", "diet", "nutrition",
    "calorie", "caloric", "alcohol", "smoking", "whole food", "processed food",
    "sugar", "red wine", "fasting", "protein", "fiber", "fibre", "antioxidant",
    "pescatarian", "vegetarian", "vegan", "fermented", "probiotic", "omega-3",
]
KW_SOCIAL = [
    "social", "community", "family", "friend", "friends", "church", "faith",
    "religion", "religious", "volunteer", "moai", "belonging", "connection",
    "loneliness", "isolated", "isolation", "marriage", "married",
]
KW_PURPOSE = [
    "purpose", "ikigai", "positive", "optimis", "grateful", "gratitude",
    "stress", "meaning", "passion", "attitude", "mindset", "resilience",
    "conscientiou", "neuroticism", "extraversion", "happiness", "humor",
    "laughter", "anxiety", "depression", "mental health", "cognitive",
]
KW_SLEEP = [
    "sleep", "rest", "nap", "siesta", "insomnia", "circadian",
    "melatonin", "sleep quality", "sleep duration",
]
KW_BIO_INFLAMMATION = [
    "inflammation", "inflammatory", "crp", "c-reactive", "il-6",
    "interleukin", "tnf", "cytokine", "inflammaging", "fibrinogen",
]
KW_BIO_GLUCOSE = [
    "glucose", "insulin", "hba1c", "a1c", "blood sugar", "diabetes",
    "metabolic syndrome", "insulin resistance", "glycemic",
]
KW_BIO_LIPIDS = [
    "cholesterol", "triglyceride", "hdl", "ldl", "lipid", "lipids",
    "apolipoprotein",
]
KW_BIO_IGF1 = [
    "igf-1", "igf1", "insulin-like growth factor", "growth hormone", "mtor",
]
KW_BIO_TELOMERES = ["telomere", "telomeres", "telomerase", "telomere length"]
KW_BIO_EPIGENETIC = [
    "epigenetic", "methylation", "dna methylation", "biological age",
    "epigenetic clock", "horvath", "grimage", "phenoage",
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
    "metabolomics", "metabolomic", "bile acid", "bile acids", "metabolite",
]
KW_GENE_APOE = ["apoe", "apolipoprotein e", "apoe4", "apoe2"]
KW_GENE_FOXO3 = ["foxo3", "foxo3a", "forkhead box"]
KW_GENE_CETP = ["cetp", "cholesteryl ester transfer"]
KW_GENE_KLOTHO = ["klotho", "kl-vs"]
KW_GENE_OTHER = [
    "sirt1", "sirtuin", "ace gene", "mtor pathway", "ampk",
    "brca", "gwas", "genome-wide", "polymorphism", "snp",
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
    "longevity", "live to 100", "lifespan", "healthspan",
    "blue zone", "oldest living", "aging well", "ageing well",
    "long life", "live longer", "exceptional longevity",
]

def content_ok(text):
    tl = text.lower()
    return any(kw in tl for kw in CONTENT_KEYWORDS)

# ================================================================================
# GOOGLE NEWS RSS FETCHER
# ================================================================================

def fetch_rss_articles(search_term, lang, country):
    """
    Fetches Google News RSS feed for a search term.
    Returns list of dicts: {title, url, pub_date, source_name}
    """
    rss_url = (
        f"https://news.google.com/rss/search?"
        f"q={requests.utils.quote(search_term)}"
        f"&hl={lang}&gl={country}&ceid={country}:{lang}"
    )

    try:
        r = requests.get(rss_url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        root = ET.fromstring(r.content)

        articles = []
        for item in root.findall(".//item"):
            title = item.findtext("title", "")
            link  = item.findtext("link", "")
            date  = item.findtext("pubDate", "")
            source_el = item.find("source")
            source_name = source_el.text if source_el is not None else ""

            if title and link:
                articles.append({
                    "rss_title": title,
                    "rss_url": link,
                    "rss_date": date,
                    "rss_source": source_name,
                })
        return articles
    except Exception as e:
        print(f"    ✗ RSS error: {e}")
        return []


def resolve_google_url(google_url):
    """
    Extracts the real article URL from a Google News redirect URL.
    Google encodes the real URL in the redirect — we decode it directly
    rather than following the redirect chain.
    """
    try:
        # Method 1: extract from the URL parameter directly
        if "articles/" in google_url:
            # Try following redirect with a longer timeout and browser headers
            r = requests.get(
                google_url,
                headers=HEADERS,
                timeout=20,
                allow_redirects=True
            )
            # The final URL after redirects is the real article URL
            if "google.com" not in r.url:
                return r.url

        # Method 2: check if URL is already a direct article link
        if "google.com" not in google_url:
            return google_url

        return google_url

    except Exception:
        return google_url


def scrape_article_text(url):
    """
    Fetches an article page and extracts paragraph text.
    Uses requests + BeautifulSoup, no Selenium needed.
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return "", ""
        soup = BeautifulSoup(r.text, "html.parser")

        # Title
        title = ""
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)

        # Body text
        paragraphs = soup.find_all("p")
        body = " ".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

        return title, body
    except Exception:
        return "", ""


# ================================================================================
# COUNTRY DETECTION FROM SOURCE NAME
# ================================================================================

# Maps common source names to countries for the source_country field
SOURCE_COUNTRY_MAP = {
    "bbc": "UK", "guardian": "UK", "telegraph": "UK", "daily mail": "UK",
    "independent": "UK", "mirror": "UK", "sun": "UK", "sky news": "UK",
    "times": "UK", "scotsman": "UK",
    "cnn": "USA", "nbc": "USA", "cbs": "USA", "abc news": "USA",
    "fox": "USA", "nyt": "USA", "new york times": "USA",
    "washington post": "USA", "today": "USA", "time": "USA",
    "people": "USA", "aarp": "USA", "npr": "USA", "usa today": "USA",
    "newsweek": "USA", "reuters": "International", "ap news": "International",
    "cbc": "Canada", "globe and mail": "Canada", "toronto star": "Canada",
    "national post": "Canada",
    "abc australia": "Australia", "sydney morning": "Australia",
    "the age": "Australia", "sbs": "Australia", "nine news": "Australia",
    "herald sun": "Australia", "news.com.au": "Australia",
    "le monde": "France", "le figaro": "France", "liberation": "France",
    "spiegel": "Germany", "welt": "Germany", "zeit": "Germany",
    "el pais": "Spain", "el mundo": "Spain",
    "repubblica": "Italy", "corriere": "Italy", "stampa": "Italy",
    "times of india": "India", "hindu": "India", "ndtv": "India",
    "hindustan times": "India",
    "japan times": "Japan", "nikkei": "Japan", "mainichi": "Japan",
    "yomiuri": "Japan", "asahi": "Japan",
    "scmp": "Hong Kong", "south china": "Hong Kong",
    "straits times": "Singapore", "channel news": "Singapore",
    "korea herald": "South Korea", "joong": "South Korea",
    "nz herald": "New Zealand", "stuff": "New Zealand",
    "irish times": "Ireland", "rte": "Ireland",
    "haaretz": "Israel", "jerusalem post": "Israel",
    "al jazeera": "Qatar",
    "news24": "South Africa", "iol": "South Africa",
    "daily nation": "Kenya", "premium times": "Nigeria",
    "globo": "Brazil", "folha": "Brazil",
    "infobae": "Argentina", "nacion": "Argentina",
}

def detect_country(source_name):
    """Detect country from Google News source name."""
    sl = source_name.lower()
    for pattern, country in SOURCE_COUNTRY_MAP.items():
        if pattern in sl:
            return country
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

    print("="*70)
    print("  REJUVE LONGEVITY — Google News RSS Scraper v1.0")
    print(f"  Queries:   {len(QUERIES)}")
    print(f"  Output:    {out}")
    print(f"  Resuming:  {len(done)} URLs already collected")
    print("="*70)

    try:
        for qi, (label, term, lang, country) in enumerate(QUERIES):
            print(f"\n{'─'*70}")
            print(f"[{qi+1}/{len(QUERIES)}] {label} ({lang}-{country})")
            print(f"{'─'*70}")

            # Fetch RSS feed
            articles = fetch_rss_articles(term, lang, country)
            print(f"  → {len(articles)} RSS results")

            if not articles:
                continue

            for i, art in enumerate(articles):
                # Resolve Google redirect URL to real article URL
                real_url = resolve_google_url(art["rss_url"])

                # Skip already collected
                if real_url in done:
                    continue

                print(f"  [{i+1}/{len(articles)}] ", end="", flush=True)

                # Scrape article text
                title, body = scrape_article_text(real_url)

                # Use RSS title if scrape didn't get one
                if not title:
                    title = art["rss_title"]

                # Quality gates
                if len(body.split()) < MIN_WORD_COUNT:
                    print("✗ too short")
                    continue
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

                source_country = detect_country(art["rss_source"])

                rec = {
                    "source_name":    art["rss_source"] or "Unknown",
                    "source_country": source_country,
                    "source_class":   "google_news_rss",
                    "url":            real_url,
                    "scraped_date":   datetime.now().strftime("%Y-%m-%d"),
                    "publish_date":   art["rss_date"],
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
                         "supercentenarian","lives to 100"]),
                }
                rec.update(cols)

                save_rec(rec, out, hdr)
                hdr = False
                done.add(real_url)
                session_saved += 1

                age_s = f"age={rec['subject_age']}" if rec['subject_age'] else (
                        f"max={rec['max_age']}" if rec['max_age'] else "no age")
                nm = rec['subject_name'] or ""
                st = " 📊" if rec['has_stats'] else ""
                ct = " 👤" if rec['is_centenarian_profile'] else ""
                src = art['rss_source'][:20]
                print(f"✓ [{src}] {title[:35]}... [{nm} {age_s}{st}{ct}]")

                time.sleep(DELAY_BETWEEN_ARTICLES)

            time.sleep(DELAY_BETWEEN_QUERIES)

    except KeyboardInterrupt:
        print("\n\n⚠ Interrupted — progress saved")

    # Summary
    print(f"\n{'='*70}")
    print(f"  DONE | Session: {session_saved} new articles")
    print(f"{'='*70}")

    if os.path.exists(out):
        df = pd.read_csv(out)
        print(f"\n  TOTAL IN COMBINED CSV: {len(df)} articles")

        # Show just Google News RSS articles
        gn = df[df["source_class"] == "google_news_rss"]
        if len(gn) > 0:
            print(f"  From Google News RSS: {len(gn)}")
            print(f"\n  GOOGLE NEWS SOURCES (top 20):")
            for s, c in gn["source_name"].value_counts().head(20).items():
                print(f"    {s:<40} {c}")
            print(f"\n  GOOGLE NEWS COUNTRIES (top 15):")
            for co, c in gn["source_country"].value_counts().head(15).items():
                print(f"    {co:<25} {c}")

        print(f"\n  FILE: {out}")


if __name__ == "__main__":
    run()
