"""
================================================================================
REJUVE LONGEVITY APP — Centenarian Data Pipeline
FILE: scraper_datasets.py
VERSION: 2.0
PURPOSE: Downloads publicly available centenarian, longevity, and biomarker
         datasets from structured sources.

DATASETS:
  1. TidyTuesday/frankiethull centenarians  — verified oldest people (CSV)
  2. Wikipedia supercentenarian tables      — names, ages, countries, occupations
  3. GRG supercentenarians                  — validated 110+ records
  4. LongeviQuest                           — modern validation database
  5. NHANES biomarkers                      — population biomarker distributions
  6. NHANES DNA methylation                 — epigenetic biological age
  7. BioAge reference                       — biological aging algorithm info
  8. UN World Population Prospects          — centenarian population by country
  9. Our World in Data life expectancy      — historical life expectancy
  10. GapMinder                             — life expectancy 1800-present
  11. Italian supercentenarian genomics     — Figshare whole genome data
  12. Human Mortality Database              — manual download instructions

LICENSE NOTES:
  NHANES: Public domain (US government) — no restrictions including commercial
  Wikipedia: CC BY-SA — commercial OK with attribution
  OWID/GapMinder: CC BY — commercial OK with attribution
  GRG/LongeviQuest: Public data — freely listed
  TidyTuesday: Public — freely available

OUTPUT: data/raw/datasets/
DEPENDENCIES: pip install requests beautifulsoup4 pandas
AUTHOR: Rejuve Longevity (open-source)
LICENSE: MIT
================================================================================
"""

import time, re, os, io
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime

OUTPUT_DIR = "data/raw/datasets"
DELAY = 2.0
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}

def save_df(df, filename, description):
    path = os.path.join(OUTPUT_DIR, filename)
    df.to_csv(path, index=False, encoding="utf-8")
    print(f"  ✓ {len(df)} rows → {filename}")
    print(f"    {description}")
    return path

def get(url, **kwargs):
    """Simple GET with headers."""
    return requests.get(url, headers=HEADERS, timeout=60, **kwargs)


# ================================================================================
# DATASET 1: TidyTuesday centenarians (from frankiethull)
# ================================================================================

def download_centenarian_csv():
    print("\n── Dataset 1: TidyTuesday/frankiethull centenarians ──")

    # Hosted in the TidyTuesday repo — correct URLs
    urls = [
        ("centenarians",
         "https://raw.githubusercontent.com/rfordatascience/tidytuesday/main/data/2023/2023-05-30/centenarians.csv",
         "Top 100 verified oldest people ever"),
    ]

    for label, url, desc in urls:
        try:
            print(f"  Downloading {label}...")
            r = get(url)
            if r.status_code == 200:
                df = pd.read_csv(io.StringIO(r.text))
                df["dataset_source"] = "tidytuesday_centenarians"
                df["dataset_type"] = "centenarian_records"
                df["license"] = "Public"
                save_df(df, f"tidytuesday_{label}.csv", desc)
            else:
                print(f"    ✗ Status {r.status_code}")
        except Exception as e:
            print(f"    ✗ {e}")
        time.sleep(DELAY)


# ================================================================================
# DATASET 2: Wikipedia supercentenarian tables
# ================================================================================

def download_wikipedia():
    print("\n── Dataset 2: Wikipedia supercentenarians ──")

    pages = [
        ("oldest_verified",   "https://en.wikipedia.org/wiki/List_of_verified_oldest_people"),
        ("oldest_living",     "https://en.wikipedia.org/wiki/List_of_living_supercentenarians"),
        ("oldest_men",        "https://en.wikipedia.org/wiki/List_of_the_verified_oldest_men"),
        ("supercentenarians", "https://en.wikipedia.org/wiki/List_of_supercentenarians"),
    ]

    all_rows = []
    for label, url in pages:
        try:
            print(f"  Fetching {label}...")
            r = get(url)
            if r.status_code != 200:
                print(f"    ✗ Status {r.status_code}")
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            tables = soup.find_all("table", class_="wikitable")
            page_total = 0
            for ti, table in enumerate(tables):
                try:
                    dfs = pd.read_html(io.StringIO(str(table)))
                    if dfs:
                        df = dfs[0]
                        if isinstance(df.columns, pd.MultiIndex):
                            df.columns = [" ".join(str(c) for c in col).strip()
                                          for col in df.columns]
                        df["wiki_page"] = label
                        all_rows.append(df)
                        page_total += len(df)
                except Exception:
                    continue
            print(f"    {page_total} rows from {len(tables)} tables")
        except Exception as e:
            print(f"    ✗ {e}")
        time.sleep(DELAY)

    if all_rows:
        combined = pd.concat(all_rows, ignore_index=True)
        combined["dataset_source"] = "wikipedia"
        combined["dataset_type"] = "centenarian_records"
        combined["license"] = "CC BY-SA"
        save_df(combined, "wikipedia_supercentenarians.csv",
                "Wikipedia supercentenarian tables — names, ages, nationalities, occupations")


# ================================================================================
# DATASET 3: GRG
# ================================================================================

def download_grg():
    print("\n── Dataset 3: GRG supercentenarians ──")

    # Try both www and non-www, and alternative paths
    urls_to_try = [
        ("oldest_living", "https://grg.org/WSRT.HTM"),
        ("oldest_living", "https://www.grg-supercentenarians.org/worlds-oldest-people/"),
        ("oldest_living", "https://grg-supercentenarians.org/worlds-oldest-people/"),
    ]

    all_rows = []
    for label, url in urls_to_try:
        try:
            print(f"  Trying {url}...")
            r = get(url)
            if r.status_code != 200:
                print(f"    ✗ Status {r.status_code}")
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            tables = soup.find_all("table")
            page_total = 0
            for table in tables:
                try:
                    dfs = pd.read_html(io.StringIO(str(table)))
                    if dfs:
                        df = dfs[0]
                        if isinstance(df.columns, pd.MultiIndex):
                            df.columns = [" ".join(str(c) for c in col).strip()
                                          for col in df.columns]
                        df["grg_page"] = label
                        all_rows.append(df)
                        page_total += len(df)
                except Exception:
                    continue
            if page_total > 0:
                print(f"    {page_total} rows")
                break
        except Exception as e:
            print(f"    ✗ {e}")
        time.sleep(DELAY)

    if all_rows:
        combined = pd.concat(all_rows, ignore_index=True)
        combined["dataset_source"] = "grg"
        combined["dataset_type"] = "centenarian_records"
        combined["license"] = "Public"
        save_df(combined, "grg_supercentenarians.csv",
                "GRG validated supercentenarians")
    else:
        print("  ℹ GRG site not accessible — Wikipedia data covers this.")


# ================================================================================
# DATASET 4: LongeviQuest
# ================================================================================

def download_longeviquest():
    print("\n── Dataset 4: LongeviQuest ──")

    urls_to_try = [
        "https://longeviquest.com/oldest-living-people/",
        "https://www.longeviquest.com/oldest-living-people/",
        "https://longeviquest.com/supercentenarians/",
    ]

    all_rows = []
    for url in urls_to_try:
        try:
            print(f"  Trying {url}...")
            r = get(url)
            if r.status_code != 200:
                print(f"    ✗ Status {r.status_code}")
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            tables = soup.find_all("table")
            page_total = 0
            for table in tables:
                try:
                    dfs = pd.read_html(io.StringIO(str(table)))
                    if dfs:
                        df = dfs[0]
                        all_rows.append(df)
                        page_total += len(df)
                except Exception:
                    continue
            if page_total > 0:
                print(f"    {page_total} rows")
        except Exception as e:
            print(f"    ✗ {e}")
        time.sleep(DELAY)

    if all_rows:
        combined = pd.concat(all_rows, ignore_index=True)
        combined["dataset_source"] = "longeviquest"
        combined["dataset_type"] = "centenarian_records"
        combined["license"] = "Public"
        save_df(combined, "longeviquest_supercentenarians.csv",
                "LongeviQuest validated supercentenarians")
    else:
        print("  ℹ LongeviQuest not accessible — Wikipedia data covers this.")


# ================================================================================
# DATASET 5: NHANES biomarkers
# Correct URL pattern: https://wwwn.cdc.gov/nchs/nhanes/YYYY-YYYY/FILENAME.XPT
# Note: pandas read_sas needs the raw bytes, not a streamed response
# ================================================================================

def download_nhanes():
    print("\n── Dataset 5: NHANES biomarkers ──")

    # Correct base URL pattern confirmed from CDC documentation
    BASE = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/{}.XPT"

    datasets = [
        ("DEMO_J",   "demographics",      "Age, sex, race, income, education"),
        ("HSCRP_J",  "crp",               "High-sensitivity CRP (inflammation)"),
        ("GLU_J",    "glucose",           "Fasting glucose and insulin"),
        ("GHB_J",    "glycohemoglobin",   "HbA1c — long-term glucose control"),
        ("TCHOL_J",  "cholesterol_total", "Total cholesterol"),
        ("HDL_J",    "cholesterol_hdl",   "HDL cholesterol"),
        ("TRIGLY_J", "triglycerides",     "Triglycerides and LDL"),
        ("BPX_J",    "blood_pressure",    "Blood pressure measurements"),
        ("BMX_J",    "body_measures",     "BMI, waist, height, weight"),
        ("CBC_J",    "cbc",               "Complete blood count"),
        ("PAQ_J",    "physical_activity", "Physical activity questionnaire"),
        ("SMQ_J",    "smoking",           "Smoking questionnaire"),
        ("ALQ_J",    "alcohol",           "Alcohol questionnaire"),
        ("SLQ_J",    "sleep",             "Sleep questionnaire"),
        ("DIQ_J",    "diabetes",          "Diabetes questionnaire"),
    ]

    saved = []
    for file_stem, label, description in datasets:
        url = BASE.format(file_stem)
        try:
            print(f"  {label}... ", end="", flush=True)
            r = get(url)
            if r.status_code != 200:
                print(f"✗ Status {r.status_code}")
                continue

            # Read XPT from bytes
            df = pd.read_sas(io.BytesIO(r.content), format="xport")
            df["nhanes_file"] = file_stem
            df["nhanes_cycle"] = "2017-2018"
            df["dataset_source"] = "nhanes"
            df["dataset_type"] = "biomarker_reference"
            df["license"] = "Public domain"

            filename = f"nhanes_{label}.csv"
            save_df(df, filename, description)
            saved.append(filename)

        except Exception as e:
            print(f"✗ {e}")
        time.sleep(DELAY)

    print(f"  NHANES: {len(saved)} files saved")
    return saved


# ================================================================================
# DATASET 6: NHANES DNA methylation epigenetic biomarkers
# ================================================================================

def download_nhanes_epigenetic():
    print("\n── Dataset 6: NHANES DNA methylation ──")

    # Correct URL from CDC documentation search
    urls_to_try = [
        "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Dnam/DNAMBIOAGE_A.XPT",
        "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Dnam/DNAMBIOAGE_A.XPT",
    ]

    for url in urls_to_try:
        try:
            print(f"  Trying {url}...")
            r = get(url)
            if r.status_code == 200:
                df = pd.read_sas(io.BytesIO(r.content), format="xport")
                df["dataset_source"] = "nhanes_dnam"
                df["dataset_type"] = "biomarker_reference"
                df["license"] = "Public domain"
                save_df(df, "nhanes_epigenetic_bioage.csv",
                        "Horvath clock, GrimAge, PhenoAge, DunedinPACE")
                return
            else:
                print(f"    ✗ Status {r.status_code}")
        except Exception as e:
            print(f"    ✗ {e}")
        time.sleep(DELAY)

    print("  ℹ Epigenetic data not available at current URLs.")
    print("    Manual download: https://wwwn.cdc.gov/nchs/nhanes/search/datapage.aspx")


# ================================================================================
# DATASET 7: BioAge reference info
# ================================================================================

def download_bioage_info():
    print("\n── Dataset 7: BioAge reference ──")
    try:
        r = get("https://raw.githubusercontent.com/dayoonkwon/BioAge/master/README.md")
        if r.status_code == 200:
            with open(os.path.join(OUTPUT_DIR, "bioage_README.txt"), "w") as f:
                f.write(r.text)
            print("  ✓ Saved BioAge README")
            print("    Note: NHANES data (Dataset 5) is the underlying source.")
    except Exception as e:
        print(f"  ✗ {e}")


# ================================================================================
# DATASET 8: Our World in Data — Life expectancy
# ================================================================================

def download_owid():
    print("\n── Dataset 8: Our World in Data ──")

    urls = [
        "https://raw.githubusercontent.com/owid/owid-datasets/master/datasets/Life%20expectancy%20-%20Gapminder%2C%20UN/Life%20expectancy%20-%20Gapminder%2C%20UN.csv",
        "https://raw.githubusercontent.com/owid/owid-datasets/master/datasets/Life%20expectancy%20(Gapminder%2C%20UN%20%26%20UN%20WPP)/Life%20expectancy%20(Gapminder%2C%20UN%20%26%20UN%20WPP).csv",
        "https://raw.githubusercontent.com/owid/owid-datasets/master/datasets/Life%20expectancy%20at%20birth%20(various%20sources)/Life%20expectancy%20at%20birth%20(various%20sources).csv",
    ]

    for url in urls:
        try:
            print(f"  Trying OWID...")
            r = get(url)
            if r.status_code == 200:
                df = pd.read_csv(io.StringIO(r.text))
                df["dataset_source"] = "owid"
                df["dataset_type"] = "population_longevity"
                df["license"] = "CC BY"
                save_df(df, "owid_life_expectancy.csv",
                        "Life expectancy by country — historical to present")
                return
            else:
                print(f"    ✗ Status {r.status_code}")
        except Exception as e:
            print(f"    ✗ {e}")
        time.sleep(DELAY)

    # Final fallback — OWID GitHub search
    try:
        print("  Trying OWID GitHub API search...")
        api = "https://api.github.com/repos/owid/owid-datasets/contents/datasets"
        r = requests.get(api, timeout=15)
        if r.status_code == 200:
            folders = [item["name"] for item in r.json()
                       if "life" in item["name"].lower() and "expect" in item["name"].lower()]
            if folders:
                folder = folders[0]
                files_r = requests.get(f"{api}/{requests.utils.quote(folder)}", timeout=15)
                if files_r.status_code == 200:
                    csv_files = [f for f in files_r.json() if f["name"].endswith(".csv")]
                    if csv_files:
                        csv_r = requests.get(csv_files[0]["download_url"], timeout=30)
                        if csv_r.status_code == 200:
                            df = pd.read_csv(io.StringIO(csv_r.text))
                            df["dataset_source"] = "owid"
                            df["dataset_type"] = "population_longevity"
                            df["license"] = "CC BY"
                            save_df(df, "owid_life_expectancy.csv",
                                    "Life expectancy by country")
                            return
    except Exception as e:
        print(f"    ✗ {e}")

    print("  ℹ OWID direct download failed. Manual: https://ourworldindata.org/life-expectancy")


# ================================================================================
# DATASET 9: GapMinder
# ================================================================================

def download_gapminder():
    print("\n── Dataset 9: GapMinder ──")

    urls = [
        "https://raw.githubusercontent.com/open-numbers/ddf--gapminder--systema_globalis/master/countries-etc-datapoints/ddf--datapoints--life_expectancy_years--by--geo--time.csv",
        "https://raw.githubusercontent.com/jennybc/gapminder/master/inst/extdata/gapminder.tsv",
    ]

    for url in urls:
        try:
            print(f"  Trying GapMinder...")
            r = get(url)
            if r.status_code == 200:
                sep = "\t" if url.endswith(".tsv") else ","
                df = pd.read_csv(io.StringIO(r.text), sep=sep)
                df["dataset_source"] = "gapminder"
                df["dataset_type"] = "population_longevity"
                df["license"] = "CC BY 4.0"
                save_df(df, "gapminder_life_expectancy.csv",
                        "Life expectancy by country 1800-present")
                return
            else:
                print(f"    ✗ Status {r.status_code}")
        except Exception as e:
            print(f"    ✗ {e}")
        time.sleep(DELAY)

    print("  ℹ Manual download: https://www.gapminder.org/data/")


# ================================================================================
# DATASET 10: UN World Population Prospects
# ================================================================================

def download_un():
    print("\n── Dataset 10: UN World Population Prospects ──")

    # UN 2024 revision — country-level indicators
    urls = [
        "https://population.un.org/wpp/assets/Files/WPP2024_GEN_F01_DEMOGRAPHIC_INDICATORS_COMPACT.xlsx",
        "https://population.un.org/wpp/assets/Excel_Files/1_Indicators_(Standard)/CSV_FILES/WPP2024_Demographic_Indicators_Medium.csv.gz",
    ]

    for url in urls:
        try:
            ext = ".xlsx" if url.endswith(".xlsx") else ".csv.gz"
            print(f"  Trying UN data ({ext})...")
            r = get(url, stream=True)
            if r.status_code == 200:
                raw_path = os.path.join(OUTPUT_DIR, f"un_wpp_raw{ext}")
                with open(raw_path, "wb") as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)
                print(f"    Downloaded to {raw_path}")

                if ext == ".csv.gz":
                    df = pd.read_csv(raw_path, compression="gzip", low_memory=False)
                else:
                    df = pd.read_excel(raw_path, sheet_name=0)

                df["dataset_source"] = "un_wpp"
                df["dataset_type"] = "population_longevity"
                df["license"] = "CC BY 3.0 IGO"
                save_df(df, "un_population_prospects.csv",
                        "UN World Population Prospects 2024")
                return
            else:
                print(f"    ✗ Status {r.status_code}")
        except Exception as e:
            print(f"    ✗ {e}")
        time.sleep(DELAY)

    print("  ℹ Manual download: https://population.un.org/wpp/downloads")


# ================================================================================
# DATASET 11: Italian supercentenarian genomics (Figshare)
# ================================================================================

def download_figshare_genomics():
    print("\n── Dataset 11: Italian supercentenarian genomics ──")

    # Figshare API for this specific dataset
    url = "https://api.figshare.com/v2/articles/12367085"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            print(f"  Title: {data.get('title','')}")
            print(f"  Description: {str(data.get('description',''))[:100]}...")
            files = data.get("files", [])
            print(f"  Files available: {len(files)}")
            for f in files[:5]:
                print(f"    - {f.get('name','')} ({f.get('size',0)/1024:.0f} KB)")

            # Save metadata
            meta_df = pd.DataFrame(files)
            if not meta_df.empty:
                meta_df["dataset_source"] = "figshare_italian_genomics"
                meta_df["dataset_type"] = "genomics"
                meta_df["license"] = "CC BY 4.0"
                save_df(meta_df, "figshare_italian_genomics_metadata.csv",
                        "Italian semi-supercentenarian WGS — 81 subjects + 36 controls")

            # Note about full data
            print("  ℹ Full genomic data is large (WGS).")
            print("    Download individual files from: https://figshare.com/articles/12367085")
        else:
            print(f"  ✗ Status {r.status_code}")
    except Exception as e:
        print(f"  ✗ {e}")


# ================================================================================
# DATASET 12: Human Mortality Database instructions
# ================================================================================

def hmd_instructions():
    print("\n── Dataset 12: Human Mortality Database ──")
    instructions = """HUMAN MORTALITY DATABASE — MANUAL DOWNLOAD INSTRUCTIONS
========================================================
1. Go to https://www.mortality.org
2. Create a free account (instant, no approval)
3. Navigate to Data → Download
4. Download: Life Tables (Period, 1x1) for ALL countries
5. Save to: data/raw/datasets/hmd/
6. merge_all.py will process them automatically.

License: Free for research and commercial use.
"""
    with open(os.path.join(OUTPUT_DIR, "hmd_DOWNLOAD_INSTRUCTIONS.txt"), "w", encoding="utf-8") as f:
        f.write(instructions)
    print("  ✓ Saved instructions → hmd_DOWNLOAD_INSTRUCTIONS.txt")


# ================================================================================
# DATASET 13: GWAS Catalog (filtered to longevity-related traits)
# ================================================================================

_GWAS_LONGEVITY_RE = re.compile(
    r"longevity|lifespan|life span|aging|ageing|centenarian|"
    r"life expectancy|mortality|supercentenarian|long[- ]lived",
    re.I,
)

def download_gwas_longevity():
    print("\n── Dataset 13: GWAS Catalog (longevity-filtered) ──")
    dest = os.path.join(OUTPUT_DIR, "gwas_longevity.csv")
    if os.path.exists(dest):
        print(f"  ↺ Already present: {dest} — skipping")
        return
    url = "https://www.ebi.ac.uk/gwas/api/search/downloads/full"
    try:
        r = get(url, timeout=300)
        if r.status_code != 200:
            print(f"  ✗ HTTP {r.status_code}")
            return
        df = pd.read_csv(io.BytesIO(r.content), sep="\t", low_memory=False,
                         dtype=str, encoding="utf-8", on_bad_lines="warn")
        trait_col = "DISEASE/TRAIT" if "DISEASE/TRAIT" in df.columns else next(
            (c for c in df.columns if "trait" in c.lower()), None)
        if not trait_col:
            print("  ✗ No trait column found")
            return
        filt = df[df[trait_col].fillna("").str.contains(_GWAS_LONGEVITY_RE)].copy()
        filt["dataset_source"] = "gwas_catalog"
        filt["dataset_type"]   = "genomic_reference"
        filt["license"]        = "EBI GWAS Catalog — public; cite the source studies"
        save_df(filt, "gwas_longevity.csv",
                "GWAS Catalog rows with longevity/lifespan/aging traits")
    except Exception as e:
        print(f"  ✗ {e}")


# ================================================================================
# DATASET 14: WHO Global Health Observatory — life expectancy + HALE
# ================================================================================

def download_who_life_expectancy():
    print("\n── Dataset 14: WHO GHO life expectancy + HALE ──")
    dest = os.path.join(OUTPUT_DIR, "who_life_expectancy.csv")
    if os.path.exists(dest):
        print(f"  ↺ Already present: {dest} — skipping")
        return
    urls = {
        "WHOSIS_000001": ("life_expectancy_at_birth",
                          "https://ghoapi.azureedge.net/api/WHOSIS_000001"),
        "WHOSIS_000002": ("hale_at_birth",
                          "https://ghoapi.azureedge.net/api/WHOSIS_000002"),
    }
    frames = []
    try:
        for code, (label, url) in urls.items():
            r = get(url, timeout=120)
            if r.status_code != 200:
                print(f"  ✗ {code} HTTP {r.status_code}")
                continue
            data = r.json().get("value", [])
            if not data:
                continue
            df = pd.DataFrame(data)
            df["WHO_indicator"]       = code
            df["WHO_indicator_label"] = label
            frames.append(df)
            time.sleep(DELAY)
        if not frames:
            print("  ✗ No data")
            return
        out = pd.concat(frames, ignore_index=True)
        out["dataset_source"] = "who_gho"
        out["dataset_type"]   = "population_reference"
        out["license"]        = "WHO GHO — public (cite as WHO Global Health Observatory)"
        save_df(out, "who_life_expectancy.csv",
                "WHO life expectancy at birth + HALE, country×year")
    except Exception as e:
        print(f"  ✗ {e}")


# ================================================================================
# DATASET 15: Manually-supplied files — UN WPP XLSX, NHANES methylation SAS,
#              HMD country zips. These require a one-time manual download into
#              data/raw/datasets/ and data/raw/datasets/hmd/ respectively; this
#              function converts/combines them into CSVs.
# ================================================================================

def process_manual_files():
    print("\n── Dataset 15: process manually-supplied files ──")
    print("    (see process_new_datasets.py for the full conversion pipeline)")

    src_wpp = os.path.join(OUTPUT_DIR, "WPP2024_GEN_F01_DEMOGRAPHIC_INDICATORS_COMPACT.xlsx")
    out_wpp = os.path.join(OUTPUT_DIR, "un_population_prospects.csv")
    if os.path.exists(src_wpp) and not os.path.exists(out_wpp):
        try:
            xl = pd.ExcelFile(src_wpp)
            frames = []
            for sh in xl.sheet_names:
                if sh.lower() in ("notes", "metadata", "info"):
                    continue
                df = pd.read_excel(xl, sheet_name=sh, header=16, dtype=str)
                df["wpp_variant"] = sh
                frames.append(df)
            out = pd.concat(frames, ignore_index=True).dropna(how="all")
            save_df(out, "un_population_prospects.csv",
                    "UN WPP 2024 compact demographic indicators")
        except Exception as e:
            print(f"  ✗ UN WPP: {e}")

    src_meth = os.path.join(OUTPUT_DIR, "dnmepi.sas7bdat")
    out_meth = os.path.join(OUTPUT_DIR, "nhanes_methylation.csv")
    if os.path.exists(src_meth) and not os.path.exists(out_meth):
        try:
            import pyreadstat
            df, _ = pyreadstat.read_sas7bdat(src_meth)
            save_df(df, "nhanes_methylation.csv",
                    "NHANES DNA methylation / epigenetic clocks")
        except ImportError:
            print("  ✗ pyreadstat not installed; pip install pyreadstat")
        except Exception as e:
            print(f"  ✗ NHANES methylation: {e}")

    # HMD processing is heavyweight (41 zips + warning scrape); delegated to
    # process_new_datasets.py to avoid blocking the standard scraper run.
    hmd_dir = os.path.join(OUTPUT_DIR, "hmd")
    if os.path.isdir(hmd_dir) and not os.path.exists(os.path.join(OUTPUT_DIR, "hmd_life_tables.csv")):
        print("  ℹ HMD zips present — run process_new_datasets.py to build "
              "hmd_life_tables.csv + scrape mortality.org quality warnings")


# ================================================================================
# MAIN
# ================================================================================

def run():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("="*70)
    print("  REJUVE LONGEVITY — Dataset Downloader v2.0")
    print(f"  Output: {OUTPUT_DIR}")
    print("="*70)

    download_centenarian_csv()
    download_wikipedia()
    download_grg()
    download_longeviquest()
    download_nhanes()
    download_nhanes_epigenetic()
    download_bioage_info()
    download_owid()
    download_gapminder()
    download_un()
    download_figshare_genomics()
    hmd_instructions()
    download_gwas_longevity()
    download_who_life_expectancy()
    process_manual_files()

    # Summary
    print(f"\n{'='*70}")
    print(f"  DONE")
    print(f"{'='*70}\n")

    files = sorted(f for f in os.listdir(OUTPUT_DIR) if f.endswith(".csv"))
    print(f"  CSV files: {len(files)}")
    for f in files:
        path = os.path.join(OUTPUT_DIR, f)
        size_kb = os.path.getsize(path) / 1024
        try:
            rows = len(pd.read_csv(path, low_memory=False))
            print(f"    {f:<50} {rows:>8} rows  {size_kb:>8.0f} KB")
        except:
            print(f"    {f:<50} (unreadable)")

    other = sorted(f for f in os.listdir(OUTPUT_DIR) if not f.endswith(".csv"))
    if other:
        print(f"\n  Other files:")
        for f in other:
            size_kb = os.path.getsize(os.path.join(OUTPUT_DIR, f)) / 1024
            print(f"    {f:<50} {size_kb:>8.0f} KB")

    print(f"\n  All files in: {OUTPUT_DIR}")


if __name__ == "__main__":
    run()
