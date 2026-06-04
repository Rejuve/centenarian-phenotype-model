"""
================================================================================
REJUVE LONGEVITY APP — Centenarian Data Pipeline
FILE: scraper_academic.py
VERSION: 2.0
PURPOSE: Collects centenarian/longevity research papers from major academic
         databases via their free public APIs. No Selenium needed — pure HTTP.

DATABASES:
  1. PubMed / MEDLINE  — 35M+ biomedical records, free E-utilities API
  2. Europe PMC        — European mirror + additional EU content
  3. Semantic Scholar   — 200M+ papers, citation graph, broader coverage

SAVES INCREMENTALLY — every query batch writes to CSV immediately.
If it crashes at query 40 of 62, re-running skips the first 39 queries
worth of data and continues from where it stopped.

OUTPUT (in data/raw/):
  academic_papers.csv         — full dataset with abstracts
  academic_papers_preview.csv — same without abstract text

DEPENDENCIES: pip install requests pandas
AUTHOR: Rejuve Longevity (open-source)
LICENSE: MIT
================================================================================
"""

import time, re, os, csv, json
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from datetime import datetime

# ================================================================================
# CONFIGURATION
# ================================================================================

OUTPUT_DIR  = "data/raw"
OUTPUT_FILE = "academic_papers.csv"

NCBI_API_KEY = os.getenv("NCBI_API_KEY", "")  # set in env; do not hardcode (kept out of VCS)
SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")  # set in env; do not hardcode

DELAY_PUBMED    = 0.4 if NCBI_API_KEY else 0.5
DELAY_EUROPEPMC = 0.3
DELAY_SEMANTIC  = 1.1

MAX_PUBMED_PER_QUERY    = 500
MAX_EUROPEPMC_PER_QUERY = 200
MAX_SEMANTIC_PER_QUERY  = 100

# ================================================================================
# SEARCH QUERIES
# ================================================================================

QUERIES = [
    ("core_centenarian",             "centenarian"),
    ("core_supercentenarian",        "supercentenarian"),
    ("core_exceptional_longevity",   "exceptional longevity"),
    ("core_extreme_longevity",       "extreme longevity human"),
    ("core_healthy_aging",           "healthy aging longevity"),
    ("core_healthy_ageing",          "healthy ageing longevity"),
    ("core_longevity_determinants",  "longevity determinants human"),
    ("core_blue_zones",              "blue zones longevity"),

    ("study_necs",          "New England Centenarian Study"),
    ("study_okinawa",       "Okinawa Centenarian Study"),
    ("study_georgia",       "Georgia Centenarian Study"),
    ("study_llfs",          "Long Life Family Study"),
    ("study_leiden",        "Leiden Longevity Study"),
    ("study_danish_twin",   "Danish Twin Study longevity"),
    ("study_swedish",       "Swedish Centenarian Study"),
    ("study_australian",    "Australian Centenarian Study"),
    ("study_tokyo",         "Tokyo Centenarian Study"),
    ("study_korean",        "Korean Centenarian Study"),
    ("study_clhls",         "Chinese Longitudinal Healthy Longevity Survey"),
    ("study_akea",          "AKEA Sardinia longevity"),
    ("study_ashkenazi",     "Ashkenazi centenarian longevity"),
    ("study_nicoya",        "Nicoya Peninsula longevity"),
    ("study_ikaria",        "Ikaria longevity population"),
    ("study_loma_linda",    "Loma Linda Adventist health longevity"),
    ("study_105plus",       "semi-supercentenarian 105"),
    ("study_uk_biobank",    "UK Biobank longevity"),
    ("study_framingham",    "Framingham Heart Study longevity"),
    ("study_hrs",           "Health Retirement Study aging longevity"),
    ("study_longevity_consortium", "Longevity Consortium centenarian"),
    ("study_integrative_omics",    "Integrative Longevity Omics"),

    ("region_china",         "centenarian China"),
    ("region_india",         "centenarian India"),
    ("region_brazil",        "centenarian Brazil"),
    ("region_korea",         "centenarian Korea"),
    ("region_iran",          "centenarian Iran"),
    ("region_africa",        "centenarian Africa"),
    ("region_caribbean",     "centenarian Caribbean Cuba"),
    ("region_latin_america", "centenarian Latin America"),
    ("region_southeast_asia","centenarian Southeast Asia"),
    ("region_caucasus",      "centenarian Caucasus Georgia Abkhazia"),
    ("region_ecuador",       "centenarian Ecuador Vilcabamba"),
    ("region_pakistan",       "centenarian Pakistan Hunza"),
    ("region_france",        "centenarian France"),
    ("region_germany",       "centenarian Germany"),
    ("region_scandinavia",   "centenarian Scandinavia Nordic"),
    ("region_mediterranean", "centenarian Mediterranean"),
    ("region_middle_east",   "centenarian Middle East Israel"),
    ("region_singapore",     "centenarian Singapore aging"),
    ("region_russia",        "centenarian Russia"),
    ("region_subsaharan",    "centenarian sub-Saharan Africa"),
    ("region_japan",         "centenarian Japan Okinawa"),
    ("region_italy",         "centenarian Italy Sardinia"),
    ("region_greece",        "centenarian Greece Ikaria"),
    ("region_costa_rica",    "centenarian Costa Rica Nicoya"),

    # ── Targeted biomarker queries (Phase 3 expansion) ────────────────────
    # Epigenetic clocks
    ("bio_horvath_clock",        "Horvath clock centenarian"),
    ("bio_phenoage",             "PhenoAge centenarian"),
    ("bio_grimage",              "GrimAge longevity"),
    ("bio_epigenetic_accel",     "epigenetic age acceleration centenarian"),
    ("bio_dna_methylation_age",  "DNA methylation age centenarian"),
    # Telomeres
    ("bio_telomere_centenarian", "telomere length centenarian"),
    ("bio_telomere_longevity",   "telomere length longevity"),
    ("bio_telomerase_centenarian","telomerase centenarian"),
    # IGF-1 axis / mTOR
    ("bio_igf1_centenarian",     "IGF-1 centenarian longevity"),
    ("bio_igf1_insulin_like",    "insulin-like growth factor centenarian"),
    ("bio_mtor_longevity",       "mTOR longevity centenarian"),
    # Inflammatory cytokines
    ("bio_il6_centenarian",      "IL-6 centenarian"),
    ("bio_il6_longevity",        "interleukin-6 longevity"),
    ("bio_tnf_alpha_centenarian","TNF-alpha centenarian"),
    ("bio_inflammaging",         "inflammaging centenarian"),
    # Kidney function
    ("bio_creatinine_centenarian","creatinine centenarian"),
    ("bio_egfr_centenarian",     "eGFR centenarian longevity"),
    ("bio_cystatinC_centenarian","cystatin C centenarian"),
    # Microbiome
    ("bio_gut_microbiome",       "gut microbiome centenarian"),
    ("bio_microbiota_diversity", "microbiota diversity centenarian longevity"),
    # Nutrition markers
    ("bio_albumin_centenarian",  "albumin centenarian"),
    ("bio_vitamind_centenarian", "vitamin D centenarian longevity"),
    ("bio_25oh_vitd",            "25-hydroxyvitamin D centenarian"),
    # Functional markers
    ("bio_grip_strength",        "grip strength centenarian"),
    ("bio_gait_speed",           "gait speed centenarian"),
    ("bio_vo2max",               "VO2 max longevity"),
    # Hormones
    ("bio_dhea",                 "DHEA centenarian"),
    ("bio_dheas",                "DHEAS longevity"),
    ("bio_testosterone",         "testosterone longevity centenarian"),

    # ── Foundational aging-biology backbone ───────────────────────────────
    # Not centenarian-specific: the core geroscience literature that grounds
    # the model's biology (hallmarks of aging series, geroscience/geromedicine
    # framing, and each hallmark). Good-practice corpus completeness; expected
    # to inform provenance/grading more than to add new quiz features.
    ("found_hallmarks_aging",      "hallmarks of aging"),
    ("found_hallmarks_ageing",     "hallmarks of ageing"),
    ("found_geroscience",          "geroscience hypothesis aging"),
    ("found_geromedicine",         "geromedicine"),
    ("found_biology_of_aging",     "biology of aging review"),
    ("found_compression_morbidity","compression of morbidity longevity"),
    ("found_rate_of_aging",        "rate of aging biomarkers humans"),
    ("found_geroprotectors",       "geroprotectors aging intervention"),
    ("found_cellular_senescence",  "cellular senescence aging"),
    ("found_senolytics",           "senescent cells senolytics aging"),
    ("found_nutrient_sensing",     "nutrient sensing longevity mTOR IGF-1"),
    ("found_autophagy",            "autophagy longevity aging"),
    ("found_mito_dysfunction",     "mitochondrial dysfunction aging"),
    ("found_proteostasis",         "proteostasis loss aging"),
    ("found_epigenetic_alt",       "epigenetic alterations aging"),
    ("found_genomic_instability",  "genomic instability aging"),
    ("found_telomere_attrition",   "telomere attrition aging"),
    ("found_stem_cell_exhaustion", "stem cell exhaustion aging"),
    ("found_inflammaging_comm",    "inflammaging intercellular communication aging"),
    ("found_dysbiosis_aging",      "gut dysbiosis aging hallmark"),
]

# ================================================================================
# KEYWORD MAPS
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
    "interleukin", "tnf", "cytokine", "anti-inflammatory", "nf-kb",
    "inflammaging", "fibrinogen", "esr",
]
KW_BIO_GLUCOSE = [
    "glucose", "insulin", "hba1c", "a1c", "blood sugar", "diabetes",
    "metabolic syndrome", "insulin resistance", "homa-ir", "glycemic",
]
KW_BIO_LIPIDS = [
    "cholesterol", "triglyceride", "hdl", "ldl", "lipid", "lipids",
    "apolipoprotein", "apob", "apoa1",
]
KW_BIO_IGF1 = [
    "igf-1", "igf1", "igf 1", "insulin-like growth factor",
    "growth hormone", "mtor",
]
KW_BIO_TELOMERES = [
    "telomere", "telomeres", "telomerase", "telomere length",
]
KW_BIO_EPIGENETIC = [
    "epigenetic", "methylation", "dna methylation", "biological age",
    "epigenetic clock", "horvath", "grimage", "phenoage",
]
KW_BIO_MICROBIOME = [
    "microbiome", "gut bacteria", "gut microbiota", "microbiota diversity",
]
KW_BIO_HORMONES = [
    "cortisol", "testosterone", "estrogen", "dhea", "thyroid",
    "hormone", "hormonal",
]
KW_BIO_FUNCTIONAL = [
    "grip strength", "gait speed", "vo2 max", "vo2max", "fev1",
    "lung function", "frailty", "sarcopenia", "muscle mass",
]
KW_BIO_METABOLOMIC = [
    "metabolomics", "metabolomic", "bile acid", "bile acids",
    "chenodeoxycholic", "lithocholic", "metabolite",
]
KW_GENE_APOE = ["apoe", "apolipoprotein e", "apoe4", "apoe2"]
KW_GENE_FOXO3 = ["foxo3", "foxo3a", "forkhead box"]
KW_GENE_CETP = ["cetp", "cholesteryl ester transfer"]
KW_GENE_KLOTHO = ["klotho", "kl-vs"]
KW_GENE_OTHER = [
    "sirt1", "sirtuin", "ace gene", "mtor pathway", "ampk",
    "brca", "gwas", "genome-wide", "polymorphism", "snp",
    "genetic variant", "heritability", "hereditary",
]

STAT_PATTERNS = {
    "odds_ratio":          r'(?:OR|odds ratio)[^\d]*(\d+\.?\d*)',
    "hazard_ratio":        r'(?:HR|hazard ratio)[^\d]*(\d+\.?\d*)',
    "relative_risk":       r'(?:RR|relative risk)[^\d]*(\d+\.?\d*)',
    "sample_size":         r'(?:n\s*=\s*|n=|sample size[^\d]*)(\d[\d,]+)',
    "percentage":          r'(\d+\.?\d*)\s*(?:%|percent)',
    "p_value":             r'p\s*[<=]\s*(\d+\.?\d+)',
    "confidence_interval": r'(?:95%\s*CI|confidence interval)[^\d]*(\d+\.?\d*)[^\d]+(\d+\.?\d*)',
}

STUDY_TYPES = [
    ("meta-analysis",    ["meta-analysis", "meta analysis", "systematic review"]),
    ("randomized_trial", ["randomized", "randomised", "rct", "clinical trial"]),
    ("cohort",           ["cohort study", "longitudinal", "prospective", "retrospective"]),
    ("case_control",     ["case-control", "case control"]),
    ("cross_sectional",  ["cross-sectional", "cross sectional", "survey"]),
    ("genome_wide",      ["gwas", "genome-wide", "genome wide"]),
    ("review",           ["review", "overview"]),
    ("case_report",      ["case report", "case series"]),
]

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

def classify_study_type(text):
    tl = text.lower()
    for stype, kws in STUDY_TYPES:
        if any(kw in tl for kw in kws):
            return stype
    return "other"

def extract_population_country(text):
    patterns = [
        (r'\b(?:Japanese|Japan|Okinawa)\b', "Japan"),
        (r'\b(?:Italian|Italy|Sardinia|Sardinian|Sicily)\b', "Italy"),
        (r'\b(?:Greek|Greece|Ikaria)\b', "Greece"),
        (r'\b(?:Costa Rica|Nicoya)\b', "Costa Rica"),
        (r'\b(?:American|United States|U\.S\.|USA)\b', "USA"),
        (r'\b(?:Chinese|China|Hainan)\b', "China"),
        (r'\b(?:Korean|Korea)\b', "South Korea"),
        (r'\b(?:Danish|Denmark)\b', "Denmark"),
        (r'\b(?:Swedish|Sweden)\b', "Sweden"),
        (r'\b(?:Dutch|Netherlands|Leiden)\b', "Netherlands"),
        (r'\b(?:British|United Kingdom|U\.K\.|UK Biobank)\b', "UK"),
        (r'\b(?:Australian|Australia)\b', "Australia"),
        (r'\b(?:French|France)\b', "France"),
        (r'\b(?:German|Germany)\b', "Germany"),
        (r'\b(?:Brazilian|Brazil)\b', "Brazil"),
        (r'\b(?:Indian|India)\b', "India"),
        (r'\b(?:Israeli|Israel|Ashkenazi)\b', "Israel"),
        (r'\b(?:Iranian|Iran)\b', "Iran"),
        (r'\b(?:Nigerian|Nigeria)\b', "Nigeria"),
        (r'\b(?:Cuban|Cuba)\b', "Cuba"),
        (r'\b(?:Singaporean|Singapore)\b', "Singapore"),
        (r'\b(?:Finnish|Finland)\b', "Finland"),
        (r'\b(?:Norwegian|Norway)\b', "Norway"),
        (r'\b(?:Spanish|Spain)\b', "Spain"),
        (r'\b(?:Portuguese|Portugal)\b', "Portugal"),
        (r'\b(?:Russian|Russia)\b', "Russia"),
        (r'\b(?:Canadian|Canada)\b', "Canada"),
        (r'\b(?:Pakistani|Pakistan|Hunza)\b', "Pakistan"),
        (r'\b(?:Ecuadorian|Ecuador|Vilcabamba)\b', "Ecuador"),
        (r'\b(?:Georgian|Caucasus|Abkhazi)\b', "Georgia/Caucasus"),
        (r'\b(?:Thai|Thailand)\b', "Thailand"),
        (r'\b(?:Mexican|Mexico)\b', "Mexico"),
        (r'\b(?:Polish|Poland)\b', "Poland"),
        (r'\b(?:Turkish|Turkey)\b', "Turkey"),
    ]
    found = []
    for pat, country in patterns:
        if re.search(pat, text):
            found.append(country)
    return ",".join(found) if found else ""

def extract_ages(text):
    raw = re.findall(r'\b(1[0-2][0-9]|[89][0-9])\b', text)
    u = sorted(set(int(a) for a in raw if 85 <= int(a) <= 130))
    return ",".join(str(a) for a in u) if u else ""

# ================================================================================
# PubMed API
# ================================================================================

PUBMED_SEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

def pubmed_search(query, max_results=MAX_PUBMED_PER_QUERY):
    params = {"db":"pubmed", "term":query, "retmax":max_results,
              "retmode":"json", "sort":"relevance"}
    if NCBI_API_KEY: params["api_key"] = NCBI_API_KEY
    try:
        r = requests.get(PUBMED_SEARCH, params=params, timeout=30)
        r.raise_for_status()
        return r.json().get("esearchresult",{}).get("idlist",[])
    except Exception as e:
        print(f"    ✗ PubMed search error: {e}")
        return []

def pubmed_fetch_batch(pmids):
    if not pmids: return []
    params = {"db":"pubmed", "id":",".join(pmids),
              "retmode":"xml", "rettype":"abstract"}
    if NCBI_API_KEY: params["api_key"] = NCBI_API_KEY
    try:
        r = requests.get(PUBMED_FETCH, params=params, timeout=60)
        r.raise_for_status()
        return parse_pubmed_xml(r.text)
    except Exception as e:
        print(f"    ✗ PubMed fetch error: {e}")
        return []

def parse_pubmed_xml(xml_text):
    records = []
    try: root = ET.fromstring(xml_text)
    except ET.ParseError: return []
    for article in root.findall(".//PubmedArticle"):
        try:
            pmid_el = article.find(".//PMID")
            pmid = pmid_el.text if pmid_el is not None else ""
            title_el = article.find(".//ArticleTitle")
            title = (title_el.text or "") if title_el is not None else ""
            abstract_parts = []
            for ab in article.findall(".//AbstractText"):
                label = ab.get("Label","")
                text = ab.text or ""
                abstract_parts.append(f"{label}: {text}" if label else text)
            abstract = " ".join(abstract_parts)
            if not abstract or len(abstract) < 50: continue
            doi = ""
            for eid in article.findall(".//ArticleId"):
                if eid.get("IdType") == "doi":
                    doi = eid.text or ""; break
            journal_el = article.find(".//Journal/Title")
            journal = journal_el.text if journal_el is not None else ""
            authors = []
            for au in article.findall(".//Author")[:5]:
                last = au.findtext("LastName","")
                first = au.findtext("ForeName","")
                if last: authors.append(f"{last}, {first}" if first else last)
            year = article.findtext(".//PubDate/Year","")
            month = article.findtext(".//PubDate/Month","")
            day = article.findtext(".//PubDate/Day","")
            mesh = [m.text for m in article.findall(".//MeshHeading/DescriptorName") if m.text]
            records.append({
                "pmid":pmid, "doi":doi, "title":title, "abstract":abstract,
                "authors":"; ".join(authors), "journal":journal,
                "pub_date":f"{year}-{month}-{day}".strip("-"), "pub_year":year,
                "mesh_terms":"; ".join(mesh), "source_database":"pubmed",
            })
        except: continue
    return records

# ================================================================================
# Europe PMC API
# ================================================================================

EUROPEPMC_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

def europepmc_search(query, max_results=MAX_EUROPEPMC_PER_QUERY):
    records = []
    cursor = "*"
    while len(records) < max_results:
        params = {"query":query, "format":"json", "pageSize":min(100,max_results),
                  "cursorMark":cursor, "resultType":"core"}
        try:
            r = requests.get(EUROPEPMC_URL, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            results = data.get("resultList",{}).get("result",[])
            if not results: break
            for item in results:
                abstract = item.get("abstractText","")
                if not abstract or len(abstract) < 50: continue
                records.append({
                    "pmid":str(item.get("pmid","")), "doi":item.get("doi","") or "",
                    "title":item.get("title",""), "abstract":abstract,
                    "authors":item.get("authorString",""),
                    "journal":item.get("journalTitle",""),
                    "pub_date":item.get("firstPublicationDate",""),
                    "pub_year":str(item.get("pubYear","")),
                    "mesh_terms":"", "source_database":"europepmc",
                })
            nc = data.get("nextCursorMark","")
            if nc == cursor or not nc: break
            cursor = nc
            time.sleep(DELAY_EUROPEPMC)
        except Exception as e:
            print(f"    ✗ Europe PMC error: {e}"); break
    return records[:max_results]

# ================================================================================
# Semantic Scholar API
# ================================================================================

SEMANTIC_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

def semantic_search(query, max_results=MAX_SEMANTIC_PER_QUERY):
    records = []
    offset = 0
    batch = min(100, max_results)
    while offset < max_results:
        params = {"query":query, "offset":offset, "limit":batch,
                  "fields":"paperId,externalIds,title,abstract,authors,journal,year,publicationDate,citationCount"}
        try:
            r = requests.get(SEMANTIC_URL, params=params, timeout=30,
                 headers={"x-api-key": SEMANTIC_SCHOLAR_API_KEY} if SEMANTIC_SCHOLAR_API_KEY else {})
            if r.status_code == 429:
                print("    ⏱ Rate limited, waiting 60s...")
                time.sleep(60); continue
            r.raise_for_status()
            papers = r.json().get("data",[])
            if not papers: break
            for p in papers:
                abstract = p.get("abstract","") or ""
                if len(abstract) < 50: continue
                ext = p.get("externalIds",{}) or {}
                anames = [a.get("name","") for a in (p.get("authors",[]) or [])[:5] if a.get("name")]
                ji = p.get("journal",{}) or {}
                jn = ji.get("name","") if isinstance(ji,dict) else ""
                records.append({
                    "pmid":str(ext.get("PubMed","")), "doi":ext.get("DOI","") or "",
                    "title":p.get("title",""), "abstract":abstract,
                    "authors":"; ".join(anames), "journal":jn,
                    "pub_date":p.get("publicationDate",""),
                    "pub_year":str(p.get("year","")),
                    "mesh_terms":"", "source_database":"semantic_scholar",
                    "citation_count":p.get("citationCount",0),
                })
            offset += batch
            time.sleep(DELAY_SEMANTIC)
        except Exception as e:
            print(f"    ✗ Semantic Scholar error: {e}"); break
    return records[:max_results]

# ================================================================================
# BUILD RECORD
# ================================================================================

def build_record(raw, query_label):
    text = (raw.get("title","") + " " + raw.get("abstract","")).strip()
    tl = text.lower()
    ages = extract_ages(text)
    stats = extract_stats(text)
    cols = extract_columns(text)
    max_age = str(max(int(a) for a in ages.split(","))) if ages else ""

    rec = {
        "pmid":            raw.get("pmid",""),
        "doi":             raw.get("doi",""),
        "source_database": raw.get("source_database",""),
        "matched_query":   query_label,
        "scraped_date":    datetime.now().strftime("%Y-%m-%d"),
        "title":           raw.get("title",""),
        "journal":         raw.get("journal",""),
        "authors":         raw.get("authors",""),
        "pub_date":        raw.get("pub_date",""),
        "pub_year":        raw.get("pub_year",""),
        "mesh_terms":      raw.get("mesh_terms",""),
        "abstract":        raw.get("abstract",""),
        "word_count":      len(raw.get("abstract","").split()),
        "study_type":          classify_study_type(text),
        "population_country":  extract_population_country(text),
        "ages_mentioned":      ages,
        "max_age":             max_age,
        "stat_odds_ratio":          stats.get("odds_ratio",""),
        "stat_hazard_ratio":        stats.get("hazard_ratio",""),
        "stat_relative_risk":       stats.get("relative_risk",""),
        "stat_sample_size":         stats.get("sample_size",""),
        "stat_percentage":          stats.get("percentage",""),
        "stat_p_value":             stats.get("p_value",""),
        "stat_confidence_interval": stats.get("confidence_interval",""),
        "has_age":   bool(ages),
        "has_stats": bool(stats),
        "citation_count": raw.get("citation_count",""),
        "is_centenarian_focused": any(
            kw in tl for kw in [
                "centenarian","supercentenarian","100-year",
                "exceptional longevity","extreme longevity"]),
    }
    rec.update(cols)
    return rec

# ================================================================================
# SAVE
# ================================================================================

def load_seen_ids(path):
    if not os.path.exists(path): return set(), set()
    try:
        df = pd.read_csv(path, usecols=["pmid","doi"])
        pmids = set(str(x) for x in df["pmid"].dropna() if str(x).strip())
        dois = set(str(x) for x in df["doi"].dropna() if str(x).strip())
        return pmids, dois
    except: return set(), set()

def save_record(rec, path, write_header):
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rec.keys())
        if write_header: w.writeheader()
        w.writerow(rec)

# ================================================================================
# MAIN
# ================================================================================

def run():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    seen_pmids, seen_dois = load_seen_ids(out_path)
    write_hdr = (len(seen_pmids) + len(seen_dois)) == 0
    session_saved = 0

    print("="*70)
    print("  REJUVE LONGEVITY — Academic Paper Scraper v2.0")
    print(f"  Queries:       {len(QUERIES)}")
    print(f"  Databases:     PubMed, Europe PMC, Semantic Scholar")
    print(f"  Output:        {out_path}")
    print(f"  Already have:  {len(seen_pmids)} PMIDs, {len(seen_dois)} DOIs")
    print("="*70)

    def process_and_save(raw_list, query_label):
        """Build records and save immediately. Crash-safe."""
        nonlocal write_hdr, session_saved
        saved = 0
        for raw in raw_list:
            pmid = str(raw.get("pmid","")).strip()
            doi  = str(raw.get("doi","")).strip()
            if pmid and pmid in seen_pmids: continue
            if doi  and doi  in seen_dois:  continue
            key = pmid or doi
            if not key: continue
            try:
                rec = build_record(raw, query_label)
                save_record(rec, out_path, write_hdr)
                write_hdr = False
                session_saved += 1
                saved += 1
                if pmid: seen_pmids.add(pmid)
                if doi:  seen_dois.add(doi)
            except Exception:
                continue
        return saved

    try:
        # ── PASS 1: PubMed ───────────────────────────────────────────
        print(f"\n{'─'*70}")
        print(f"  PASS 1: PubMed ({len(QUERIES)} queries)")
        print(f"{'─'*70}")

        for qi, (label, query) in enumerate(QUERIES):
            print(f"  [{qi+1}/{len(QUERIES)}] {label}: ", end="", flush=True)
            pmids = pubmed_search(query)
            print(f"{len(pmids)} IDs", end="", flush=True)
            if pmids:
                all_recs = []
                for i in range(0, len(pmids), 200):
                    batch = pmids[i:i+200]
                    recs = pubmed_fetch_batch(batch)
                    all_recs.extend(recs)
                    time.sleep(DELAY_PUBMED)
                sv = process_and_save(all_recs, label)
                print(f" -> {sv} saved (total: {session_saved})")
            else:
                print()
            time.sleep(DELAY_PUBMED)

        # ── PASS 2: Europe PMC ───────────────────────────────────────
        print(f"\n{'─'*70}")
        print(f"  PASS 2: Europe PMC ({len(QUERIES)} queries)")
        print(f"{'─'*70}")

        for qi, (label, query) in enumerate(QUERIES):
            print(f"  [{qi+1}/{len(QUERIES)}] {label}: ", end="", flush=True)
            recs = europepmc_search(query)
            sv = process_and_save(recs, label)
            print(f"{len(recs)} results -> {sv} saved (total: {session_saved})")
            time.sleep(DELAY_EUROPEPMC)

        # ── PASS 3: Semantic Scholar ─────────────────────────────────
        print(f"\n{'─'*70}")
        print(f"  PASS 3: Semantic Scholar (core + named studies only)")
        print(f"{'─'*70}")

        ss_queries = [(l,q) for l,q in QUERIES
                      if l.startswith("core_") or l.startswith("study_")]
        for qi, (label, query) in enumerate(ss_queries):
            print(f"  [{qi+1}/{len(ss_queries)}] {label}: ", end="", flush=True)
            recs = semantic_search(query)
            sv = process_and_save(recs, label)
            print(f"{len(recs)} results -> {sv} saved (total: {session_saved})")
            time.sleep(DELAY_SEMANTIC)

    except KeyboardInterrupt:
        print("\n\n⚠ Interrupted — progress saved")

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  DONE | Session: {session_saved} new papers")
    print(f"{'='*70}")

    if os.path.exists(out_path):
        df = pd.read_csv(out_path)
        print(f"\n  TOTAL: {len(df)} papers")
        print(f"  Centenarian focused: {df['is_centenarian_focused'].sum()}")
        print(f"  With age mentions:   {df['has_age'].sum()}")
        print(f"  With statistics:     {df['has_stats'].sum()}")
        print(f"  Avg word count:      {int(df['word_count'].mean())}")

        print(f"\n  BY DATABASE:")
        for db,ct in df["source_database"].value_counts().items():
            print(f"    {db:<25} {ct}")
        print(f"\n  BY STUDY TYPE:")
        for st,ct in df["study_type"].value_counts().items():
            print(f"    {st:<25} {ct}")
        print(f"\n  BY POPULATION COUNTRY (top 15):")
        countries = df["population_country"].dropna().str.split(",").explode().str.strip()
        for co,ct in countries.value_counts().head(15).items():
            if co: print(f"    {co:<25} {ct}")

        tc = [c for c in df.columns if c.startswith("trait_")]
        bc = [c for c in df.columns if c.startswith("biomarker_")]
        gc = [c for c in df.columns if c.startswith("gene_")]
        print(f"\n  TRAIT COVERAGE:")
        for c in tc: print(f"    {c:<30} {df[c].sum():>5}")
        print(f"\n  BIOMARKER COVERAGE:")
        for c in bc: print(f"    {c:<30} {df[c].sum():>5}")
        print(f"\n  GENE COVERAGE:")
        for c in gc: print(f"    {c:<30} {df[c].sum():>5}")
        print(f"\n  TOP JOURNALS:")
        for j,ct in df["journal"].value_counts().head(20).items():
            if j: print(f"    {j:<45} {ct}")

        prev = out_path.replace(".csv","_preview.csv")
        df[[c for c in df.columns if c!="abstract"]].to_csv(
            prev, index=False, encoding="utf-8")
        print(f"\n  FILES:\n    {out_path}\n    {prev}")

if __name__ == "__main__":
    run()
