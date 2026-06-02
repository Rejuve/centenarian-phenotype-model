"""
Layer 1 quiz feature extraction from named centenarians.

Finds which lifestyle traits appear most consistently across named centenarians
in the news corpus, to seed the Tier-1 (8-question) quiz/ad funnel.

Pipeline:
  1. Build master centenarian name list (supercentenarians.csv + wikipedia list), deduped.
  2. Filter news_articles.csv to is_centenarian_profile == True.
  3. Identify the named subject of each profile (subject_name + full_text scan),
     fuzzy-matching against the master list to flag VERIFIED centenarians.
  4. Extract traits two ways: (a) the five boolean trait_* columns,
     (b) keyword extraction in a 40-word window around the subject mention.
  5. Record (centenarian_name, trait, trait_category, source_name, sample_quote).
  6. Aggregate distinct centenarians per trait; keep individual_count >= 3.
  7. Write data/processed/layer1_trait_frequency.csv, sorted by individual_count desc.
  8. Print: total output rows, top 20 traits, top 10 most-covered centenarians.

Run:  python extract_layer1_traits.py
"""

import os
import re
import sys
import unicodedata
from collections import defaultdict, Counter
from difflib import SequenceMatcher

import pandas as pd

NEWS = "data/raw/news_articles.csv"
SUPER = "data/processed/supercentenarians.csv"
WIKI = "data/raw/datasets/wikipedia_supercentenarians.csv"
TIDY = "data/raw/datasets/tidytuesday_centenarians.csv"
LONGE = "data/raw/datasets/longeviquest_atlas.csv"
OUT = "data/processed/layer1_trait_frequency.csv"

# Longevity tiers by age.
TIER_SUPER = "supercentenarian"   # 110+
TIER_CENT = "centenarian"         # 100-109
TIER_NONA = "nonagenarian"        # 90-99
TIER_ORDER = [TIER_SUPER, TIER_CENT, TIER_NONA]   # richest-signal first


def age_to_tier(age):
    """Map a numeric age to a longevity tier (or None if <90 / unknown)."""
    try:
        a = float(age)
    except (TypeError, ValueError):
        return None
    if a >= 110:
        return TIER_SUPER
    if a >= 100:
        return TIER_CENT
    if a >= 90:
        return TIER_NONA
    return None


def parse_subject_age(row):
    """Best estimate of the *subject's* age from a news row.

    Preference: subject_age (the NER-extracted subject age) -> max_age
    (highest age mentioned, a good proxy in a single-subject profile) ->
    largest value parsed from the ages_mentioned list.
    """
    for col in ("subject_age", "max_age"):
        v = pd.to_numeric(row.get(col), errors="coerce")
        if pd.notna(v) and v >= 90:
            return float(v)
    am = row.get("ages_mentioned")
    if isinstance(am, str) and am.strip():
        nums = [int(x) for x in re.findall(r"\d+", am)]
        nums = [n for n in nums if 90 <= n <= 130]
        if nums:
            return float(max(nums))
    return None

# ---------------------------------------------------------------------------
# Name normalization / matching helpers
# ---------------------------------------------------------------------------

# Common given-name nicknames -> canonical, to help fuzzy matching.
NICKNAMES = {
    "bill": "william", "billy": "william", "will": "william", "willie": "william",
    "bob": "robert", "bobby": "robert", "rob": "robert",
    "dick": "richard", "rick": "richard", "richie": "richard",
    "jim": "james", "jimmy": "james", "jamie": "james",
    "joe": "joseph", "joey": "joseph",
    "jack": "john", "johnny": "john", "jon": "john",
    "tom": "thomas", "tommy": "thomas",
    "tony": "anthony",
    "ed": "edward", "eddie": "edward", "ted": "edward", "teddy": "edward",
    "harry": "henry", "hank": "henry",
    "fred": "frederick", "freddie": "frederick",
    "charlie": "charles", "chuck": "charles",
    "mike": "michael", "mickey": "michael",
    "dave": "david",
    "steve": "stephen", "stevie": "stephen",
    "sam": "samuel",
    "ben": "benjamin",
    "dan": "daniel", "danny": "daniel",
    "matt": "matthew",
    "nick": "nicholas",
    "pat": "patrick",
    "ron": "ronald", "ronnie": "ronald",
    "don": "donald", "donnie": "donald",
    "walt": "walter",
    "gus": "augustus",
    "peggy": "margaret", "meg": "margaret", "maggie": "margaret", "marge": "margaret",
    "betty": "elizabeth", "beth": "elizabeth", "liz": "elizabeth", "lizzie": "elizabeth",
    "bess": "elizabeth", "eliza": "elizabeth",
    "kate": "katherine", "katie": "katherine", "kathy": "katherine", "cathy": "katherine",
    "sue": "susan", "susie": "susan",
    "nan": "nancy", "nancy": "ann",
    "dot": "dorothy", "dottie": "dorothy",
    "jenny": "jennifer", "jen": "jennifer",
    "molly": "mary", "polly": "mary", "may": "mary", "mae": "mary",
    "sally": "sarah", "sadie": "sarah",
    "fanny": "frances", "fran": "frances",
    "gerry": "geraldine", "jerry": "gerald",
    "millie": "mildred",
    "winnie": "winifred",
    "minnie": "wilhelmina",
}

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "phd", "md", "dr", "mr", "mrs", "ms", "sir", "dame"}

# Tokens that betray an NER false-positive masquerading as a person name
# (function words, headline fragments, generic nouns seen in subject_name noise).
NAME_STOPWORDS = {
    "the", "a", "an", "at", "to", "for", "of", "in", "on", "by", "is", "are", "was",
    "this", "that", "these", "those", "where", "when", "how", "why", "who", "what",
    "away", "here", "there", "from", "with", "and", "or", "but", "as", "into",
    "live", "lives", "living", "diet", "birthday", "turning", "celebrates", "celebrate",
    "extraordinary", "amazing", "distinguished", "visitors", "editors", "editor",
    "cafe", "county", "coffee", "nation", "uncovers", "airman", "court", "least",
    "centenarian", "centenarians", "supercentenarian", "oldest", "secret", "secrets",
    "happy", "world", "news", "report", "story", "exclusive", "obituary", "tribute",
    "woman", "man", "lady", "gentleman", "people", "person", "years", "year", "old",
    "yorker", "today", "yesterday", "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
}


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def clean_name(raw: str) -> str:
    """Lowercase, strip accents/footnotes/punctuation; drop honorifics & suffixes."""
    if not isinstance(raw, str):
        return ""
    s = strip_accents(raw)
    s = re.sub(r"\[[^\]]*\]", " ", s)          # remove [9] style footnotes
    s = re.sub(r"\([^)]*\)", " ", s)            # remove parentheticals
    s = s.lower()
    s = re.sub(r"[^a-z\s'-]", " ", s)           # keep letters, apostrophe, hyphen
    s = re.sub(r"[-']", " ", s)
    toks = [t for t in s.split() if t and t not in SUFFIXES]
    return " ".join(toks)


def name_tokens(cleaned: str):
    toks = cleaned.split()
    return [NICKNAMES.get(t, t) for t in toks]


def is_personlike(cleaned: str) -> bool:
    """Heuristic: a real person name has 2-4 alphabetic tokens, each >=2 chars,
    none of which is a function word / headline-fragment token."""
    toks = cleaned.split()
    if not (2 <= len(toks) <= 4):
        return False
    if any(len(t) < 2 for t in toks):
        return False
    if any(t in NAME_STOPWORDS for t in toks):
        return False
    return True


def full_name_in_text(cleaned: str, text_clean_lower: str) -> bool:
    """True if the subject's first and last name appear together in the body."""
    toks = cleaned.split()
    if len(toks) < 2:
        return False
    pat = r"\b" + re.escape(toks[0]) + r"\b.{0,15}\b" + re.escape(toks[-1]) + r"\b"
    return re.search(pat, text_clean_lower) is not None


def names_match(a_clean: str, b_clean: str) -> bool:
    """Fuzzy person-name match with nickname + token-subset + ratio logic."""
    if not a_clean or not b_clean:
        return False
    if a_clean == b_clean:
        return True
    a = name_tokens(a_clean)
    b = name_tokens(b_clean)
    sa, sb = set(a), set(b)
    # one name's tokens are a subset of the other (handles middle names)
    if sa and sb and (sa <= sb or sb <= sa):
        return True
    # same last name + same first initial (and first names compatible)
    if a and b and a[-1] == b[-1]:
        if a[0] == b[0] or a[0][0] == b[0][0]:
            return True
    # overall string similarity
    if SequenceMatcher(None, " ".join(a), " ".join(b)).ratio() >= 0.90:
        return True
    return False


# ---------------------------------------------------------------------------
# Keyword lexicon for 40-word-window extraction (specific traits)
# Each entry: regex -> (specific_trait_label, trait_category)
# ---------------------------------------------------------------------------

PA = "physical_activity"
DIET = "diet"
SOC = "social"
PURP = "purpose_psychology"
SLEEP = "sleep"
SUB = "substance_use"
WORK = "work_activity"

KEYWORD_TRAITS = [
    # --- physical activity ---
    (r"\byoga\b", "yoga", PA),
    (r"\bpilates\b", "pilates", PA),
    (r"\b(walk|walking|walks)\b", "walking daily", PA),
    (r"\b(run|running|runner|marathon|jog|jogging)\b", "running/marathon", PA),
    (r"\bswim(ming|s)?\b", "swimming", PA),
    (r"\b(cycl|bik(e|ing)|bicycle)\w*\b", "cycling", PA),
    (r"\b(dance|dancing|dancer)\b", "dancing", PA),
    (r"\b(gym|weight\s?lift|exercise|exercising|workout|work out)\w*\b", "regular exercise", PA),
    (r"\b(garden|gardening)\b", "gardening", PA),
    (r"\b(tai\s?chi|qigong|qi gong)\b", "tai chi", PA),
    (r"\b(spin class|spinning class|spin classes)\b", "spin classes", PA),
    (r"\b(stretch|stretching)\b", "stretching", PA),
    (r"\b(golf|golfing)\b", "golf", PA),
    (r"\b(active|activity|stay active|keep active|keeping active)\b", "staying active", PA),
    # --- diet ---
    (r"\bvegetarian\b", "vegetarian diet", DIET),
    (r"\bvegan\b", "vegan diet", DIET),
    (r"\b(vegetable|veggies|greens)\b", "eats vegetables", DIET),
    (r"\bfruit\b", "eats fruit", DIET),
    (r"\bfish\b", "eats fish", DIET),
    (r"\boatmeal|porridge|oats\b", "oatmeal/porridge", DIET),
    (r"\beggs?\b", "eats eggs", DIET),
    (r"\b(olive oil)\b", "olive oil", DIET),
    (r"\bbeans?\b|\blegumes?\b", "beans/legumes", DIET),
    (r"\b(rice)\b", "rice staple", DIET),
    (r"\b(home\s?cook|home-cooked|cook(s|ing)? (her|his|their) own)\b", "home cooking", DIET),
    (r"\b(moderation|small portion|eat less|never overeat|portion)\b", "eating in moderation", DIET),
    (r"\b(no junk|avoid(s|ed)? processed|no processed|whole food)\b", "avoids processed food", DIET),
    (r"\b(chocolate)\b", "chocolate", DIET),
    (r"\b(coffee)\b", "coffee", DIET),
    (r"\b(tea)\b", "tea", DIET),
    (r"\b(honey)\b", "honey", DIET),
    (r"\b(bacon)\b", "bacon", DIET),
    (r"\b(sugar|sweets|candy)\b", "sweets/sugar", DIET),
    # --- substance use ---
    (r"\b(no alcohol|never drank|never drink|teetotal|don't drink|doesn't drink|abstain)\w*\b", "no alcohol", SUB),
    (r"\b(wine|whisk(e)?y|beer|gin|brandy|sherry|rum|vodka|drink (a|the) )\w*\b", "drinks alcohol (moderate)", SUB),
    (r"\b(never smoked|no smoking|don't smoke|doesn't smoke|non-smoker|nonsmoker|never smoke)\b", "never smoked", SUB),
    (r"\b(smok(e|es|ed|ing)|cigarette|cigar|tobacco|pipe)\b", "smoked", SUB),
    # --- social ---
    (r"\b(married)\b", "married (long)", SOC),
    (r"\b(family|families)\b", "close family", SOC),
    (r"\b(grandchild|grandchildren|great-grand|grandkids)\b", "grandchildren", SOC),
    (r"\b(friends?|friendship)\b", "friendships", SOC),
    (r"\b(community|neighbou?rs?)\b", "community ties", SOC),
    (r"\b(church|temple|mosque|synagogue|congregation)\b", "religious community", SOC),
    (r"\b(social|sociali[sz]|gathering|visit|company)\w*\b", "socializing", SOC),
    (r"\b(volunteer|volunteering|charity)\b", "volunteering", SOC),
    # --- purpose / psychology ---
    (r"\b(faith|god|religion|religious|pray|prayer|spiritual|belief)\w*\b", "faith/religion", PURP),
    (r"\b(positive|optimis|happy|happiness|cheerful|joy)\w*\b", "positive outlook", PURP),
    (r"\b(purpose|meaning|reason to)\w*\b", "sense of purpose", PURP),
    (r"\b(read|reads|reading|book)\w*\b", "reads daily", PURP),
    (r"\b(no stress|stress-free|don't worry|doesn't worry|never worry|no worries|stay calm|keep calm|calm)\b", "low stress / calm", PURP),
    (r"\b(grateful|gratitude|thankful)\b", "gratitude", PURP),
    (r"\b(curious|curiosity|learning|learn new)\b", "curiosity/learning", PURP),
    (r"\b(laugh|laughter|sense of humou?r|humou?r)\b", "humor/laughter", PURP),
    (r"\b(music|sing|singing|piano|choir|instrument)\b", "music", PURP),
    (r"\b(paint|painting|art|knit|knitting|craft|sew|sewing)\w*\b", "creative hobbies", PURP),
    (r"\b(puzzle|crossword|sudoku|cards|chess|bingo)\b", "puzzles/games", PURP),
    # --- work / activity ---
    (r"\b(still work|still working|never retired|keep working|kept working|won't retire|works every)\b", "still working", WORK),
    (r"\b(busy|keep busy|stay busy|keeping busy)\b", "keeping busy", WORK),
    (r"\b(independent|live(s)? alone|lives independently|on her own|on his own)\b", "lives independently", WORK),
    # --- sleep ---
    (r"\b(sleep|sleeps|slept)\b", "good sleep", SLEEP),
    (r"\b(nap|naps|napping|siesta)\b", "naps", SLEEP),
    (r"\b(early (to bed|riser|rise)|wake(s)? up early|up at dawn|go to bed early)\b", "early to bed/rise", SLEEP),
    (r"\b(eight hours|8 hours|full night|good night's)\b", "8 hours sleep", SLEEP),
]
KEYWORD_TRAITS = [(re.compile(p, re.I), label, cat) for p, label, cat in KEYWORD_TRAITS]

# Boolean trait_* columns -> (trait label, category)
BOOLEAN_TRAITS = {
    "trait_physical_activity": ("[tagged] physically active", PA),
    "trait_diet": ("[tagged] healthy/notable diet", DIET),
    "trait_social": ("[tagged] socially connected", SOC),
    "trait_purpose_psychology": ("[tagged] sense of purpose / positive psychology", PURP),
    "trait_sleep": ("[tagged] notable sleep habits", SLEEP),
}


# ---------------------------------------------------------------------------
# Build master centenarian list
# ---------------------------------------------------------------------------

def build_master():
    """Return cleaned_name -> (display_name, age_years).

    Sources are all verified 110+ oldest-people registries, so every master
    entry tiers as supercentenarian; the age is kept so the tier is computed
    the same way as for news-derived subjects.
    """
    sc = pd.read_csv(SUPER, low_memory=False)
    wk = pd.read_csv(WIKI, low_memory=False)
    tt = pd.read_csv(TIDY, low_memory=False)
    records = []
    for _, r in sc.iterrows():
        records.append((str(r["name"]), r.get("age_years")))
    for _, r in wk.iterrows():
        records.append((str(r["Name"]), r.get("Age")))
    for _, r in tt.iterrows():
        records.append((str(r["name"]), r.get("age")))
    # LongeviQuest atlas: verified, complete-gender 110+ profiles (optional file)
    if os.path.exists(LONGE):
        lq = pd.read_csv(LONGE, low_memory=False)
        for _, r in lq.iterrows():
            records.append((str(r["name"]), r.get("age_years")))

    master = {}  # cleaned -> (display, age)
    for raw, age in records:
        disp = re.sub(r"\[[^\]]*\]", "", str(raw)).strip()
        cl = clean_name(raw)
        if not cl or not is_personlike(cl):
            continue
        age_v = pd.to_numeric(age, errors="coerce")
        if cl not in master:
            master[cl] = (disp, float(age_v) if pd.notna(age_v) else None)
        elif master[cl][1] is None and pd.notna(age_v):
            master[cl] = (master[cl][0], float(age_v))
    return master


# ---------------------------------------------------------------------------
# Subject identification
# ---------------------------------------------------------------------------

def find_master_in_text(text_clean_lower: str, master_display: dict, master_clean_list):
    """Return the first master display name whose full name appears in the text."""
    for cl, disp in zip(master_clean_list, [master_display[c] for c in master_clean_list]):
        toks = cl.split()
        if len(toks) < 2:
            continue
        # require first and last token both present as words, in order, close together
        pat = r"\b" + re.escape(toks[0]) + r"\b.{0,15}\b" + re.escape(toks[-1]) + r"\b"
        if re.search(pat, text_clean_lower):
            return disp
    return None


def mention_windows(full_text: str, subject_display: str, window=40):
    """Return a list of ~40-word windows, one around each mention of the subject.

    Anchors on the subject's surname (falling back to the first name). Adjacent /
    overlapping windows are merged so each chunk of text is only emitted once.
    If the subject is never found by name, returns the opening 40 words as a
    single window (the profile is about them even if NER named them elsewhere).
    """
    if not isinstance(full_text, str) or not full_text.strip():
        return []
    words = full_text.split()
    low = [strip_accents(w).lower().strip(".,;:!?'\"()") for w in words]
    cl = clean_name(subject_display)
    surname = cl.split()[-1] if cl else ""
    first = cl.split()[0] if cl else ""

    idxs = [i for i, w in enumerate(low) if surname and len(surname) > 2 and surname in w]
    if not idxs:
        idxs = [i for i, w in enumerate(low) if first and len(first) > 2 and first in w]
    if not idxs:
        idxs = [0]

    spans = []
    for i in idxs:
        start = max(0, i - window // 2)
        end = min(len(words), i + window // 2)
        if spans and start <= spans[-1][1]:        # merge overlapping
            spans[-1] = (spans[-1][0], max(spans[-1][1], end))
        else:
            spans.append((start, end))
    return [" ".join(words[s:e]).strip() for s, e in spans]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    master = build_master()
    master_display = {cl: v[0] for cl, v in master.items()}      # cleaned -> display
    master_age = {cl: v[1] for cl, v in master.items()}          # cleaned -> age
    master_clean_list = list(master_display.keys())
    src_note = f"{SUPER} + {WIKI} + {TIDY}"
    if os.path.exists(LONGE):
        src_note += f" + {LONGE}"
    print(f"[1] Master centenarian list: {len(master_display)} unique verified names "
          f"(from {src_note}, deduped). All tier as supercentenarian (110+).")

    news = pd.read_csv(NEWS, low_memory=False)
    is_profile = news["is_centenarian_profile"].astype(str).str.upper().isin(["TRUE", "1", "1.0"])
    print(f"[2] Centenarian-profile articles (core pool, 100+): {int(is_profile.sum())} of {len(news)} rows. "
          f"Non-profile rows are scanned too, but only admitted as the nonagenarian (90-99) supplement.")

    # Pre-clean master token sets for fuzzy match
    master_items = [(cl, master_display[cl]) for cl in master_clean_list]
    # display -> master cleaned key (to look up verified ages)
    disp_to_clean = {v: k for k, v in master_display.items()}

    # Per-article subject resolution
    records = []           # one row per (article, trait)
    article_subject = {}   # row index -> (canonical_name, verified_bool)
    indiv_age = {}         # canonical_name -> best (max) age seen
    n_verified = 0
    n_named = 0
    n_nona_supp = 0        # nonagenarian rows pulled in from non-profile articles

    for idx, row in news.iterrows():
        profile_flag = bool(is_profile.iloc[idx])
        subj_raw = row.get("subject_name")
        full_text = row.get("full_text") if isinstance(row.get("full_text"), str) else ""
        text_clean = strip_accents(full_text).lower()

        subj_clean = clean_name(subj_raw)
        canonical = None
        verified = False

        # Verified-match paths (a, b) only matter for the core (profile) pool:
        # a master match is always a supercentenarian, which the inclusion gate
        # excludes from non-profile rows anyway. Skipping them there is a big
        # speedup with no effect on results -- only path (c) can admit a
        # nonagenarian supplement.
        if profile_flag:
            # (a) subject_name fuzzy-matches a master name
            if subj_clean and is_personlike(subj_clean):
                for mcl, mdisp in master_items:
                    if names_match(subj_clean, mcl):
                        canonical = mdisp
                        verified = True
                        break

            # (b) no subject match -> scan full_text for any master name
            if canonical is None and full_text:
                hit = find_master_in_text(text_clean, master_display, master_clean_list)
                if hit:
                    canonical = hit
                    verified = True

        # (c) fall back to a person-like subject_name named (first+last) in the body.
        #     Requiring both name tokens in proximity guards against NER noise.
        if canonical is None and subj_clean and is_personlike(subj_clean):
            if full_name_in_text(subj_clean, text_clean):
                canonical = re.sub(r"\[[^\]]*\]", "", str(subj_raw)).strip()
                verified = False

        if canonical is None:
            continue  # no identifiable named subject

        # ---- determine the subject's age for tiering ----
        # Verified subjects use their authoritative master-registry age (110+);
        # everyone else is tiered from the news row's age signals.
        if verified:
            age = master_age.get(disp_to_clean.get(canonical))
            if age is None:
                age = parse_subject_age(row)
        else:
            age = parse_subject_age(row)
        row_tier = age_to_tier(age)

        # Inclusion gate: centenarian-profile rows form the core pool (any tier,
        # incl. unknown age). Non-profile rows are admitted ONLY when the subject
        # resolves to a nonagenarian (90-99) -- the labeled-separately supplement.
        if not profile_flag and row_tier != TIER_NONA:
            continue
        if not profile_flag:
            n_nona_supp += 1

        n_named += 1
        if verified:
            n_verified += 1
        article_subject[idx] = (canonical, verified)
        if age is not None:
            indiv_age[canonical] = max(indiv_age.get(canonical, 0), age)

        source = row.get("source_name") if isinstance(row.get("source_name"), str) else "unknown"
        windows = mention_windows(full_text, canonical, window=40)
        rep_quote = max(windows, key=len) if windows else ""

        # ---- (4a) boolean trait columns ----
        for col, (label, cat) in BOOLEAN_TRAITS.items():
            val = str(row.get(col)).strip().upper()
            if val in ("TRUE", "1", "1.0"):
                records.append((canonical, verified, label, cat, source, rep_quote, "boolean"))

        # ---- (4b) keyword extraction across all 40-word mention windows ----
        seen_labels = set()
        for rx, label, cat in KEYWORD_TRAITS:
            if label in seen_labels:
                continue
            for w in windows:
                m = rx.search(w)
                if m:
                    seen_labels.add(label)
                    records.append((canonical, verified, label, cat, source, w, "keyword"))
                    break

    print(f"[3] Articles with an identifiable named subject: {n_named} "
          f"({n_verified} matched to the verified master list; "
          f"{n_nona_supp} nonagenarian rows pulled from non-profile articles).")

    rec = pd.DataFrame(records, columns=[
        "centenarian_name", "verified", "trait", "trait_category",
        "source_name", "sample_quote", "method"])

    # ---- assign each distinct individual a single longevity tier ----
    indiv_tier = {name: age_to_tier(age) for name, age in indiv_age.items()}
    tier_counts_total = Counter(t for t in indiv_tier.values() if t)
    n_untiered = sum(1 for v in article_subject.values() if indiv_tier.get(v[0]) is None)
    print(f"[4] Longevity tiers across {len(indiv_tier)} distinct named subjects: "
          + ", ".join(f"{t}={tier_counts_total.get(t,0)}" for t in TIER_ORDER)
          + f", unknown-age={sum(1 for v in indiv_tier.values() if v is None)}.")

    def tier_flag(ns, nc, nn):
        present = [t for t, n in zip(TIER_ORDER, (ns, nc, nn)) if n > 0]
        total = ns + nc + nn
        if total == 0:
            return "untiered", "untiered"
        counts = dict(zip(TIER_ORDER, (ns, nc, nn)))
        primary = max(TIER_ORDER, key=lambda t: (counts[t], -TIER_ORDER.index(t)))
        if len(present) == 1:
            conc = "single_tier"
        elif counts[primary] / total >= 0.60:
            conc = "concentrated"
        else:
            conc = "spread"
        return primary, conc

    # ---- (6) aggregate: distinct centenarians per trait, tiered ----
    agg_rows = []
    for trait, g in rec.groupby("trait"):
        individuals = sorted(g["centenarian_name"].unique())
        individual_count = len(individuals)
        if individual_count < 3:
            continue
        cat = g["trait_category"].mode().iloc[0]
        article_mention_count = len(g)
        # per-tier DISTINCT individual counts
        tc = Counter(indiv_tier.get(n) for n in individuals)
        n_super, n_cent, n_nona = tc.get(TIER_SUPER, 0), tc.get(TIER_CENT, 0), tc.get(TIER_NONA, 0)
        core_count = n_super + n_cent                       # lead with cent + super
        primary, conc = tier_flag(n_super, n_cent, n_nona)
        # lead examples with core-tier (super/cent) individuals first
        core_first = sorted(individuals, key=lambda n: (indiv_tier.get(n) == TIER_NONA, n))
        examples = "; ".join(core_first[:8])
        quotes = [q for q in g["sample_quote"].tolist() if isinstance(q, str) and q.strip()]
        sample_quote = max(quotes, key=len) if quotes else ""
        method = "boolean" if g["method"].iloc[0] == "boolean" and g["method"].nunique() == 1 else (
            "keyword" if (g["method"] == "keyword").all() else "mixed")
        agg_rows.append({
            "trait": trait,
            "individual_count": individual_count,
            "core_count": core_count,
            "longevity_tier": primary,
            "tier_concentration": conc,
            "n_supercentenarian": n_super,
            "n_centenarian": n_cent,
            "n_nonagenarian": n_nona,
            "tier_breakdown": f"super:{n_super}|cent:{n_cent}|nona:{n_nona}",
            "centenarian_examples": examples,
            "trait_category": cat,
            "article_mention_count": article_mention_count,
            "sample_quote": sample_quote,
            "extraction_method": method,
        })

    # lead with centenarian + supercentenarian strength (core_count), then total
    out = pd.DataFrame(agg_rows).sort_values(
        ["core_count", "individual_count", "article_mention_count"],
        ascending=False).reset_index(drop=True)
    out.to_csv(OUT, index=False, encoding="utf-8")

    # ---- (8) report ----
    print()
    print(f"[7] Wrote {OUT}")
    print(f"    Total output rows (traits with individual_count >= 3): {len(out)}")
    print()
    print("=== TOP 20 TRAITS (sorted by core_count = supercentenarian + centenarian) ===")
    cols = ["trait", "individual_count", "core_count", "longevity_tier",
            "tier_concentration", "tier_breakdown", "trait_category"]
    with pd.option_context("display.max_rows", None, "display.width", 200,
                           "display.max_colwidth", 42):
        print(out[cols].head(20).to_string(index=False))

    print()
    print("=== TOP 10 MOST-COVERED CENTENARIANS (by article count) ===")
    art = pd.DataFrame([
        {"centenarian_name": v[0], "verified": v[1]} for v in article_subject.values()])
    top = art.groupby("centenarian_name").agg(
        article_count=("centenarian_name", "size"),
        verified=("verified", "max")).sort_values("article_count", ascending=False).head(10)
    top["longevity_tier"] = [indiv_tier.get(n) for n in top.index]
    with pd.option_context("display.width", 160):
        print(top.to_string())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
