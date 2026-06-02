"""Attempt to extract control-group prevalence (%) for silver corpus_control
traits from academic_papers.csv abstracts (no full_text exists). Flag traits
where a control-group % materializes; others -> silver_pending."""
import re, pandas as pd
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","pipeline"))
import step_c_lock_tier1 as C

lock=pd.read_csv("data/processed/tier1_features_locked.csv")
silver=lock[(lock["corroboration_tier"]=="silver") & (lock["baseline_source"]=="corpus_control")]
ap=pd.read_csv("data/raw/academic_papers.csv")
text=(ap["title"].fillna("")+". "+ap["abstract"].fillna("")).str.lower()
longm=text.str.contains(C.LONGEVITY)
lt=text[longm]
control=re.compile(r"control|comparison group|non[-\s]?centenarian", re.I)
pct_near_ctrl=re.compile(r"(?:control[s]?[^.]{0,60}?(\d{1,2}(?:\.\d)?)\s?%)|(\d{1,2}(?:\.\d)?)\s?%[^.]{0,40}?control", re.I)

rows=[]
for _,r in silver.iterrows():
    trait=r["trait"]
    syns=C.SYNONYMS.get(trait) or [w for w in re.split(r"[/()\s]+",trait) if len(w)>2] or [trait]
    treg=C.build_trait_regex(syns)
    cand=lt[lt.str.contains(treg) & lt.str.contains(control)]
    found=[]
    for t in cand.tolist():
        for w in [t[max(0,m.start()-120):m.end()+40] for m in treg.finditer(t)]:
            mm=pct_near_ctrl.search(w)
            if mm:
                found.append(mm.group(1) or mm.group(2))
    rows.append(dict(trait=trait, n_control_papers=int(cand.shape[0]),
                     control_pct_found=len(found),
                     example_pct="|".join(found[:3]),
                     status="materialized" if found else "silver_pending"))
out=pd.DataFrame(rows).sort_values("control_pct_found",ascending=False)
out.to_csv("data/processed/step_d_silver_control_attempt.csv",index=False)
print(f"silver corpus_control traits attempted: {len(out)}")
print("  materialized (control % extractable from abstract):", int((out['status']=='materialized').sum()))
print("  silver_pending:", int((out['status']=='silver_pending').sum()))
print(out[out['status']=='materialized'][['trait','n_control_papers','control_pct_found','example_pct']].head(15).to_string(index=False))
