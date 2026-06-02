"""Extract and categorize smoking mentions across centenarian profile articles."""
import html, re, pandas as pd

news = pd.read_csv('data/raw/news_articles.csv', low_memory=False)
prof = news[news['is_centenarian_profile'].astype(str).str.upper().isin(['TRUE','1','1.0'])]

SMOKE = re.compile(r'\b(smok\w*|cigarette\w*|cigar\b|cigars\b|pipe\b|tobacco|pack[-\s]?year)\w*', re.I)
pat = {
 'status_never': re.compile(r'never\s+smok|non[-\s]?smoker|did\s?n[o\']t\s+smoke|didnt smoke', re.I),
 'status_former': re.compile(r'(quit|gave up|stopped|ceased|former\s+smoker|used to smoke)', re.I),
 'status_current': re.compile(r'(still\s+smok|smokes?\s+(?:daily|every|a)|continues? to smoke|a[-\s]?day habit)', re.I),
 'amount_cigs': re.compile(r'(\d+)\s*(?:cigarettes?|cigs?)\s*(?:a|per)?\s*day', re.I),
 'amount_packs': re.compile(r'(\d+(?:\.\d+)?)\s*pack', re.I),
 'duration_years': re.compile(r'smok\w*\s+for\s+(\d+)\s+years|(\d+)\s+years?\s+of\s+smok', re.I),
 'cessation_quit_age': re.compile(r'(?:quit|stopped|gave up).{0,30}?(?:at|aged|age)\s+(\d+)', re.I),
 'cessation_years_since': re.compile(r'(?:quit|stopped|gave up).{0,30}?(\d+)\s+years\s+(?:ago|earlier|before)', re.I),
 'type_pipe': re.compile(r'\bpipe\b', re.I),
 'type_cigar': re.compile(r'\bcigars?\b', re.I),
 'type_occasional': re.compile(r'occasional\w*\s+(?:smok|cigar)', re.I),
}
counts = {k:0 for k in pat}
indiv = {k:set() for k in pat}
examples = {k:[] for k in pat}
n_with_smoke = 0; subjects_with_smoke=set()
for _, r in prof.iterrows():
    t = r.get('full_text'); 
    if not isinstance(t,str): continue
    t = html.unescape(t)
    subj = str(r.get('subject_name'))
    has=False
    for m in SMOKE.finditer(t):
        w = t[max(0,m.start()-90):m.end()+90]
        has=True
        for k,rx in pat.items():
            if rx.search(w):
                counts[k]+=1; indiv[k].add(subj)
                if len(examples[k])<3: examples[k].append(re.sub(r'\s+',' ',w).strip()[:160])
    if has: n_with_smoke+=1; subjects_with_smoke.add(subj)
print(f'Profile articles mentioning smoking/tobacco: {n_with_smoke} (distinct subjects ~{len(subjects_with_smoke)})\n')
print(f'{"pattern":22}{"mentions":>9}{"indiv":>7}   example')
for k in pat:
    ex = examples[k][0] if examples[k] else ''
    print(f'{k:22}{counts[k]:>9}{len(indiv[k]):>7}   {ex[:90]}')
