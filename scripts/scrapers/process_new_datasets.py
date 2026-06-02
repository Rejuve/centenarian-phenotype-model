"""
Download / process the new datasets requested:
  1. GWAS Catalog (full → filter for longevity traits)
  2. WHO Global Health Observatory (life expectancy + HALE)
  3. UN World Population Prospects (compact XLSX → CSV)
  4. NHANES methylation (sas7bdat → CSV)
  5. HMD life tables (41 country zips → combined CSV)
  6. HMD country quality warnings (scrape mortality.org)
  7. Join warnings into HMD life tables (has_quality_warning column)

Each step is wrapped in try/except so one failure doesn't kill the rest.
Run: PYTHONIOENCODING=utf-8 python -u process_new_datasets.py
"""
import io
import re
import sys
import time
import zipfile
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

RAW   = Path("data/raw/datasets")
HMD   = RAW / "hmd"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Rejuve longevity research, contact: jasmine@rejuve.ai) "
                  "Centenarian-Clock-Phase2/1.0",
}


def _section(title):
    print(f"\n{'=' * 76}\n  {title}\n{'=' * 76}")


def _http_get(url, **kwargs):
    """GET with shared headers + default 60s timeout."""
    kwargs.setdefault("headers", HEADERS)
    kwargs.setdefault("timeout", 60)
    r = requests.get(url, **kwargs)
    r.raise_for_status()
    return r


# ─────────────────────────────────────────────────────────────────────────────
# 1. GWAS Catalog — full TSV, filter for longevity-related traits
# ─────────────────────────────────────────────────────────────────────────────

_LONGEVITY_TRAIT_RE = re.compile(
    r"longevity|lifespan|life span|aging|ageing|centenarian|"
    r"life expectancy|mortality|supercentenarian|long[- ]lived",
    re.I,
)

def step_gwas():
    _section("1. GWAS Catalog — download full TSV, filter for longevity traits")
    dest = RAW / "gwas_longevity.csv"
    # The /api/search/downloads/full endpoint was retired. The canonical
    # download is now the FTP-hosted ontology-annotated associations ZIP.
    url  = "https://ftp.ebi.ac.uk/pub/databases/gwas/releases/latest/gwas-catalog-associations_ontology-annotated-full.zip"
    print(f"  GET {url}")
    t0 = time.time()
    resp = _http_get(url, timeout=300)
    raw_size_mb = len(resp.content) / 1e6
    print(f"  Downloaded {raw_size_mb:.1f} MB in {time.time()-t0:.0f}s")

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        tsv_members = [m for m in zf.namelist() if m.endswith(".tsv")]
        if not tsv_members:
            print(f"  ERROR: no TSV inside zip; members: {zf.namelist()}")
            return
        print(f"  TSVs in zip: {tsv_members}")
        with zf.open(tsv_members[0]) as f:
            df = pd.read_csv(f, sep="\t", low_memory=False,
                             dtype=str, encoding="utf-8", on_bad_lines="warn")
    print(f"  Full catalog rows: {len(df):,}  cols: {len(df.columns)}")

    trait_col = "DISEASE/TRAIT"
    if trait_col not in df.columns:
        candidates = [c for c in df.columns if "trait" in c.lower() or "disease" in c.lower()]
        print(f"  WARN: 'DISEASE/TRAIT' missing — candidate trait cols: {candidates}")
        if candidates:
            trait_col = candidates[0]
        else:
            print("  ERROR: no trait column found")
            return

    mask = df[trait_col].fillna("").str.contains(_LONGEVITY_TRAIT_RE)
    filt = df[mask].copy()
    print(f"  Longevity-related rows: {len(filt):,}")
    filt.to_csv(dest, index=False)
    print(f"  Saved → {dest}")

    by_trait = filt[trait_col].value_counts().head(15)
    print(f"  Top 15 traits in filtered set:")
    for t, n in by_trait.items():
        print(f"    {n:>4}  {t}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. WHO Global Health Observatory — life expectancy + HALE
# ─────────────────────────────────────────────────────────────────────────────

def step_who():
    _section("2. WHO GHO — life expectancy (WHOSIS_000001) + HALE (WHOSIS_000002)")
    dest = RAW / "who_life_expectancy.csv"
    if dest.exists():
        print(f"  Already present: {dest} — skipping")
        return
    urls = {
        "WHOSIS_000001": "https://ghoapi.azureedge.net/api/WHOSIS_000001",  # LE at birth
        "WHOSIS_000002": "https://ghoapi.azureedge.net/api/WHOSIS_000002",  # HALE at birth
    }
    frames = []
    for code, url in urls.items():
        print(f"  GET {url}")
        resp = _http_get(url, timeout=120)
        js = resp.json()
        rows = js.get("value", [])
        if not rows:
            print(f"    WARN: empty response for {code}")
            continue
        df = pd.DataFrame(rows)
        df["WHO_indicator"] = code
        df["WHO_indicator_label"] = "life_expectancy_at_birth" if code == "WHOSIS_000001" else "hale_at_birth"
        print(f"    {code} rows: {len(df):,}  cols: {len(df.columns)}")
        frames.append(df)

    if not frames:
        print("  ERROR: no WHO data downloaded")
        return

    out = pd.concat(frames, ignore_index=True)
    keep = [
        "WHO_indicator", "WHO_indicator_label",
        "SpatialDimType", "SpatialDim",        # country/region code
        "TimeDimType",    "TimeDim",            # year
        "Dim1Type",       "Dim1",               # sex stratification when present
        "NumericValue",   "Value",              # numeric & string forms
        "Low", "High",
    ]
    keep = [c for c in keep if c in out.columns]
    out = out[keep]
    out.to_csv(dest, index=False)
    print(f"  Combined rows: {len(out):,}")
    print(f"  Saved → {dest}")
    print(f"  Sample:")
    print(out.head(3).to_string(max_cols=8, max_colwidth=18, index=False))


# ─────────────────────────────────────────────────────────────────────────────
# 3. UN WPP — compact demographic indicators XLSX → CSV
# ─────────────────────────────────────────────────────────────────────────────

def step_un_wpp():
    _section("3. UN WPP — load compact XLSX, save as CSV")
    src  = RAW / "WPP2024_GEN_F01_DEMOGRAPHIC_INDICATORS_COMPACT.xlsx"
    dest = RAW / "un_population_prospects.csv"
    if dest.exists():
        print(f"  Already present: {dest} — skipping")
        return
    if not src.exists():
        print(f"  ERROR: {src} not present")
        return

    print(f"  Reading {src.name} ({src.stat().st_size/1e6:.1f} MB) ...")
    xl = pd.ExcelFile(src)
    print(f"  Sheets: {xl.sheet_names}")

    # The compact indicators file has 'Estimates' and 'Medium variant' sheets.
    # Both have the same column structure; concatenate them.
    frames = []
    for sheet in xl.sheet_names:
        if sheet.lower() in ("notes", "metadata", "info"):
            continue
        # Skip the title rows — actual headers usually on row 16 (0-indexed)
        df = pd.read_excel(xl, sheet_name=sheet, header=16, dtype=str)
        df["wpp_variant"] = sheet
        print(f"    sheet '{sheet}': {len(df):,} rows  {len(df.columns)} cols")
        frames.append(df)

    if not frames:
        print("  ERROR: no usable sheets")
        return
    out = pd.concat(frames, ignore_index=True)
    # Drop entirely-empty rows (Excel artifacts)
    out = out.dropna(axis=0, how="all").reset_index(drop=True)
    out.to_csv(dest, index=False)
    print(f"  Combined rows: {len(out):,}  cols: {len(out.columns)}")
    print(f"  First 6 columns: {list(out.columns[:6])}")
    print(f"  Saved → {dest}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. NHANES methylation — sas7bdat via pyreadstat
# ─────────────────────────────────────────────────────────────────────────────

def step_nhanes_methylation():
    _section("4. NHANES methylation — read dnmepi.sas7bdat via pyreadstat")
    src  = RAW / "dnmepi.sas7bdat"
    dest = RAW / "nhanes_methylation.csv"
    if dest.exists():
        print(f"  Already present: {dest} — skipping")
        return
    if not src.exists():
        print(f"  ERROR: {src} not present")
        return
    try:
        import pyreadstat
    except ImportError:
        print("  ERROR: pyreadstat not installed — run: pip install pyreadstat")
        return

    print(f"  Reading {src.name} ({src.stat().st_size/1e6:.2f} MB) ...")
    df, meta = pyreadstat.read_sas7bdat(str(src))
    print(f"  Rows: {len(df):,}  cols: {len(df.columns)}")
    print(f"  Columns: {list(df.columns)}")
    if hasattr(meta, "column_labels"):
        labels = {c: l for c, l in zip(meta.column_names, meta.column_labels) if l}
        if labels:
            print(f"  Column labels (where defined):")
            for c, l in list(labels.items())[:25]:
                print(f"    {c:<20} {l}")
    df.to_csv(dest, index=False)
    print(f"  Saved → {dest}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. HMD life tables — extract STATS/*lt*per_1x1.{csv,txt} from 41 country zips
# ─────────────────────────────────────────────────────────────────────────────

# Map: country-code-from-zip-filename → human-readable name
HMD_COUNTRY_NAMES = {
    "AUS": "Australia", "AUT": "Austria", "BEL": "Belgium", "BGR": "Bulgaria",
    "BLR": "Belarus", "CAN": "Canada", "CHE": "Switzerland", "CHL": "Chile",
    "CZE": "Czechia", "DEUTNP": "Germany (total)", "DNK": "Denmark",
    "ESP": "Spain", "EST": "Estonia", "FIN": "Finland",
    "FRATNP": "France (total)", "GBR_NP": "United Kingdom (total)",
    "GRC": "Greece", "HKG": "Hong Kong SAR", "HRV": "Croatia",
    "HUN": "Hungary", "IRL": "Ireland", "ISL": "Iceland",
    "ISR": "Israel", "ITA": "Italy", "JPN": "Japan", "KOR": "South Korea",
    "LTU": "Lithuania", "LUX": "Luxembourg", "LVA": "Latvia",
    "NLD": "Netherlands", "NOR": "Norway", "NZL_NP": "New Zealand (total)",
    "POL": "Poland", "PRT": "Portugal", "RUS": "Russia", "SVK": "Slovakia",
    "SVN": "Slovenia", "SWE": "Sweden", "TWN": "Taiwan", "UKR": "Ukraine",
    "USA": "United States",
}


def _read_hmd_table(zf, member_name):
    """Read a single life-table file from an open ZipFile. Returns DataFrame."""
    with zf.open(member_name) as f:
        # HMD STATS files have a 2-line header (title + blank), data starts on line 3.
        # The .txt files are space-separated; .csv files are comma-separated.
        raw = f.read().decode("utf-8", errors="replace")
    lines = raw.splitlines()
    # Skip leading non-data lines (the title and the blank/separator).
    # The header row contains "Year", "Age" etc.; find it.
    header_idx = next(
        (i for i, ln in enumerate(lines) if re.match(r"\s*Year\b", ln)),
        2,
    )
    body = "\n".join(lines[header_idx:])
    # HMD .txt life tables are space-separated with multiple spaces between cols
    df = pd.read_csv(io.StringIO(body), sep=r"\s+", dtype=str, engine="python")
    return df


def step_hmd_life_tables():
    _section("5. HMD life tables — process 41 country zips")
    if not HMD.exists():
        print(f"  ERROR: {HMD} not present")
        return None

    zips = sorted(HMD.glob("*.zip"))
    if not zips:
        print(f"  ERROR: no zips in {HMD}")
        return None
    print(f"  Country zips found: {len(zips)}")

    frames = []
    skipped = []
    for zp in zips:
        ccode = zp.stem
        cname = HMD_COUNTRY_NAMES.get(ccode, ccode)
        try:
            with zipfile.ZipFile(zp) as zf:
                # Each zip has STATS/{bltper,fltper,mltper}_1x1.{csv,txt}
                for sex_key, sex_label in [("bltper", "both"), ("fltper", "female"), ("mltper", "male")]:
                    # HMD STATS/.csv files contain raw stats WITHOUT a header row;
                    # only .txt has the named life-table columns. Use .txt only.
                    chosen = next(
                        (m for m in zf.namelist()
                         if f"STATS/{sex_key}_1x1.txt" in m),
                        None,
                    )
                    if not chosen:
                        continue
                    try:
                        df = _read_hmd_table(zf, chosen)
                    except Exception as e:
                        print(f"    {ccode} {sex_label}: parse error ({e})")
                        continue
                    df["country_code"] = ccode
                    df["country_name"] = cname
                    df["sex"] = sex_label
                    frames.append(df)
        except Exception as e:
            print(f"    {ccode}: zip error ({e})")
            skipped.append(ccode)

    if not frames:
        print("  ERROR: no life tables extracted")
        return None
    out = pd.concat(frames, ignore_index=True)
    # Normalize numeric columns (HMD uses '.' as missing)
    for c in ("Year", "Age", "mx", "qx", "ax", "lx", "dx", "Lx", "Tx", "ex"):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    # Standardize column names
    out.rename(columns={"Year": "year", "Age": "age"}, inplace=True)
    # Drop comment-noise rows (HMD .txt files can have stray content)
    if "year" in out.columns:
        out = out[out["year"].notna()].reset_index(drop=True)

    print(f"  Combined rows: {len(out):,}  cols: {len(out.columns)}  "
          f"countries: {out['country_code'].nunique()}")
    if skipped:
        print(f"  Skipped countries: {skipped}")
    print(f"  Year range: {int(out['year'].min())}–{int(out['year'].max())}")
    print(f"  Sample:")
    print(out.head(3).to_string(max_cols=8, max_colwidth=12, index=False))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 6. HMD quality warnings — scrape mortality.org per-country pages
# ─────────────────────────────────────────────────────────────────────────────

_WARNING_SPAN_RE = re.compile(
    r"^\s*(warning|caution|note|important|disclaimer)\s*:?\s*",
    re.I,
)


def _extract_warnings_from_country_page(html):
    """
    Return a list of warning paragraphs from a mortality.org country page.
    HMD marks warnings with <span style="color:red">Warning:</span> inside <p>.
    Falls back to class/style heuristics if that fails.
    """
    soup = BeautifulSoup(html, "html.parser")
    out = []

    # Primary pattern: <p>... <span style="color:red">Warning: </span> rest </p>
    for span in soup.find_all("span"):
        style = (span.get("style") or "").lower()
        text  = span.get_text(" ", strip=True)
        if ("color:red" in style.replace(" ", "")
                or _WARNING_SPAN_RE.match(text)):
            # The full paragraph this span lives inside
            p = span.find_parent("p") or span.find_parent("div")
            if p:
                t = p.get_text(" ", strip=True)
                if 20 < len(t) < 2000 and t not in out:
                    out.append(t)
            else:
                t = text
                if 20 < len(t) < 2000:
                    out.append(t)

    # Fallback: explicit warning/alert/note classes
    for el in soup.find_all(["div", "p", "section"]):
        cls = " ".join(el.get("class") or []).lower()
        if any(k in cls for k in ("warning", "alert", "caution", "danger",
                                    "callout")):
            t = el.get_text(" ", strip=True)
            if 20 < len(t) < 2000 and t not in out:
                out.append(t)

    return out


def step_hmd_quality_warnings():
    _section("6. HMD country quality warnings — scrape mortality.org")
    dest = HMD / "hmd_quality_notes.csv"
    index_url = "https://www.mortality.org/Data/DataAvailability"

    print(f"  GET index: {index_url}")
    try:
        resp = _http_get(index_url, timeout=60)
    except Exception as e:
        print(f"  ERROR: index fetch failed: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    # Correct HMD URL pattern: /Country/Country?cntr={CODE}
    links = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = re.search(r"/Country/Country\?cntr=([A-Z][A-Z0-9_]+)", href)
        if m:
            code = m.group(1)
            links[code] = (urljoin(index_url, href), a.get_text(strip=True))
    print(f"  Country links discovered on index: {len(links)}")

    # Ensure all the codes we care about are represented
    for code in HMD_COUNTRY_NAMES:
        if code not in links:
            links[code] = (
                f"https://www.mortality.org/Country/Country?cntr={code}",
                HMD_COUNTRY_NAMES[code],
            )

    rows = []
    for i, (code, (url, anchor_text)) in enumerate(sorted(links.items()), 1):
        cname = HMD_COUNTRY_NAMES.get(code, anchor_text)
        warning = ""
        err = ""
        for attempt in range(2):
            try:
                r = _http_get(url, timeout=45)
                break
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                if attempt == 0:
                    time.sleep(2.0)
                else:
                    r = None
        if r is None or r.status_code != 200:
            print(f"    [{i}/{len(links)}] {code:<8} fetch failed: {err}")
            rows.append({"country_code": code, "country_name": cname,
                         "warning_text": "", "has_warning": False,
                         "url": url, "error": err})
            time.sleep(0.8)
            continue

        texts = _extract_warnings_from_country_page(r.text)
        warning = " || ".join(texts)
        has_warning = bool(warning)
        rows.append({"country_code": code, "country_name": cname,
                     "warning_text": warning, "has_warning": has_warning,
                     "url": url, "error": ""})
        print(f"    [{i}/{len(links)}] {code:<8} warning={'Y' if has_warning else '-'}  "
              f"len={len(warning)}")
        time.sleep(0.8)   # be polite — mortality.org returns 500 if hit too fast

    df = pd.DataFrame(rows)
    df.to_csv(dest, index=False)
    n_warned = int(df["has_warning"].sum())
    print(f"  Rows: {len(df)}  with warning: {n_warned}")
    print(f"  Saved → {dest}")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 7. Join warnings into HMD life tables
# ─────────────────────────────────────────────────────────────────────────────

def step_hmd_join(life_tables_df, quality_df):
    _section("7. Join quality warnings into hmd_life_tables.csv")
    dest = RAW / "hmd_life_tables.csv"
    if life_tables_df is None:
        print("  ERROR: life tables df missing — skipping join")
        return
    if quality_df is None:
        print("  WARN: quality df missing — saving life tables without warning flag")
        life_tables_df["has_quality_warning"] = False
    else:
        warn_map = dict(zip(quality_df["country_code"], quality_df["has_warning"]))
        life_tables_df["has_quality_warning"] = life_tables_df["country_code"].map(warn_map).fillna(False).astype(bool)

    life_tables_df.to_csv(dest, index=False)
    print(f"  Rows: {len(life_tables_df):,}  "
          f"flagged-warning rows: {int(life_tables_df['has_quality_warning'].sum()):,}")
    print(f"  Saved → {dest}")


# ─────────────────────────────────────────────────────────────────────────────
# Driver
# ─────────────────────────────────────────────────────────────────────────────

def safe(step_name, fn, *args):
    try:
        return fn(*args)
    except Exception as e:
        print(f"\n  ! Step '{step_name}' raised: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    print("Processing new datasets — outputs to", RAW)
    safe("gwas",                step_gwas)
    safe("who",                 step_who)
    safe("un_wpp",              step_un_wpp)
    safe("nhanes_methylation",  step_nhanes_methylation)
    life_df    = safe("hmd_life_tables",   step_hmd_life_tables)
    quality_df = safe("hmd_quality_warnings", step_hmd_quality_warnings)
    safe("hmd_join", step_hmd_join, life_df, quality_df)

    # Final summary of new files
    _section("SUMMARY — new files in data/raw/datasets/")
    targets = [
        "gwas_longevity.csv", "who_life_expectancy.csv",
        "un_population_prospects.csv", "nhanes_methylation.csv",
        "hmd_life_tables.csv",
    ]
    for name in targets:
        p = RAW / name
        if p.exists():
            try:
                df = pd.read_csv(p, low_memory=False, nrows=5)
                full_n = sum(1 for _ in open(p, encoding="utf-8")) - 1
                cols = list(df.columns)[:8]
                print(f"  {name:<32}  {full_n:>10,} rows   cols: {cols}")
            except Exception as e:
                print(f"  {name:<32}  (size {p.stat().st_size/1e6:.1f} MB; read error: {e})")
        else:
            print(f"  {name:<32}  NOT WRITTEN")
    qp = HMD / "hmd_quality_notes.csv"
    if qp.exists():
        df = pd.read_csv(qp)
        print(f"  hmd/hmd_quality_notes.csv         {len(df):>10,} rows   "
              f"with warning: {int(df['has_warning'].sum())}")


if __name__ == "__main__":
    main()
