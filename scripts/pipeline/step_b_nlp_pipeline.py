#!/usr/bin/env python3
"""
nlp_pipeline.py — Phase 2 NLP feature extraction for the Centenarian Clock.

Passes:
  1. NER pass      — fix subject_name / subject_age using entity-level age association
  2. Feature pass  — corpus-driven frequency + lift analysis, weighted by source quality
  3. Matrix pass   — build per-document feature columns and tier flags

Outputs (data/processed/):
  master_dataset_nlp.csv  — original columns + NLP columns + feature matrix
  feature_registry.csv    — ranked features with tier, lift, evidence strength

Also attempts optional downloads:
  data/raw/datasets/cent_WGS.txt              (Italian supercentenarian WGS, 158 MB)
  data/raw/datasets/wpp_life_expectancy.csv   (UN World Population Prospects)
  NOTE: NHANES methylation requires dbGaP authorization — not on public NHANES lab pages.
  NOTE: HMD requires email verification — manual steps printed at end.

Run: python nlp_pipeline.py
     python nlp_pipeline.py --skip-download   (skip optional downloads)
     python nlp_pipeline.py --resume          (skip already-processed rows)
"""

import argparse
import json
import math
import re
import sys
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

PROCESSED   = Path("data/processed")
RAW_DS      = Path("data/raw/datasets")
INPUT_CSV   = PROCESSED / "master_dataset.csv"
OUTPUT_CSV  = PROCESSED / "master_dataset_nlp.csv"
INTER_PKL   = PROCESSED / "nlp_intermediate.pkl"       # resumable checkpoint
FEAT_REG    = PROCESSED / "feature_registry.csv"

SPACY_MODEL  = "en_core_web_sm"
BATCH_SIZE   = 100    # rows per nlp.pipe batch
SAVE_EVERY   = 1000   # checkpoint frequency (rows)
AGE_MIN, AGE_MAX = 95, 135
MAX_CHAR_DIST    = 600    # max char distance for PERSON–age association
MIN_FEAT_CENT_FREQ = 15   # minimum centenarian-doc mentions to keep a discovered phrase
MIN_FEAT_LIFT      = 1.3  # minimum lift over general corpus

# ─────────────────────────────────────────────────────────────────────────────
# Optional downloads
# ─────────────────────────────────────────────────────────────────────────────

DOWNLOADS = {
    "cent_WGS.txt": {
        "url":  "https://ndownloader.figshare.com/files/27659406",
        "dest": RAW_DS / "cent_WGS.txt",
        "desc": "Italian supercentenarian whole-genome sequencing (158 MB)",
        "size_mb": 158,
    },
}

def attempt_downloads(skip=False):
    print("\n--- Optional Downloads ---")
    if skip:
        print("  --skip-download set. Skipping.")
        return

    try:
        import requests
    except ImportError:
        print("  requests not installed — skipping downloads.")
        return

    for name, info in DOWNLOADS.items():
        dest = info["dest"]
        if dest.exists():
            print(f"  {name}: already present ({dest})")
            continue
        print(f"  Downloading {info['desc']} ...")
        print(f"    URL: {info['url']}")
        try:
            resp = requests.get(info["url"], stream=True, timeout=30)
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 256):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded / total * 100
                        print(f"\r    {pct:.1f}%  ({downloaded/1e6:.1f}/{total/1e6:.1f} MB)", end="", flush=True)
            print(f"\n    Saved: {dest}  ({downloaded/1e6:.1f} MB)")
        except Exception as e:
            print(f"    FAILED: {e}")
            if dest.exists():
                dest.unlink()

    # UN WPP note
    print("  UN WPP: URL structure changed — check https://population.un.org/wpp for current links.")
    print("  NHANES methylation: requires dbGaP authorization (not on public NHANES lab page).")

    # HMD manual instructions
    print("""
--- Human Mortality Database — Manual Download Steps ---
  1. Go to: https://www.mortality.org
  2. Click "Register" — enter your email, name, institution
  3. You will receive a verification email — click the link
  4. Log in → Data → Download → Life Tables (Period, 1x1) → Select All Countries → Download ZIP
  5. Unzip into: data/raw/datasets/hmd/
  merge_all.py will process them automatically on next run.
""")


# ─────────────────────────────────────────────────────────────────────────────
# spaCy setup
# ─────────────────────────────────────────────────────────────────────────────

def ensure_spacy():
    try:
        import spacy
    except ImportError:
        sys.exit("spaCy not installed. Run: pip install spacy")

    try:
        nlp = spacy.load(SPACY_MODEL)
        print(f"  Loaded spaCy model: {SPACY_MODEL}")
    except OSError:
        print(f"  {SPACY_MODEL} not found — downloading...")
        import subprocess
        subprocess.run([sys.executable, "-m", "spacy", "download", SPACY_MODEL], check=True)
        nlp = spacy.load(SPACY_MODEL)
        print(f"  Downloaded and loaded: {SPACY_MODEL}")

    # Disable unused pipeline components to speed up processing
    disabled = [p for p in ["textcat", "senter", "morphologizer"] if p in nlp.pipe_names]
    for p in disabled:
        nlp.disable_pipe(p)

    print(f"  Active pipes: {nlp.pipe_names}")
    print(f"  NOTE: en_core_web_lg or en_core_web_trf would improve PERSON NER")
    print(f"        in short news snippets and non-Western names. Flag for Phase 3.")
    return nlp


# ─────────────────────────────────────────────────────────────────────────────
# Boilerplate filter — strip UI/JS/scrape artifacts from news text only
# (Academic abstracts don't have this problem; they bypass this stage.)
# ─────────────────────────────────────────────────────────────────────────────

# Phrases to delete on substring match (scrape-concatenation artifacts and known junk).
# Case-insensitive. These get nuked before sentence splitting so they don't leak
# into discovered phrases via boundary effects.
_BOILERPLATE_SUBSTRINGS = [
    "lessdisplay advertising",
    "fromlocal businessespromotinglocal service",
    "fromlocal businesses",
    "promotinglocal service",
    "promotinglocal",
    "thelocal community",
    "piano meteractive meterexpired callbackevent",
    "piano meteractive meterexpired",
    "piano meteractive",
    "meteractive meterexpired",
    "meterexpired callbackevent",
    "callbackevent",
    "useandprivacy policy",
    "useandprivacy",
    "lively civil forum",
    "more lessdisplay",
    "challenge time",
    # v2 — observed in dedup/registry audit
    "community guidelines",
    "ourcommunity guidelines",
    "ourcommunity guidelinesfor",
    "agree ourterms",
    "agree to ourterms",
    "follow comments",
    "follow comment",
    "you follow comments",
    "comment relevant respectful",
    "lively civil forum maintain",
    "maintain lively civil forum",
    "promote advert",
    "promotional advert",
    "receive email",
    "newsletter signup",
    "subscribe button",
    "challenging times",
    "during these challenging",
    "need challenge time",
    "need support possible",
    "need as much support as possible",
    "as much support as possible during these challenging",
    "challenging times as much support as possible",
    "great reading every saturday",
    "big issues on wednesday",
    "agree to our terms",
    "trending now",
]

# Pre-substitutions that split common scrape-glue patterns into real words.
# Run before any sentence splitting / regex matching so phrases like
# "andobesity" or "ourCommunity" don't survive as fake tokens.
_GLUE_PATTERNS = [
    # camelCase split: insert space at lowercase->uppercase boundary
    (re.compile(r"([a-z])([A-Z])"),                     r"\1 \2"),
    # Common glued connectives -> "and obesity", "tobacco as", "our terms" ...
    (re.compile(r"\bandobesity\b",  re.I),              "and obesity"),
    (re.compile(r"\btobaccoas\b",   re.I),              "tobacco as"),
    (re.compile(r"\bourterms\b",    re.I),              "our terms"),
    (re.compile(r"\bourcommunity\b", re.I),             "our community"),
    (re.compile(r"\bGuidelinesfor\b", re.I),            "Guidelines for"),
    (re.compile(r"\bbusinessespromoting\b", re.I),      "businesses promoting"),
    (re.compile(r"\bmeteractive\b", re.I),              "meter active"),
    (re.compile(r"\bmeterexpired\b", re.I),             "meter expired"),
    (re.compile(r"\bcallbackevent\b", re.I),            "callback event"),
    # Generic: short connective + 4+ letters that begin with vowel cluster
    (re.compile(r"\b(and|but|the|our|for|with)([A-Z][a-z]{3,})\b"),  r"\1 \2"),
]

# Sentence-level boilerplate patterns. Any sentence matching one of these is dropped.
# Conservative: only drop sentences whose primary content IS boilerplate, not
# sentences that happen to mention these phrases incidentally.
_BOILERPLATE_PATTERNS = [
    # Cookie / consent banners
    r"\bwe use cookies\b", r"\bcookie (?:policy|notice|preferences|settings|consent)\b",
    r"\baccept (?:all )?cookies\b", r"\bby clicking (?:accept|i agree|agree)\b",
    r"\bthis (?:site|website|page) uses cookies\b",
    r"\b(?:enable|disable) cookies\b", r"\bmanage (?:cookie )?preferences\b",
    # Privacy / terms / legal
    r"\bprivacy policy\b", r"\bterms of (?:service|use|conditions)\b",
    r"\ball rights reserved\b", r"\bcopyright\s+(?:©|\(c\)|\d{4})\b",
    # Newsletter / email signup
    r"\bsubscribe to (?:our )?(?:newsletter|email)\b",
    r"\b(?:daily|weekly|monthly|free) newsletter\b",
    r"\bsign up (?:for|to)\b(?:[^.!?]{0,40})\b(?:newsletter|updates|emails?)\b",
    r"\benter your email\b", r"\bemail (?:address )?required\b",
    r"\b(?:get|receive) (?:the )?latest (?:news|stories|updates)\b",
    # Advertising
    r"\bdisplay advertising\b", r"\badvertisement\b",
    r"\bsponsored (?:content|by|post|article)\b", r"\bpromotional content\b",
    r"\btarget audience\b",
    r"\bsmall businesses?\s+(?:advertising|promote|reach)\b",
    r"\b(?:from\s+)?local businesses?\s+(?:promote|advertising|target)\b",
    # JS/scrape artifacts (any line containing these is junk)
    r"\bdata ?layer\b", r"\bgoogle ?tag\b", r"\bwindow\.__\w+\b",
    r"\bdocument\.(?:getElementById|querySelector)\b",
    r"\bpiano meter\b",
    # Comments / forum CTAs
    r"\bcomment policy\b", r"\bjoin the conversation\b",
    r"\bleave a comment\b", r"\bcomments? (?:below|section|are\s+closed)\b",
    # Social sharing
    r"\bshare (?:this article|on facebook|on twitter|on linkedin|via email)\b",
    r"\bfollow us on\s+(?:facebook|twitter|instagram|linkedin)\b",
    r"\btweet this\b", r"\bshare via\b",
    # Read more / related / trending
    r"\bread more\b", r"\bcontinue reading\b",
    r"\brelated (?:articles?|stories|content|posts?)\b",
    r"\byou (?:may|might) also like\b",
    r"\btrending (?:now|today|this week)\b",
    r"\bmost (?:read|popular|viewed)\b", r"\beditor'?s picks?\b",
    # Navigation
    r"\bskip to (?:main )?content\b",
    r"\b(?:main|primary|site) (?:menu|navigation)\b",
    r"\bsearch this site\b", r"\bquick links\b",
    # Paywall / subscription
    r"\bsubscribe (?:today|now|for)\b", r"\bsubscribe for (?:unlimited|full)\b",
    r"\bpremium (?:content|article|subscriber|access)\b",
    r"\bfor subscribers only\b", r"\bfree trial\b",
    r"\b(?:create|register for) (?:an? )?account\b",
    r"\balready (?:a subscriber|registered)\b",
    # Footer / nav
    r"\babout us\b\s*[\|·•]?\s*\bcontact us\b",
    r"\bcontact us\b\s*[\|·•]?\s*\babout us\b",
    # v2 — observed footer / comments-moderation boilerplate
    r"\bcommunity guidelines?\b",
    r"\bfollow comments?\b",
    r"\bagree (?:to )?(?:our )?terms\b",
    r"\bkeep comments? (?:relevant|respectful|civil)\b",
    r"\bmaintain (?:a )?lively (?:civil )?forum\b",
    r"\bduring (?:these )?challenging times\b",
    r"\bas much support as possible\b",
    r"\bgreat reading (?:every )?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    r"\bbig issues on (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    r"\bvisit (?:our )?community\b",
    r"\bget news (?:via|by) email\b",
    r"\breceive (?:our )?email\b",
    r"\b(?:moderator|moderation) (?:team|policy)\b",
    r"\bview comments?\b",
]
_BOILERPLATE_COMPILED = [re.compile(p, re.I) for p in _BOILERPLATE_PATTERNS]


def clean_news_text(text):
    """
    Strip UI/JS/scrape boilerplate from a news article body.

    Two passes:
      1. Substring removal for known scrape-concatenation artifacts.
      2. Sentence-level drop for sentences matching any boilerplate pattern.

    Returns the cleaned text (whitespace-normalized). Empty input → "".
    """
    if not text:
        return ""

    # Pass 0: split known scrape-glue patterns (ourCommunity, andobesity, ...)
    for pat, repl in _GLUE_PATTERNS:
        text = pat.sub(repl, text)

    # Pass 1: nuke known substring junk (case-insensitive)
    for junk in _BOILERPLATE_SUBSTRINGS:
        text = re.sub(re.escape(junk), " ", text, flags=re.IGNORECASE)

    # Normalize whitespace so sentence splitting is reliable
    text = re.sub(r"\s+", " ", text).strip()

    # Pass 2: split into rough sentences and drop boilerplate sentences
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'])", text)
    keep = []
    for s in sentences:
        s = s.strip()
        if len(s) < 12:           # skip fragments — likely menu items or labels
            continue
        if any(p.search(s) for p in _BOILERPLATE_COMPILED):
            continue
        keep.append(s)

    return " ".join(keep)


# ─────────────────────────────────────────────────────────────────────────────
# Document weighting
# ─────────────────────────────────────────────────────────────────────────────

STUDY_TYPE_WEIGHTS = {
    "meta_analysis": 5.0, "meta-analysis": 5.0,
    "rct": 4.0, "randomized_trial": 4.0,
    "cohort": 3.0,
    "cross_sectional": 2.0,
    "review": 1.5,
    "case_report": 1.0, "case_study": 1.0,
    "other": 1.0,
}

def compute_doc_weight(row):
    src = str(row.get("source_type", "")).lower()
    if src == "academic":
        st = str(row.get("study_type") or "other").lower().strip()
        base = STUDY_TYPE_WEIGHTS.get(st, 1.0)

        ss = row.get("stat_sample_size")
        if pd.notna(ss):
            try:
                ss_f = math.log(max(float(ss), 2)) / math.log(1000)
                ss_f = max(0.5, min(ss_f, 3.0))
            except (ValueError, TypeError):
                ss_f = 1.0
        else:
            ss_f = 1.0

        has_es = (pd.notna(row.get("stat_odds_ratio")) or pd.notna(row.get("stat_hazard_ratio")))
        es_f = 1.5 if has_es else 1.0

        pv = row.get("stat_p_value")
        try:
            sig_f = 1.2 if (pd.notna(pv) and float(pv) < 0.05) else 1.0
        except (ValueError, TypeError):
            sig_f = 1.0

        return min(base * ss_f * es_f * sig_f, 20.0)

    elif src == "news":
        is_cent = row.get("is_centenarian_profile", 0) or 0
        base = 2.0 if int(is_cent) == 1 else 0.5
        age = row.get("subject_age")
        try:
            age_f = 1.0 + min((float(age) - 100) / 15.0, 1.0) if pd.notna(age) else 1.0
        except (ValueError, TypeError):
            age_f = 1.0
        return base * max(age_f, 1.0)

    return 1.0


# ─────────────────────────────────────────────────────────────────────────────
# NER: associate ages with named people
# ─────────────────────────────────────────────────────────────────────────────

_AGE_RES = [
    re.compile(r'\b(\d{2,3})[- ]year[s]?[- ]old\b', re.I),
    re.compile(r'\baged?\s+(\d{2,3})\b', re.I),
    re.compile(r'\bat\s+(?:the\s+)?age\s+of\s+(\d{2,3})\b', re.I),
    re.compile(r'\b(\d{2,3})\s+years?\s+old\b', re.I),
    re.compile(r'\bwho\s+(?:was|is|turned?)\s+(\d{2,3})\b', re.I),
    re.compile(r'\bturned?\s+(\d{2,3})\b', re.I),
    re.compile(r'\bcentenarian\s+(?:aged?|who\s+is)\s+(\d{2,3})\b', re.I),
    re.compile(r'\bsupercentenarian\s+aged?\s+(\d{2,3})\b', re.I),
]

def _age_mentions(text):
    hits = []
    for pat in _AGE_RES:
        for m in pat.finditer(text):
            try:
                v = int(m.group(1))
                if AGE_MIN <= v <= AGE_MAX:
                    hits.append((v, m.start()))
            except (IndexError, ValueError):
                pass
    return hits   # list of (age_value, char_pos)


def ner_extract(doc, text):
    """
    Return (name, age) for the most prominent centenarian in text.
    Uses spaCy PERSON entities + regex age patterns.
    Prefers entities appearing close to an age mention.
    """
    ages = _age_mentions(text)
    if not ages:
        return None, None

    persons = [e for e in doc.ents if e.label_ == "PERSON"]

    if not persons:
        # No named entity — return best age only
        ages.sort(key=lambda x: x[0], reverse=True)
        return None, ages[0][0]

    best_name, best_age, best_dist = None, None, float("inf")
    for age_val, age_pos in ages:
        for ent in persons:
            dist = abs(ent.start_char - age_pos)
            if dist < best_dist and dist < MAX_CHAR_DIST:
                best_dist = dist
                best_name = ent.text.strip()
                best_age  = age_val

    # Fallback: no close PERSON found, return age alone from first mention
    if best_age is None:
        best_age = ages[0][0]

    return best_name, best_age


# ─────────────────────────────────────────────────────────────────────────────
# Phrase extraction for corpus-first feature discovery
#
# Three phrase types are extracted independently:
#   - noun_phrase    : 2-4 word noun chunks (lemmatized)
#   - verb_phrase    : VERB + direct/prepositional object pairs (lemmatized)
#   - attribution    : objects of "secret to longevity", "credits her long life to",
#                      "attributed to ...", etc. — highest-confidence direct voice
#
# Proper-noun entities (PERSON, GPE, ORG, LOC, NORP, FAC) are dropped from the
# vocabulary entirely — they are entities, not traits.
# ─────────────────────────────────────────────────────────────────────────────

# Junk lemmas that should not appear as standalone discovered features.
_JUNK = {
    "study", "studies", "paper", "papers", "article", "articles", "result",
    "results", "finding", "findings", "analysis", "analyses", "method",
    "methods", "datum", "data", "sample", "samples", "group", "groups",
    "participant", "participants", "subject", "subjects", "patient", "patients",
    "individual", "individuals", "cohort", "cohorts", "population", "populations",
    "number", "percent", "percentage", "rate", "ratio", "odds", "hazard",
    "confidence", "interval", "value", "level", "mean", "average", "median",
    "range", "standard", "deviation", "regression", "model", "variable",
    "factor", "association", "relationship", "correlation", "effect", "impact",
    "logistic", "linear", "multivariate", "covariate", "adjusted", "unadjusted",
    "table", "figure", "conclusion", "introduction", "background", "aim",
    "objective", "author", "year", "month", "week", "day", "period", "follow",
    "control", "comparison", "age", "sex", "gender", "p-value", "ci",
    # News-side fillers that survive the boilerplate filter
    "news", "story", "stories", "reporter", "editor", "photo", "image",
    "video", "caption", "link", "click", "page", "site", "website",
}

# Entity labels whose spans we exclude from generic noun/verb phrase features.
# Person names are never traits. Place/organization names CAN be exposomic signal
# (Blue Zones, Okinawa, Sardinia) so we KEEP them in the discovered vocabulary.
_PERSON_LABELS = {"PERSON"}
# Labels that, when found inside an attribution object, change the feature_type
_ATTRIB_PLACE_LABELS   = {"GPE", "LOC", "FAC"}
_ATTRIB_PRODUCT_LABELS = {"PRODUCT", "WORK_OF_ART", "ORG"}


def _person_token_indices(doc):
    """Return the set of token indices covered by PERSON entity spans only."""
    blocked = set()
    for ent in doc.ents:
        if ent.label_ in _PERSON_LABELS:
            for i in range(ent.start, ent.end):
                blocked.add(i)
    return blocked


_LONG_CONSONANT_RE = re.compile(r"[bcdfghjklmnpqrstvwxz]{5,}", re.I)
_GLUE_PREFIX_RE    = re.compile(r"^(and|but|the|our|for|with|from|that)[a-z]{4,}", re.I)


def _looks_like_concatenated(raw_text):
    """Heuristic: token surface looks like an unintended word concatenation."""
    if len(raw_text) > 18:               # almost no real single English word is this long
        return True
    if _LONG_CONSONANT_RE.search(raw_text):    # "callbackevent"-style consonant runs
        return True
    if _GLUE_PREFIX_RE.match(raw_text):        # "andobesity", "ourterms"-style glues
        return True
    return False


def _normalize_tokens(tokens):
    """Lemmatize + lowercase + filter stops/punct/short/concatenated tokens."""
    out = []
    for t in tokens:
        if not t.is_alpha or t.is_stop or len(t.text) <= 2:
            continue
        if _looks_like_concatenated(t.text):
            return []                  # reject the whole phrase if any token is junk
        out.append(t.lemma_.lower())
    return out


def extract_noun_chunks(doc, blocked_idx):
    """
    Return list of normalized 2-4 word noun phrases from a spaCy doc.
    Excludes any chunk that overlaps a blocked entity span (PERSON/GPE/ORG/LOC/...).
    """
    chunks = []
    for chunk in doc.noun_chunks:
        if any(i in blocked_idx for i in range(chunk.start, chunk.end)):
            continue
        toks = _normalize_tokens(chunk)
        if len(toks) < 2 or len(toks) > 5:
            continue
        if all(w in _JUNK for w in toks):
            continue
        phrase = " ".join(toks)
        if len(phrase) < 5:
            continue
        chunks.append(phrase)
    return chunks


def extract_verb_phrases(doc, blocked_idx):
    """
    Extract VERB + direct-object / VERB + preposition + object phrases.
    Uses spaCy dependency parse. Returns lemmatized 2-3 word phrases like
    "eat vegetable", "drink wine", "walk every day", "live alone".

    Excludes phrases whose object overlaps a blocked entity span.
    """
    phrases = []
    for tok in doc:
        if tok.pos_ != "VERB" or tok.lemma_ in {"be", "have", "do", "say",
                                                 "see", "find", "show",
                                                 "use", "make", "get", "report",
                                                 "include", "provide"}:
            continue
        vlemma = tok.lemma_.lower()
        if len(vlemma) < 3:
            continue
        for child in tok.children:
            if child.dep_ not in {"dobj", "pobj", "attr", "advmod", "prep"}:
                continue
            # Take the noun-chunk span this child anchors
            head = child
            if child.dep_ == "prep":
                # follow prep to its pobj
                for gc in child.children:
                    if gc.dep_ == "pobj":
                        head = gc
                        break
                else:
                    continue
            span_start = head.left_edge.i
            span_end   = head.right_edge.i + 1
            if any(i in blocked_idx for i in range(span_start, span_end)):
                continue
            obj_toks = _normalize_tokens(doc[span_start:span_end])
            if not obj_toks or len(obj_toks) > 3:
                continue
            if all(w in _JUNK for w in obj_toks):
                continue
            phrase = f"{vlemma} {' '.join(obj_toks)}"
            if len(phrase) < 7 or len(phrase) > 60:
                continue
            phrases.append(phrase)
    return phrases


# Direct-attribution patterns. Capturing group is the WHAT (the practice/trait).
# Designed for centenarian-profile journalism.
_ATTRIB_RES = [
    re.compile(r"\b(?:I|she|he|they)\s+attributes?\s+(?:my|her|his|the|their|it)?\s*(?:longevity|long\s+life|long\s+years|age)?\s*(?:to\s+)([^.;!?]{6,90})", re.I),
    re.compile(r"\b(?:she|he|they)\s+credits?\s+([^.;!?]{6,90})\s+(?:for|with)\s+(?:her|his|their)?\s*(?:longevity|long\s+life|long\s+years|long\s+age)", re.I),
    re.compile(r"\bcredits?\s+(?:her|his|their|my)\s+(?:long\s+life|longevity|long\s+years|long\s+age)\s+to\s+([^.;!?]{6,90})", re.I),
    re.compile(r"\b(?:her|his|my|their)\s+secret\s+(?:to\s+(?:longevity|long\s+life|living\s+long|living\s+to\s+\d+)\s+)?(?:is|was|are|were)\s+([^.;!?]{6,90})", re.I),
    re.compile(r"\battributed?\s+(?:her|his|their|the|it|my)\s+(?:longevity|long\s+life|long\s+years)\s+to\s+([^.;!?]{6,90})", re.I),
    re.compile(r"\b(?:the\s+)?(?:key|secret|recipe|formula|reason)\s+(?:to|of|for|behind)\s+(?:her|his|their|my)\s+(?:long\s+life|longevity|long\s+years|long\s+age|long\s+\d+\s+years)\s+(?:is|was)\s+([^.;!?]{6,90})", re.I),
    re.compile(r"\b(?:she|he|they)\s+says?\s+(?:her|his|their)\s+secret\s+(?:to\s+(?:longevity|long\s+life)\s+)?(?:is|was)\s+([^.;!?]{6,90})", re.I),
    re.compile(r"\b(?:she|he|they)\s+(?:said|believes?|thinks?|claims?|stated)\s+(?:that\s+)?(?:her|his|their)\s+(?:longevity|long\s+life)\s+(?:is|was)?\s*(?:due\s+to|because\s+of|thanks\s+to|comes?\s+from)\s+([^.;!?]{6,90})", re.I),
    re.compile(r"\b(?:she|he|they)\s+(?:lived|lives)\s+to\s+\d+\s+(?:by|because\s+of|thanks\s+to|due\s+to)\s+([^.;!?]{6,90})", re.I),
    re.compile(r"\b(?:put|puts|putting)\s+(?:her|his|their)\s+(?:longevity|long\s+life|long\s+years)\s+down\s+to\s+([^.;!?]{6,90})", re.I),
    re.compile(r"\b(?:thanks?|owes?)\s+(?:her|his|their)\s+(?:longevity|long\s+life|long\s+years|long\s+age)\s+to\s+([^.;!?]{6,90})", re.I),
]


def _trim_attrib_object(s, lower=True):
    """Clean a raw attribution-object string into a normalized phrase.
    Set lower=False to preserve capitalization (needed for downstream NER)."""
    s = s.strip().strip(",;:'\"")
    s = re.sub(r"^(?:a |an |the |that |which |it |this |these |those |her |his |their |my |our )+", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s)
    if lower:
        s = s.lower()
    # Stop at a clause break (case-insensitive)
    for stop in [" and ", " but ", " because ", " which ", " who ", " that ",
                 " however ", " though ", " although ", " while "]:
        idx = s.lower().find(stop)
        if 5 < idx < 80:
            s = s[:idx]
    if len(s) > 60:
        s = s[:60].rsplit(" ", 1)[0]
    return s.strip()


def extract_attribution_phrases(text, nlp=None):
    """
    Extract phrases that follow direct-attribution constructions like
    'her secret to longevity is ...' or 'attributed his long life to ...'.

    Returns list[(typed_phrase, subtype)]:
      subtype ∈ {"attribution", "attribution_place", "attribution_product"}

    PERSON-entity tokens are stripped from the object (we want the WHAT, not
    the WHO). GPE/LOC/FAC presence in the object promotes it to
    "attribution_place" (exposomic signal — e.g. "Italian village", "Okinawa").
    PRODUCT/ORG/WORK_OF_ART presence promotes it to "attribution_product".
    """
    out = []
    for pat in _ATTRIB_RES:
        for m in pat.finditer(text):
            obj_raw = m.group(1)
            # Trim preserving case for downstream NER
            cased = _trim_attrib_object(obj_raw, lower=False)
            if len(cased) < 4 or len(cased) > 80:
                continue
            cleaned = cased.lower()
            if any(w in cleaned for w in ("cookie", "newsletter", "subscribe",
                                          "advertis", "click here", "read more",
                                          "community guideline", "ourcommunity",
                                          "follow comment")):
                continue

            subtype = "attribution"
            if nlp is not None:
                # NER on the cased trimmed phrase (capitalization matters)
                small = nlp(cased)
                labels = {e.label_ for e in small.ents}
                # Strip PERSON tokens — operate on cased then lowercase result
                if _PERSON_LABELS & labels:
                    person_spans = [(e.start_char, e.end_char) for e in small.ents
                                    if e.label_ in _PERSON_LABELS]
                    keep, last = [], 0
                    for s, e in sorted(person_spans):
                        keep.append(cased[last:s])
                        last = e
                    keep.append(cased[last:])
                    cased = _trim_attrib_object(
                        " ".join(p for p in keep if p.strip()), lower=False
                    )
                    if len(cased) < 4:
                        continue
                    small   = nlp(cased)
                    labels  = {e.label_ for e in small.ents}
                    cleaned = cased.lower()
                if labels & _ATTRIB_PLACE_LABELS:
                    subtype = "attribution_place"
                elif labels & _ATTRIB_PRODUCT_LABELS:
                    subtype = "attribution_product"
            out.append((cleaned, subtype))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Context window capture for example_phrases column
# ─────────────────────────────────────────────────────────────────────────────

# How many example contexts to keep per phrase across the whole corpus.
# Capped to keep memory bounded and registry CSV readable.
MAX_CONTEXTS_PER_PHRASE = 5
# Words of context to keep on either side of the matched phrase.
CONTEXT_RADIUS_WORDS = 5


def capture_context_for_chunk(doc, chunk, contexts, phrase, record_id):
    """Append a ±5-word context snippet to contexts[phrase] (capped)."""
    bucket = contexts[phrase]
    if len(bucket) >= MAX_CONTEXTS_PER_PHRASE:
        return
    start = max(0, chunk.start - CONTEXT_RADIUS_WORDS)
    end   = min(len(doc), chunk.end + CONTEXT_RADIUS_WORDS)
    ctx   = doc[start:end].text.strip()
    ctx   = re.sub(r"\s+", " ", ctx)
    if len(ctx) > 220:
        ctx = ctx[:220].rsplit(" ", 1)[0] + "..."
    bucket.append(f"[{record_id}] {ctx}")


def capture_context_for_string(text, phrase, contexts, record_id):
    """Append a ±5-word context for a phrase located by regex in raw text."""
    bucket = contexts[phrase]
    if len(bucket) >= MAX_CONTEXTS_PER_PHRASE:
        return
    m = re.search(re.escape(phrase), text, re.IGNORECASE)
    if not m:
        return
    # Word-boundary expansion: walk back/forward CONTEXT_RADIUS_WORDS spaces
    start = m.start()
    end   = m.end()
    pre   = text[:start].rsplit(" ", CONTEXT_RADIUS_WORDS)
    post  = text[end:].split(" ", CONTEXT_RADIUS_WORDS + 1)
    pre_ctx  = " ".join(pre[-CONTEXT_RADIUS_WORDS:]) if len(pre) > 1 else ""
    post_ctx = " ".join(post[:CONTEXT_RADIUS_WORDS]) if len(post) > 1 else ""
    snippet  = f"{pre_ctx} {text[start:end]} {post_ctx}".strip()
    snippet  = re.sub(r"\s+", " ", snippet)
    if len(snippet) > 220:
        snippet = snippet[:220].rsplit(" ", 1)[0] + "..."
    bucket.append(f"[{record_id}] {snippet}")


# ─────────────────────────────────────────────────────────────────────────────
# NHANES alignment — map surfaced features to nhanes_merged.csv variables
# so Phase 3 scoring has population baselines.
#
# Each entry: concept_id → dict with:
#   keywords     : substrings to match against a feature phrase (lowercased)
#   nhanes_vars  : list of column names in nhanes_merged.csv (post-rename)
#   tier         : 1 (ad/quiz) | 2 (free app) | 3 (premium biomarker/genomic)
#   category     : lifestyle | biomarker | genomic
# ─────────────────────────────────────────────────────────────────────────────

NHANES_FEATURE_MAP = {
    # ── Tier 1/2 lifestyle ──────────────────────────────────────────────────
    "physical_activity": {
        "keywords": ["physical activity", "exercise", "walking", "sedentary",
                     "aerobic", "active lifestyle", "recreation", "vigorous",
                     "moderate activity", "fitness", "sport"],
        "nhanes_vars": ["vigorous_work_yn", "moderate_work_yn",
                        "vigorous_recreation_yn", "moderate_recreation_yn",
                        "walk_bicycle_transport_yn", "sedentary_min_day"],
        "tier": 1, "category": "lifestyle",
    },
    "smoking": {
        "keywords": ["smoking", "tobacco", "cigarette", "smoker", "nicotine",
                     "never smoked", "non-smoker"],
        "nhanes_vars": ["smoked_100_cigarettes_lifetime", "current_smoker",
                        "cigs_per_day_past30", "age_started_smoking",
                        "smoke_inside_home"],
        "tier": 1, "category": "lifestyle",
    },
    "alcohol": {
        "keywords": ["alcohol", "drinking", "wine", "beer", "spirits", "drinker",
                     "abstainer", "moderate drinking"],
        "nhanes_vars": ["drinking_freq_past12mo", "avg_drinks_per_drinking_day",
                        "any_drinking_past12mo", "heavy_drinking_days_past2wk"],
        "tier": 1, "category": "lifestyle",
    },
    "sleep": {
        "keywords": ["sleep", "insomnia", "sleep duration", "sleep quality",
                     "napping", "circadian", "rest", "snore"],
        "nhanes_vars": ["sleep_hours_weekday", "sleep_hours_weekend",
                        "told_sleep_disorder", "sleepy_daytime_frequency",
                        "snore", "snore_frequency"],
        "tier": 1, "category": "lifestyle",
    },
    "diet_nutrition": {
        "keywords": ["diet", "nutrition", "mediterranean", "plant-based",
                     "vegetable", "fruit", "whole grain", "processed food",
                     "eating habit", "food intake", "caloric"],
        # Dietary intake files (DR1/DR2) not in our merged set — population
        # diet baseline must come from NHANES dietary recall files separately.
        "nhanes_vars": [],
        "tier": 1, "category": "lifestyle",
        "nhanes_note": "NHANES dietary recall (DR1IFF, DR1TOT) not in merged file",
    },
    "social_connection": {
        "keywords": ["social", "marriage", "married", "loneliness", "isolation",
                     "social network", "social support", "friendship",
                     "community", "relationship"],
        "nhanes_vars": ["marital_status", "household_size", "family_size",
                        "household_adults_over60"],
        "tier": 1, "category": "lifestyle",
    },
    "education_cognitive": {
        "keywords": ["education", "cognitive", "intellectual", "learning",
                     "reading", "literacy", "schooling"],
        "nhanes_vars": ["education_adult"],
        "tier": 2, "category": "lifestyle",
    },
    "occupation_retirement": {
        "keywords": ["retirement", "working", "occupation", "employment",
                     "productive activity", "labor", "job"],
        "nhanes_vars": [],
        "tier": 2, "category": "lifestyle",
        "nhanes_note": "NHANES occupation file (OCQ) not in merged file",
    },
    # ── Tier 3 biomarkers ───────────────────────────────────────────────────
    "inflammation_crp": {
        "keywords": ["crp", "c-reactive protein", "inflammation",
                     "inflammatory marker", "systemic inflammation",
                     "chronic inflammation"],
        "nhanes_vars": ["crp_mg_l"],
        "tier": 3, "category": "biomarker",
    },
    "glucose_metabolism": {
        "keywords": ["glucose", "fasting glucose", "blood glucose", "hba1c",
                     "glycated hemoglobin", "glycemia", "glycemic",
                     "insulin resistance", "prediabetes"],
        "nhanes_vars": ["fasting_glucose_mg_dl", "hba1c_pct"],
        "tier": 3, "category": "biomarker",
    },
    "diabetes_status": {
        "keywords": ["diabetes", "diabetic", "type 2 diabetes", "type ii diabetes"],
        "nhanes_vars": ["diagnosed_diabetes", "taking_insulin",
                        "taking_diabetes_pills", "age_diagnosed_diabetes"],
        "tier": 3, "category": "biomarker",
    },
    "cholesterol_lipids": {
        "keywords": ["cholesterol", "ldl", "hdl", "lipid", "dyslipidemia",
                     "lipoprotein", "total cholesterol"],
        "nhanes_vars": ["total_cholesterol_mg_dl", "hdl_cholesterol_mg_dl",
                        "ldl_mg_dl", "ldl_direct_mg_dl"],
        "tier": 3, "category": "biomarker",
    },
    "triglycerides": {
        "keywords": ["triglyceride", "trig"],
        "nhanes_vars": ["triglycerides_mg_dl"],
        "tier": 3, "category": "biomarker",
    },
    "blood_pressure": {
        "keywords": ["blood pressure", "hypertension", "systolic", "diastolic",
                     "hypertensive", "normotensive", "arterial pressure"],
        "nhanes_vars": ["systolic_bp1_mmhg", "diastolic_bp1_mmhg",
                        "systolic_bp2_mmhg", "diastolic_bp2_mmhg",
                        "systolic_bp3_mmhg", "diastolic_bp3_mmhg"],
        "tier": 3, "category": "biomarker",
    },
    "body_composition": {
        "keywords": ["body mass index", "bmi", "body weight", "obesity",
                     "overweight", "underweight", "adiposity", "waist",
                     "body composition", "muscle mass", "lean mass",
                     "sarcopenia"],
        "nhanes_vars": ["bmi", "weight_kg", "standing_height_cm",
                        "waist_circumference_cm", "hip_circumference_cm",
                        "arm_circumference_cm"],
        "tier": 3, "category": "biomarker",
    },
    "immune_blood": {
        "keywords": ["immune", "lymphocyte", "neutrophil", "white blood cell",
                     "leukocyte", "immunity", "wbc", "platelet"],
        "nhanes_vars": ["wbc_1000_per_ul", "lymphocyte_pct", "neutrophil_pct",
                        "lymphocyte_1000_per_ul", "neutrophil_1000_per_ul",
                        "platelets_1000_per_ul"],
        "tier": 3, "category": "biomarker",
    },
    "anemia_red_cells": {
        "keywords": ["hemoglobin", "red blood cell", "anemia", "hematocrit",
                     "rbc"],
        "nhanes_vars": ["hemoglobin_g_dl", "rbc_million_per_ul",
                        "hematocrit_pct", "mcv_fl", "mch_pg"],
        "tier": 3, "category": "biomarker",
    },
    # ── Biomarkers / genomics not in NHANES public merged file ──────────────
    "telomere_length": {
        "keywords": ["telomere", "telomerase", "telomere length", "leukocyte telomere"],
        "nhanes_vars": [],   # available in NHANES 1999-2002 cycle only (not merged)
        "tier": 3, "category": "biomarker",
        "nhanes_note": "NHANES 1999-2002 telomere file (TELO_A/B) not in merged set",
    },
    "epigenetic_methylation": {
        "keywords": ["methylation", "dna methylation", "epigenetic", "epigenome",
                     "epigenetic clock", "horvath", "phenoage", "grimage"],
        "nhanes_vars": [],
        "tier": 3, "category": "biomarker",
        "nhanes_note": "NHANES methylation data requires dbGaP authorization",
    },
    "microbiome_gut": {
        "keywords": ["microbiome", "gut microbiota", "gut bacteria", "microbiota",
                     "gut flora"],
        "nhanes_vars": [],
        "tier": 3, "category": "biomarker",
        "nhanes_note": "Not collected in NHANES",
    },
    "kidney_function": {
        "keywords": ["creatinine", "kidney function", "gfr", "egfr",
                     "renal function", "cystatin"],
        "nhanes_vars": [],
        "tier": 3, "category": "biomarker",
        "nhanes_note": "NHANES biochemistry profile (BIOPRO) not in merged set",
    },
    # ── Tier 3 genomic ──────────────────────────────────────────────────────
    "apoe_gene": {
        "keywords": ["apoe", "apolipoprotein e", "apoe4", "apoe2", "apoe3",
                     "e4 allele"],
        "nhanes_vars": [],
        "tier": 3, "category": "genomic",
        "nhanes_note": "NHANES does not release individual-level genotypes publicly",
    },
    "foxo3_gene": {
        "keywords": ["foxo3", "foxo", "forkhead box"],
        "nhanes_vars": [],
        "tier": 3, "category": "genomic",
        "nhanes_note": "Not collected in NHANES",
    },
    "longevity_snps": {
        "keywords": ["longevity snp", "gwas longevity", "longevity locus",
                     "longevity allele", "centenarian genome"],
        "nhanes_vars": [],
        "tier": 3, "category": "genomic",
        "nhanes_note": "Centenarian-specific GWAS — not in NHANES",
    },
    "mtor_pathway": {
        "keywords": ["mtor", "rapamycin", "mtorc1", "tor signaling"],
        "nhanes_vars": [],
        "tier": 3, "category": "genomic",
    },
    "sirtuin_nad": {
        "keywords": ["sirtuin", "sirt1", "sirt3", "sirt6", "nad+",
                     "nicotinamide"],
        "nhanes_vars": [],
        "tier": 3, "category": "genomic",
    },
    "mitochondrial": {
        "keywords": ["mitochondria", "mitochondrial dna", "mtdna",
                     "mitochondrial function", "haplogroup"],
        "nhanes_vars": [],
        "tier": 3, "category": "genomic",
    },
}


def match_nhanes(phrase):
    """
    Given a discovered phrase, return (concept_id, nhanes_vars_csv, tier, category).
    If no match, returns ("", "", None, "").
    Matches by substring overlap with concept keywords.
    """
    pl = phrase.lower()
    for concept_id, info in NHANES_FEATURE_MAP.items():
        for kw in info["keywords"]:
            if kw in pl:
                return (
                    concept_id,
                    "|".join(info["nhanes_vars"]),
                    info["tier"],
                    info["category"],
                )
    return ("", "", None, "")


# ─────────────────────────────────────────────────────────────────────────────
# Corpus statistics
# ─────────────────────────────────────────────────────────────────────────────

def compute_corpus_stats(rows_meta):
    """
    rows_meta: list of dicts with keys:
      record_id, is_centenarian, doc_weight, population_country, individual_name,
      noun_phrases / verb_phrases / attribution_phrases /
      attribution_place_phrases / attribution_product_phrases (lists)

    Per-phrase aggregates: freq_cent, freq_all, weighted_score, lift,
                           n_countries, individual_count, individuals (set)

    Returns: {feature_type: ranked_list_of_dicts}
      feature_type ∈ {"noun_phrase", "verb_phrase", "attribution",
                      "attribution_place", "attribution_product"}
    """
    n_cent = sum(1 for r in rows_meta if r["is_centenarian"])
    n_all  = len(rows_meta)

    def new_counter():
        return defaultdict(lambda: {
            "freq_cent": 0, "freq_all": 0,
            "weighted_score": 0.0,
            "countries": set(),
            "individuals": set(),
        })

    counters = {
        "noun_phrase":          new_counter(),
        "verb_phrase":          new_counter(),
        "attribution":          new_counter(),
        "attribution_place":    new_counter(),
        "attribution_product":  new_counter(),
    }
    key_map = {
        "noun_phrase":          "noun_phrases",
        "verb_phrase":          "verb_phrases",
        "attribution":          "attribution_phrases",
        "attribution_place":    "attribution_place_phrases",
        "attribution_product":  "attribution_product_phrases",
    }

    for r in rows_meta:
        w     = r["doc_weight"]
        cen   = r["is_centenarian"]
        cty   = r.get("population_country") or ""
        indiv = (r.get("individual_name") or "").strip()

        for ftype, rkey in key_map.items():
            seen = set(r.get(rkey, []) or [])
            for phrase in seen:
                ctr = counters[ftype][phrase]
                ctr["freq_all"] += 1
                ctr["weighted_score"] += w
                if indiv:
                    ctr["individuals"].add(indiv)
                if cen:
                    ctr["freq_cent"] += 1
                    if cty:
                        ctr["countries"].add(cty)

    # Type-specific floors. Attribution & subtypes have far lower freq; relax.
    type_floors = {
        "noun_phrase":          (MIN_FEAT_CENT_FREQ, MIN_FEAT_LIFT),
        "verb_phrase":          (max(MIN_FEAT_CENT_FREQ // 2, 5), MIN_FEAT_LIFT),
        "attribution":          (3, 1.0),
        "attribution_place":    (3, 1.0),
        "attribution_product":  (3, 1.0),
    }

    ranked = {}
    for ftype, ctr in counters.items():
        min_freq, min_lift = type_floors[ftype]
        out = []
        for phrase, s in ctr.items():
            fc = s["freq_cent"] / max(n_cent, 1)
            fa = s["freq_all"]  / max(n_all, 1)
            lift = fc / max(fa, 1e-9)
            if s["freq_cent"] < min_freq or lift < min_lift:
                continue
            n_cty = len(s["countries"])
            n_ind = len(s["individuals"])
            # population_score upweights phrases spread across many distinct
            # named individuals (vs syndicated single-individual stories).
            pop_score = round(lift * math.log(n_ind + 1), 4)
            out.append({
                "phrase":           phrase,
                "feature_type":     ftype,
                "freq_cent":        s["freq_cent"],
                "freq_all":         s["freq_all"],
                "lift":             round(lift, 3),
                "weighted_score":   round(s["weighted_score"], 2),
                "n_countries":      n_cty,
                "individual_count": n_ind,
                "individuals_sample": "|".join(sorted(s["individuals"])[:8]),
                "cross_cultural":   n_cty >= 3,
                "population_score": pop_score,
            })
        # Rank by population_score (lift × log(individuals+1)) — favors breadth
        out.sort(key=lambda x: x["population_score"] * (x["weighted_score"] ** 0.5),
                 reverse=True)
        ranked[ftype] = out

    return ranked


# ─────────────────────────────────────────────────────────────────────────────
# Feature registry output
# ─────────────────────────────────────────────────────────────────────────────

def build_feature_registry(ranked_by_type, contexts, max_per_type=None):
    """
    Build the redesigned feature_registry.csv DataFrame.

    Columns:
      feature_name         the lemmatized phrase
      feature_type         noun_phrase | verb_phrase | attribution |
                           attribution_place | attribution_product
      tier                 1 / 2 / 3, or empty if no NHANES alignment
      corpus_lift_score    lift of cent-freq vs. all-freq
      document_count       distinct docs containing the phrase (=total_freq)
      centenarian_freq     centenarian-focused docs containing it
      individual_count     distinct named individuals associated with it
      individuals_sample   up to 8 names (pipe-separated)
      weighted_score       sum of doc weights across all docs containing it
      population_score     lift × log(individual_count + 1)
      n_countries          distinct centenarian populations seen in
      cross_cultural       True if n_countries >= 3
      nhanes_variable      pipe-joined NHANES columns (empty if no match)
      nhanes_concept       concept_id from NHANES_FEATURE_MAP
      nhanes_category      lifestyle | biomarker | genomic
      direction            (populated later by annotate_direction)
      example_phrases      up to MAX_CONTEXTS_PER_PHRASE context snippets

    Phrases are NOT pre-classified by topic. Tier and category come from
    NHANES alignment only — discovered phrases with no NHANES mapping get
    empty tier and the user interprets them after seeing them.
    """
    rows = []

    if max_per_type is None:
        max_per_type = {
            "noun_phrase":          120,
            "verb_phrase":          80,
            "attribution":          120,
            "attribution_place":    60,
            "attribution_product":  60,
        }

    for ftype, ranked in ranked_by_type.items():
        cap = max_per_type.get(ftype, 100)
        for d in ranked[:cap]:
            phrase = d["phrase"]
            concept, nhanes_vars, tier, category = match_nhanes(phrase)
            ctxs = contexts.get(phrase, [])[:MAX_CONTEXTS_PER_PHRASE]
            rows.append({
                "feature_name":       phrase,
                "feature_type":       ftype,
                "tier":               tier if tier is not None else "",
                "corpus_lift_score":  d["lift"],
                "document_count":     d["freq_all"],
                "centenarian_freq":   d["freq_cent"],
                "individual_count":   d["individual_count"],
                "individuals_sample": d["individuals_sample"],
                "weighted_score":     d["weighted_score"],
                "population_score":   d["population_score"],
                "n_countries":        d["n_countries"],
                "cross_cultural":     d["cross_cultural"],
                "nhanes_variable":    nhanes_vars,
                "nhanes_concept":     concept,
                "nhanes_category":    category,
                "direction":          "",
                "example_phrases":    " || ".join(ctxs),
            })

    reg_df = pd.DataFrame(rows)

    # Sort: NHANES-mapped first (within mapped: by tier asc, then by population_score desc),
    # then unmapped by population_score × weighted_score.
    reg_df["_has_nhanes"] = reg_df["nhanes_variable"].astype(bool)
    reg_df["_tier_sort"]  = reg_df["tier"].apply(
        lambda v: int(v) if str(v).strip() != "" else 99
    )
    reg_df = reg_df.sort_values(
        ["_has_nhanes", "_tier_sort", "population_score", "weighted_score"],
        ascending=[False, True, False, False],
    ).drop(columns=["_has_nhanes", "_tier_sort"]).reset_index(drop=True)

    return reg_df


# ─────────────────────────────────────────────────────────────────────────────
# Direction of association
# ─────────────────────────────────────────────────────────────────────────────

_DIR_HIGH  = re.compile(r"\b(high|elevated|increased?|raised?|greater|higher|excessive|hyper)\b", re.I)
_DIR_LOW   = re.compile(r"\b(low|reduced?|decreased?|less|lower|deficient|deficiency|hypo|under|lack of)\b", re.I)
_DIR_NEVER = re.compile(r"\b(never|no|without|non[- ]?|abstain|free of|absence of)\b", re.I)
_DIR_MOD   = re.compile(r"\b(moderate|balanced|adequate|controlled|managed|optimal|normal|stable)\b", re.I)


def _dominant_direction(text_window):
    """Score a context window for direction tokens and return the strongest."""
    counts = {
        "high":      len(_DIR_HIGH.findall(text_window)),
        "low":       len(_DIR_LOW.findall(text_window)),
        "never":     len(_DIR_NEVER.findall(text_window)),
        "moderate":  len(_DIR_MOD.findall(text_window)),
    }
    best = max(counts.items(), key=lambda kv: kv[1])
    return best[0] if best[1] > 0 else ""


def annotate_direction(reg_df, df, window_chars=80):
    """
    For each NHANES-aligned feature, scan all docs containing it for direction
    modifiers within ±window_chars of the phrase. Tally and pick the dominant
    direction. Write into reg_df['direction'].
    """
    if "nhanes_variable" not in reg_df.columns:
        return reg_df
    aligned = reg_df[reg_df["nhanes_variable"].astype(bool)]
    if aligned.empty:
        return reg_df

    texts = dict(zip(df["record_id"].tolist(), df["text"].fillna("").tolist()))
    out_directions = {}
    for _, row in aligned.iterrows():
        phrase = str(row["feature_name"])
        if not phrase or len(phrase) < 4:
            continue
        pat = re.compile(r"\b" + re.escape(phrase.split()[0]) + r"\b", re.I)
        tallies = {"high": 0, "low": 0, "never": 0, "moderate": 0}
        n_scanned = 0
        for rid, txt in texts.items():
            if not txt or phrase.split()[0].lower() not in txt.lower():
                continue
            for m in pat.finditer(txt):
                start = max(0, m.start() - window_chars)
                end   = min(len(txt), m.end() + window_chars)
                d = _dominant_direction(txt[start:end])
                if d:
                    tallies[d] += 1
                n_scanned += 1
                if n_scanned >= 300:
                    break
            if n_scanned >= 300:
                break
        total = sum(tallies.values())
        if total == 0:
            out_directions[row["feature_name"]] = ""
            continue
        best = max(tallies.items(), key=lambda kv: kv[1])
        if best[1] / total >= 0.4:
            pct = round(100 * best[1] / total)
            out_directions[row["feature_name"]] = f"{best[0]} ({pct}%)"
        else:
            out_directions[row["feature_name"]] = "mixed"

    reg_df["direction"] = reg_df.apply(
        lambda r: out_directions.get(r["feature_name"], r.get("direction", "")),
        axis=1,
    )
    return reg_df


# ─────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ─────────────────────────────────────────────────────────────────────────────

def _section(title):
    print(f"\n{'='*60}\n{title}\n{'='*60}")


def main(args):
    PROCESSED.mkdir(exist_ok=True)

    # ── Optional downloads ───────────────────────────────────────────────
    attempt_downloads(skip=args.skip_download)

    # ── Load spaCy ───────────────────────────────────────────────────────
    _section("LOADING DATA AND MODEL")
    nlp = ensure_spacy()

    # ── Load corpus + apply dedup blacklist ──────────────────────────────
    df = pd.read_csv(INPUT_CSV, low_memory=False)
    print(f"  Corpus loaded: {len(df):,} rows")
    blacklist_path = PROCESSED / "news_blacklist.txt"
    if blacklist_path.exists():
        blacklist = set(
            line.strip() for line in blacklist_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        before = len(df)
        df = df[~df["record_id"].isin(blacklist)].reset_index(drop=True)
        print(f"  Applied news_blacklist.txt — dropped {before - len(df):,} duplicates "
              f"({len(df):,} rows remain)")
    else:
        print(f"  (no news_blacklist.txt found — proceeding without dedup)")

    # ── Determine which rows to process (resume support) ─────────────────
    if args.resume and INTER_PKL.exists():
        done = pd.read_pickle(INTER_PKL)
        done_ids = set(done["record_id"])
        todo = df[~df["record_id"].isin(done_ids)].copy()
        print(f"  Resuming: {len(done_ids):,} already processed, {len(todo):,} remaining")
    else:
        done = pd.DataFrame()
        todo = df.copy()
        print(f"  Processing all {len(todo):,} rows")

    # ── NLP pass: NER + noun chunks + doc weight ─────────────────────────
    _section("PASS 1: PER-DOCUMENT NLP (NER + noun chunks)")
    print(f"  Model: {SPACY_MODEL}  |  Batch size: {BATCH_SIZE}")

    results = []
    # Boilerplate-clean news rows, then truncate over-long texts so spaCy's
    # 1M-character ceiling doesn't kill the run.
    MAX_TEXT_CHARS = 500_000
    raw_rows = list(todo.itertuples(index=False))   # for source_type lookup
    cleaned_texts = []
    n_cleaned_news = 0
    for r in raw_rows:
        rowdict = r._asdict()
        if str(rowdict.get("source_type", "")).lower() == "news":
            t = clean_news_text(str(rowdict.get("text") or ""))
            n_cleaned_news += 1
        else:
            t = str(rowdict.get("text") or "")
        cleaned_texts.append(t)
    texts = [t[:MAX_TEXT_CHARS] if len(t) > MAX_TEXT_CHARS else t for t in cleaned_texts]
    n_truncated = sum(1 for t in cleaned_texts if len(t) > MAX_TEXT_CHARS)
    print(f"  Boilerplate-filtered {n_cleaned_news:,} news rows")
    if n_truncated:
        print(f"  Truncated {n_truncated} oversized docs to {MAX_TEXT_CHARS:,} chars")
    n = len(texts)
    t0 = time.time()

    # Context capture buckets (only kept here while Pass 1 runs; pickled with
    # the checkpoint so --resume works correctly).
    if args.resume and INTER_PKL.exists():
        # When resuming, we lose pre-existing contexts because they weren't
        # persisted; that's fine — top phrases will still get plenty of new
        # examples from the remaining ~1.9k rows.
        contexts = defaultdict(list)
    else:
        contexts = defaultdict(list)

    # Stream batches through nlp.pipe
    batch_docs = nlp.pipe(texts, batch_size=BATCH_SIZE)

    for i, (doc, row_tuple) in enumerate(zip(batch_docs, raw_rows)):
        row  = row_tuple._asdict()
        text = texts[i]
        rid  = row["record_id"]

        # NER age-name (uses entity spans + age regex)
        ner_name, ner_age = ner_extract(doc, text)

        # Build the set of token indices covered by excluded entity types
        blocked_idx = _person_token_indices(doc)

        # Phrase extraction — three independent vocabularies
        noun_ph   = extract_noun_chunks(doc, blocked_idx)
        verb_ph   = extract_verb_phrases(doc, blocked_idx)
        # Attribution returns (phrase, subtype) tuples; split into 3 lists
        attrib_typed = extract_attribution_phrases(text, nlp=nlp)
        attrib_ph    = [p for p, st in attrib_typed if st == "attribution"]
        attrib_place = [p for p, st in attrib_typed if st == "attribution_place"]
        attrib_prod  = [p for p, st in attrib_typed if st == "attribution_product"]

        # Capture ±5-word contexts for each new phrase occurrence (capped)
        for chunk in doc.noun_chunks:
            if any(j in blocked_idx for j in range(chunk.start, chunk.end)):
                continue
            toks = _normalize_tokens(chunk)
            if len(toks) < 2 or len(toks) > 5:
                continue
            phrase = " ".join(toks)
            if phrase in noun_ph:
                capture_context_for_chunk(doc, chunk, contexts, phrase, rid)
        for vp in set(verb_ph):
            capture_context_for_string(text, vp, contexts, rid)
        for ap in set(attrib_ph) | set(attrib_place) | set(attrib_prod):
            capture_context_for_string(text, ap, contexts, rid)

        # Entity-count stats (kept for downstream Phase 3 features)
        entities = [(e.text, e.label_) for e in doc.ents]

        dw = compute_doc_weight(row)

        # Fall back to original subject_name if NER didn't find one — needed for
        # individual_count tracking in Pass 2.
        individual_name = ner_name or str(row.get("subject_name") or "").strip() or None

        results.append({
            "record_id":              rid,
            "nlp_subject_name_ner":   ner_name,
            "nlp_subject_age_ner":    ner_age,
            "nlp_n_persons":          sum(1 for _, l in entities if l == "PERSON"),
            "nlp_n_entities":         len(entities),
            "nlp_doc_weight":         round(dw, 4),
            "nlp_noun_phrases":       noun_ph,        # temp, removed in final output
            "nlp_verb_phrases":       verb_ph,        # temp
            "nlp_attrib_phrases":     attrib_ph,      # temp
            "nlp_attrib_place":       attrib_place,   # temp
            "nlp_attrib_product":     attrib_prod,    # temp
            "nlp_text_cleaned_len":   len(text),      # diagnostic
            "_is_centenarian":        int(row.get("is_centenarian_profile") or 0),
            "_population_country":    str(row.get("population_country") or ""),
            "_individual_name":       individual_name,
        })

        if (i + 1) % 500 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta  = (n - i - 1) / max(rate, 0.1)
            print(f"  [{i+1:,}/{n:,}]  {rate:.0f} docs/s  ETA {eta/60:.1f} min")

        if (i + 1) % SAVE_EVERY == 0:
            batch_df = pd.DataFrame(results)
            combined = pd.concat([done, batch_df], ignore_index=True) if len(done) else batch_df
            combined.to_pickle(INTER_PKL)
            print(f"  Checkpoint saved ({len(combined):,} rows)")

    # Final save of intermediate
    batch_df  = pd.DataFrame(results)
    inter_df  = pd.concat([done, batch_df], ignore_index=True) if len(done) else batch_df
    inter_df.to_pickle(INTER_PKL)
    elapsed = time.time() - t0
    print(f"\n  Pass 1 complete: {len(inter_df):,} rows in {elapsed:.1f}s  ({len(inter_df)/elapsed:.0f} docs/s)")

    # ── Corpus statistics ────────────────────────────────────────────────
    _section("PASS 2: CORPUS STATISTICS (frequency + lift, per phrase type)")

    rows_meta = [
        {
            "record_id":                  r["record_id"],
            "is_centenarian":             bool(r["_is_centenarian"]),
            "doc_weight":                 r["nlp_doc_weight"],
            "population_country":         r["_population_country"],
            "individual_name":            r.get("_individual_name") or "",
            "noun_phrases":               r.get("nlp_noun_phrases", []) or [],
            "verb_phrases":               r.get("nlp_verb_phrases", []) or [],
            "attribution_phrases":        r.get("nlp_attrib_phrases", []) or [],
            "attribution_place_phrases":  r.get("nlp_attrib_place", []) or [],
            "attribution_product_phrases":r.get("nlp_attrib_product", []) or [],
        }
        for _, r in inter_df.iterrows()
    ]

    ranked = compute_corpus_stats(rows_meta)

    n_cent = sum(1 for r in rows_meta if r["is_centenarian"])
    print(f"  Centenarian-focused docs: {n_cent:,} / {len(rows_meta):,}")
    for ftype in ("noun_phrase", "verb_phrase", "attribution",
                  "attribution_place", "attribution_product"):
        print(f"  {ftype:<22} candidates (post floor): {len(ranked[ftype]):,}")

    # Preview top 15 per type so we can SEE what the data is saying.
    for ftype in ("noun_phrase", "verb_phrase", "attribution",
                  "attribution_place", "attribution_product"):
        if not ranked[ftype]:
            continue
        print(f"\n  Top 15 {ftype}s by population_score (lift × log(individuals+1) × √ws):")
        for d in ranked[ftype][:15]:
            print(f"    {d['phrase'][:50]:<52}  cent={d['freq_cent']:>4}  "
                  f"lift={d['lift']:>5.2f}  ind={d['individual_count']:>3}  "
                  f"cty={d['n_countries']:>2}  pop_score={d['population_score']:>6.2f}")

    # ── Feature registry ─────────────────────────────────────────────────
    _section("PASS 3: FEATURE REGISTRY + MATRIX BUILD")

    reg_df = build_feature_registry(ranked, contexts)
    # Direction extraction for NHANES-aligned features
    print(f"  Computing direction-of-association for NHANES-aligned features ...")
    reg_df = annotate_direction(reg_df, df)
    reg_df.to_csv(FEAT_REG, index=False)
    print(f"  Feature registry saved: {FEAT_REG}")
    print(f"  Total features: {len(reg_df)}")
    by_type = reg_df["feature_type"].value_counts().to_dict()
    for ftype, n in by_type.items():
        print(f"    {ftype:<14} {n}")
    n_with_nhanes = (reg_df["nhanes_variable"].astype(bool)).sum()
    n_cross_cult  = reg_df["cross_cultural"].sum()
    print(f"  NHANES-aligned features: {n_with_nhanes} / {len(reg_df)}")
    print(f"  Cross-cultural replicated (>=3 countries): {n_cross_cult} / {len(reg_df)}")

    # ── Build feature matrix (column-major, set-membership) ──────────────
    # Index inter_df by record_id once so per-record lookups are O(1).
    inter_indexed = inter_df.set_index("record_id", drop=False)
    rid_order = df["record_id"].tolist()

    # Per-type {record_id: frozenset(phrases)}
    def _phrase_lookup(col):
        out = {}
        for rid, val in inter_indexed[col].items():
            out[rid] = frozenset(val or [])
        return out
    lookups = {
        "noun_phrase":          _phrase_lookup("nlp_noun_phrases"),
        "verb_phrase":          _phrase_lookup("nlp_verb_phrases"),
        "attribution":          _phrase_lookup("nlp_attrib_phrases"),
        "attribution_place":    _phrase_lookup("nlp_attrib_place"),
        "attribution_product":  _phrase_lookup("nlp_attrib_product"),
    }
    empty = frozenset()
    # Pre-fetch one ordered list of frozensets per type — list lookups are faster
    # than dict.get inside the hot loop below.
    sets_by_type = {
        ftype: [lookups[ftype].get(rid, empty) for rid in rid_order]
        for ftype in lookups
    }

    # Column name per registry row
    type_prefix = {
        "noun_phrase":          "nlp_np",
        "verb_phrase":          "nlp_vp",
        "attribution":          "nlp_at",
        "attribution_place":    "nlp_apl",
        "attribution_product":  "nlp_apr",
    }
    def _col_name(ftype, phrase, idx):
        slug = re.sub(r"[^a-z0-9]+", "_", phrase.lower()).strip("_")[:40]
        return f"{type_prefix[ftype]}_{idx:03d}_{slug}"
    reg_df = reg_df.copy()
    reg_df["matrix_column"] = [
        _col_name(ft, fn, i)
        for i, (ft, fn) in enumerate(
            zip(reg_df["feature_type"].tolist(), reg_df["feature_name"].tolist())
        )
    ]
    print(f"  Building {len(reg_df)} feature columns ...")

    # Column-major construction: one list comprehension per feature.
    matrix_cols = {}
    reg_records = list(zip(
        reg_df["feature_type"].tolist(),
        reg_df["feature_name"].tolist(),
        reg_df["matrix_column"].tolist(),
    ))
    for ft, phrase, col in reg_records:
        sets = sets_by_type[ft]
        matrix_cols[col] = [1 if phrase in s else 0 for s in sets]
    feat_matrix = pd.DataFrame(matrix_cols)

    # ── Merge NLP metadata back onto master ──────────────────────────────
    nlp_meta = inter_df[[
        "record_id", "nlp_subject_name_ner", "nlp_subject_age_ner",
        "nlp_n_persons", "nlp_n_entities", "nlp_doc_weight",
        "nlp_text_cleaned_len",
    ]].copy()

    # Per-doc flag: contains at least one cross-cultural-replicated feature
    cc_phrases = set(reg_df.loc[reg_df["cross_cultural"], "feature_name"])
    def _doc_has_cc(rid):
        for lk in lookups.values():
            if lk.get(rid, empty) & cc_phrases:
                return 1
        return 0
    nlp_meta["nlp_has_cross_cultural_feature"] = nlp_meta["record_id"].map(_doc_has_cc)

    out = df.merge(nlp_meta, on="record_id", how="left")
    out = pd.concat([out, feat_matrix], axis=1)

    # ── Incremental CSV write ────────────────────────────────────────────
    print(f"\n  Writing {OUTPUT_CSV} ...")
    chunk_size = 1000
    for i in range(0, len(out), chunk_size):
        chunk = out.iloc[i:i + chunk_size]
        write_header = (i == 0)
        chunk.to_csv(OUTPUT_CSV, mode="w" if write_header else "a",
                     header=write_header, index=False)
        if (i // chunk_size + 1) % 5 == 0:
            print(f"    Written {min(i + chunk_size, len(out)):,}/{len(out):,} rows")

    # ── Final summary ────────────────────────────────────────────────────
    _section("SUMMARY")
    print(f"  master_dataset_nlp.csv : {len(out):,} rows x {len(out.columns)} cols")
    print(f"  feature_registry.csv   : {len(reg_df)} features")
    print()
    print(f"  NER improvements:")
    nlp_names = nlp_meta["nlp_subject_name_ner"].notna().sum()
    nlp_ages  = nlp_meta["nlp_subject_age_ner"].notna().sum()
    orig_names = df["subject_name"].notna().sum() if "subject_name" in df.columns else 0
    orig_ages  = df["subject_age"].notna().sum()  if "subject_age"  in df.columns else 0
    print(f"    subject_name: original {orig_names:,} non-null → NER {nlp_names:,} non-null")
    print(f"    subject_age:  original {orig_ages:,} non-null → NER {nlp_ages:,} non-null")
    print()

    # NHANES-aligned tier breakdown
    print(f"\n  Features by tier (from NHANES alignment):")
    for tier_label in ("1", "2", "3"):
        t_feats = reg_df[reg_df["tier"].astype(str) == tier_label]
        if len(t_feats):
            print(f"    Tier {tier_label}: {len(t_feats)} features")
            for _, f in t_feats.head(5).iterrows():
                nv = f["nhanes_variable"][:60] + "..." if len(f["nhanes_variable"]) > 60 else f["nhanes_variable"]
                print(f"      {f['feature_name'][:38]:<40} "
                      f"({f['feature_type']:<11}) lift={f['corpus_lift_score']:>5.2f}  "
                      f"nhanes={nv}")
    n_no_tier = (reg_df["tier"].astype(str) == "").sum()
    print(f"    No tier (corpus-discovered, no NHANES match): {n_no_tier} features")

    print(f"\n  Top 15 features overall by lift × weighted_score:")
    top15 = reg_df.assign(_score=reg_df["corpus_lift_score"] * reg_df["weighted_score"]) \
                  .sort_values("_score", ascending=False).head(15)
    for _, f in top15.iterrows():
        print(f"    [{(f['feature_type']):<11}] {f['feature_name'][:42]:<44} "
              f"tier={f['tier'] or '-':<3} lift={f['corpus_lift_score']:>5.2f}  "
              f"ws={f['weighted_score']:>7.1f}")

    print(f"\n  Top 10 ATTRIBUTION phrases (direct centenarian voice):")
    attribs = reg_df[reg_df["feature_type"] == "attribution"].head(10)
    for _, f in attribs.iterrows():
        ex = f["example_phrases"].split(" || ")[0] if f["example_phrases"] else ""
        print(f"    {f['feature_name'][:50]:<52} cent={f['centenarian_freq']:>3}")
        if ex:
            print(f"        ex: {ex[:120]}")

    print(f"\n  Feature column prefix guide (master_dataset_nlp.csv):")
    print(f"    nlp_np_*    — discovered noun phrases")
    print(f"    nlp_vp_*    — discovered verb phrases")
    print(f"    nlp_at_*    — discovered attribution phrases (highest confidence)")
    print(f"    nlp_doc_weight  — document quality weight for Phase 3 training")
    print(f"    nlp_has_cross_cultural_feature  — doc contains any cross-cultural feature")
    print()
    print(f"  Phase 3 wiring note:")
    print(f"    Tier 1 input = registry rows where tier=1 (NHANES lifestyle questionnaire)")
    print(f"    Tier 2 input = registry rows where tier in (1,2)")
    print(f"    Tier 3 input = all registry rows")
    print(f"    Untiered (corpus-only) features = exploratory / interpretive — review")
    print(f"    feature_registry.csv before promoting any to a product tier.")

    # Clean up intermediate file
    if INTER_PKL.exists():
        INTER_PKL.unlink()
        print(f"\n  Intermediate checkpoint removed.")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 2 NLP pipeline")
    parser.add_argument("--skip-download", action="store_true",
                        help="Skip optional external downloads")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from checkpoint if previous run was interrupted")
    args = parser.parse_args()

    try:
        main(args)
    except KeyboardInterrupt:
        print("\n\nInterrupted. Re-run with --resume to continue from checkpoint.")
        sys.exit(0)
