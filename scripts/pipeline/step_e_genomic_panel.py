"""
Step E (genomic deepening) — curate an expanded longevity variant panel from our own data.

Sources (no new scraping):
  - data/raw/datasets/gwas_longevity.csv   (GWAS Catalog longevity associations, 1,863 rows)
  - data/raw/datasets/cent_WGS.txt         (centenarian 105+ vs control allele frequencies)

Produces data/processed/genomic_panel_curated.csv: genome-wide-significant longevity-trait
variants with mapped gene, risk allele, effect size, and — where the position matches our
centenarian WGS — the case-vs-control allele frequencies as independent corroboration.

Nothing is invented: effect direction is read from the catalog trait + OR/BETA; WGS columns are
only filled where CHR:POS matches. Build mismatch (if any) simply yields no WGS match and is reported.
"""
import csv
import os

csv.field_size_limit(2 ** 27)
GWAS = "data/raw/datasets/gwas_longevity.csv"
WGS = "data/raw/datasets/cent_WGS.txt"
OUT = "data/processed/genomic_panel_curated.csv"
PSIG = 5e-8

# longevity-relevant traits only (exclude COVID mortality, emphysema imaging, etc.)
def is_longevity(trait):
    t = (trait or "").lower()
    keys = ("longevity", "lifespan", "extreme age", "attained age", "age at death",
            "aging", "ageing", "centenarian", "long-lived", "exceptional long")
    bad = ("covid", "emphysema", "amyloid deposition")
    return any(k in t for k in keys) and not any(b in t for b in bad)


def parse_float(s):
    try:
        return float(str(s).replace(" ", "").replace("E", "e"))
    except Exception:
        return None


def effect_direction(trait, orbeta):
    """Best-effort, conservative. Only label when unambiguous; else 'reported'."""
    t = (trait or "").lower()
    b = parse_float(orbeta)
    if b is None:
        return "reported"
    longer = any(k in t for k in ("longevity", "lifespan", "long-lived", "extreme age",
                                  "attained age", "centenarian", "exceptional long"))
    if "age at death" in t or "parental" in t:
        # beta on age-at-death: positive => longer life
        return "longevity_associated" if b > 0 else ("longevity_adverse" if b < 0 else "reported")
    if longer:
        # OR on a longevity phenotype: >1 favours longevity
        return "longevity_associated" if b > 1 else ("longevity_adverse" if 0 < b < 1 else "reported")
    return "reported"


def curate_gwas():
    best = {}  # snp -> record (keep most significant)
    for r in csv.DictReader(open(GWAS, encoding="utf-8", errors="replace")):
        trait = r["DISEASE/TRAIT"]
        if not is_longevity(trait):
            continue
        p = parse_float(r["P-VALUE"])
        if p is None or p > PSIG:
            continue
        snp = (r["SNPS"] or "").split(";")[0].split(",")[0].strip()
        if not snp.startswith("rs"):
            continue
        chrid = (r["CHR_ID"] or "").split(";")[0].strip()
        pos = (r["CHR_POS"] or "").split(";")[0].strip()
        rec = dict(
            snp=snp, gene=(r["MAPPED_GENE"] or "").split(";")[0].strip() or r["REPORTED GENE(S)"],
            trait=trait, risk_allele=(r["STRONGEST SNP-RISK ALLELE"] or "").split("-")[-1].strip(),
            p_value=p, or_beta=(r["OR or BETA"] or "").strip(),
            effect_direction=effect_direction(trait, r["OR or BETA"]),
            chr=chrid, pos=pos, first_author=r["FIRST AUTHOR"], pubmedid=r["PUBMEDID"],
        )
        if snp not in best or p < best[snp]["p_value"]:
            best[snp] = rec
    return best


def corroborate_wgs(records):
    """Stream the 5.5M-row WGS once; fill case/control freq where CHR:POS matches."""
    want = {}
    for rec in records.values():
        if rec["chr"] and rec["pos"]:
            want.setdefault((rec["chr"], rec["pos"]), []).append(rec)
    if not want:
        return 0
    matched = 0
    with open(WGS, encoding="utf-8", errors="replace") as f:
        f.readline()  # header CHR BP A1 F_105 F_CTRL
        for line in f:
            p = line.split()
            if len(p) < 5:
                continue
            key = (p[0], p[1])
            if key in want:
                for rec in want[key]:
                    rec["wgs_a1"] = p[2]
                    rec["wgs_cent_freq"] = p[3]
                    rec["wgs_ctrl_freq"] = p[4]
                    fc, fk = parse_float(p[3]), parse_float(p[4])
                    rec["wgs_freq_diff"] = round(fc - fk, 4) if (fc is not None and fk is not None) else ""
                matched += 1
    return matched


def main():
    records = curate_gwas()
    matched = corroborate_wgs(records)
    rows = sorted(records.values(), key=lambda r: r["p_value"])
    cols = ["snp", "gene", "trait", "effect_direction", "risk_allele", "or_beta", "p_value",
            "chr", "pos", "wgs_a1", "wgs_cent_freq", "wgs_ctrl_freq", "wgs_freq_diff",
            "first_author", "pubmedid"]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})

    genes = sorted({r["gene"] for r in rows if r["gene"]})
    wgs_hits = [r for r in rows if r.get("wgs_freq_diff") not in (None, "")]
    print(f"genome-wide-significant longevity variants curated: {len(rows)}")
    print(f"distinct mapped genes: {len(genes)}")
    print(f"variants position-matched in centenarian WGS: {matched}")
    print(f"  -> with usable case/control freq diff: {len(wgs_hits)}")
    print("\ntop 20 by significance:")
    for r in rows[:20]:
        wd = r.get("wgs_freq_diff", "")
        wd = f" | WGS cent-ctrl diff={wd}" if wd != "" else ""
        print(f"  {r['snp']:13} {str(r['gene'])[:16]:16} {r['effect_direction']:20} p={r['p_value']:.0e}{wd}")
    print(f"\nwritten -> {OUT}")


if __name__ == "__main__":
    main()
