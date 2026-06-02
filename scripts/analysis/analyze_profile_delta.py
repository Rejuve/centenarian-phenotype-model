"""Measure the NEW trait signal LongeviQuest profile blurbs add beyond the news corpus.

Run AFTER scrape+merge (profile rows present in news_articles.csv with
source_class='database_profile'). For the individuals who appear in BOTH the news
corpus and as a LongeviQuest profile, compare the trait categories evidenced by
their news coverage vs. their profile blurb, and report what the blurb adds.

Trait categories are the 5 Tier-1 lifestyle families:
  physical_activity, diet, social, purpose_psychology, sleep
extracted two ways (same as extract_layer1_traits.py): the boolean trait_* columns
and keyword matches over the text.
"""
import os
import sys
import re
import pandas as pd

# extract_layer1_traits lives in scripts/pipeline/ — add it to the import path.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pipeline"))
import extract_layer1_traits as E

NEWS = "data/raw/news_articles.csv"
VERIFIED = "data/processed/_verified_in_news.csv"

COL_CAT = {
    "trait_physical_activity": "physical_activity",
    "trait_diet": "diet",
    "trait_social": "social",
    "trait_purpose_psychology": "purpose_psychology",
    "trait_sleep": "sleep",
}
CATS = list(dict.fromkeys(COL_CAT.values()))


def row_cats(row):
    """Trait categories evidenced by one article row (boolean cols + keyword mining)."""
    cats = set()
    for col, cat in COL_CAT.items():
        v = str(row.get(col)).strip().upper()
        if v in ("TRUE", "1", "1.0"):
            cats.add(cat)
    txt = row.get("full_text") if isinstance(row.get("full_text"), str) else ""
    if txt:
        for rx, _label, cat in E.KEYWORD_TRAITS:
            if cat in CATS and cat not in cats and rx.search(txt):
                cats.add(cat)
    return cats


def main():
    news = pd.read_csv(NEWS, low_memory=False)
    vf = pd.read_csv(VERIFIED)
    overlap = list(vf["canonical_name"])

    is_prof = news["source_class"].astype(str) == "database_profile"
    profiles = news[is_prof]
    newsrows = news[~is_prof]

    # index profile rows by cleaned subject name
    prof_by = {}
    for _, r in profiles.iterrows():
        prof_by[E.clean_name(r.get("subject_name"))] = r

    per = []
    for name in overlap:
        cl = E.clean_name(name)
        # news rows for this person: subject_name fuzzy-match or full name in text
        ncats = set()
        n_news = 0
        for _, r in newsrows.iterrows():
            sc = E.clean_name(r.get("subject_name"))
            txt = E.strip_accents(r.get("full_text") if isinstance(r.get("full_text"), str) else "").lower()
            hit = (sc and E.is_personlike(sc) and E.names_match(sc, cl)) or E.full_name_in_text(cl, txt)
            if hit:
                ncats |= row_cats(r)
                n_news += 1
        pcats = row_cats(prof_by[cl]) if cl in prof_by else set()
        added = pcats - ncats
        per.append(dict(name=name, n_news=n_news, has_profile=cl in prof_by,
                        news_cats="|".join(sorted(ncats)) or "-",
                        profile_cats="|".join(sorted(pcats)) or "-",
                        added="|".join(sorted(added)) or "-",
                        n_added=len(added)))

    d = pd.DataFrame(per)
    have = d[d.has_profile]
    print(f"Overlap individuals (news + profile): {len(have)} of {len(d)}")
    print(f"  gained >=1 new trait category from the blurb: {(have.n_added>0).sum()} "
          f"({100*(have.n_added>0).mean():.0f}%)")
    print(f"  avg new categories per person: {have.n_added.mean():.2f}")
    print("\n  new-signal by category (people who gained it from the blurb):")
    for c in CATS:
        gained = have[have.added.str.contains(c, regex=False)]
        print(f"    {c:20} +{len(gained)}")
    print("\n  per-person (top gainers):")
    cols = ["name", "n_news", "news_cats", "profile_cats", "added"]
    print(have.sort_values("n_added", ascending=False)[cols].head(20).to_string(index=False))


if __name__ == "__main__":
    main()
