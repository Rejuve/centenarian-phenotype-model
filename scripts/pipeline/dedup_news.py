"""
Corpus-wide near-duplicate clustering on news rows.

Strategy:
  1. Compute 7-word shingles for every news article.
  2. Bucket candidate pairs by:
       a. first 4 alphanumeric title tokens (lowercased)
       b. hash of first 80 alphanumeric body chars (lede fingerprint)
     Two articles only become a candidate pair if they share at least one bucket key.
  3. For each candidate pair, compute containment of the smaller shingle set in the
     larger: |S_small & S_big| / |S_small|.  If >= 0.6 -> union them.
  4. Keep one representative per cluster (the lowest record_id), blacklist the rest.

Output:
  data/processed/news_blacklist.txt          one record_id per line (to skip in NLP)
  data/processed/news_dedup_report.csv       cluster_id, n_members, representative, members
"""
import re
import time
from collections import defaultdict
from pathlib import Path
import pandas as pd

PROC = Path("data/processed")
RAW  = PROC / "master_dataset.csv"
BL   = PROC / "news_blacklist.txt"
REPORT = PROC / "news_dedup_report.csv"

SHINGLE_K           = 7
CONTAINMENT_FLOOR   = 0.6
TITLE_BUCKET_TOKENS = 4
LEDE_BUCKET_CHARS   = 80


def shingles(text, k=SHINGLE_K):
    words = re.findall(r"[a-z]+", text.lower())
    if len(words) < k:
        return frozenset()
    return frozenset(" ".join(words[i:i+k]) for i in range(len(words) - k + 1))


def title_bucket_key(title):
    toks = re.findall(r"[a-z]+", (title or "").lower())
    return " ".join(toks[:TITLE_BUCKET_TOKENS]) if len(toks) >= TITLE_BUCKET_TOKENS else None


def lede_bucket_key(text):
    body = re.sub(r"[^a-z]+", "", (text or "").lower())
    return body[:LEDE_BUCKET_CHARS] if len(body) >= LEDE_BUCKET_CHARS else None


def main():
    t0 = time.time()
    print("Loading master_dataset.csv ...")
    df = pd.read_csv(RAW, low_memory=False)
    news = df[df["source_type"] == "news"].copy()
    print(f"  News rows: {len(news):,}")

    print("\nBuilding 7-word shingles ...")
    rids   = news["record_id"].tolist()
    titles = news["title"].fillna("").tolist()
    texts  = news["text"].fillna("").tolist()

    sh = {}
    for rid, txt in zip(rids, texts):
        sh[rid] = shingles(txt)
    nonempty = sum(1 for s in sh.values() if s)
    avg_len  = sum(len(s) for s in sh.values()) / max(nonempty, 1)
    print(f"  Built shingles for {nonempty:,}/{len(rids):,} docs (avg {avg_len:.0f} shingles)")

    print("\nBucketing candidate pairs ...")
    title_buckets = defaultdict(list)
    lede_buckets  = defaultdict(list)
    for rid, ttl, txt in zip(rids, titles, texts):
        if not sh[rid]:
            continue
        tk = title_bucket_key(ttl)
        if tk:
            title_buckets[tk].append(rid)
        lk = lede_bucket_key(txt)
        if lk:
            lede_buckets[lk].append(rid)
    big_title = sum(1 for v in title_buckets.values() if len(v) > 1)
    big_lede  = sum(1 for v in lede_buckets.values()  if len(v) > 1)
    print(f"  Title buckets with 2+ members: {big_title:,}")
    print(f"  Lede  buckets with 2+ members: {big_lede:,}")

    # Generate candidate pairs (set of frozenset({a,b}) to dedupe)
    candidate_pairs = set()
    for buckets in (title_buckets, lede_buckets):
        for members in buckets.values():
            if len(members) < 2:
                continue
            members.sort()
            for i, a in enumerate(members):
                for b in members[i+1:]:
                    candidate_pairs.add((a, b) if a < b else (b, a))
    print(f"  Candidate pairs to check: {len(candidate_pairs):,}")

    # Union-find
    parent = {rid: rid for rid in rids}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    print("\nChecking pairs for containment >= {:.0%} ...".format(CONTAINMENT_FLOOR))
    n_checked = 0
    n_merged  = 0
    t_check   = time.time()
    for a, b in candidate_pairs:
        n_checked += 1
        if n_checked % 50000 == 0:
            print(f"  [{n_checked:,}/{len(candidate_pairs):,}]  merged so far: {n_merged:,}")
        sa, sb = sh[a], sh[b]
        if not sa or not sb:
            continue
        if find(a) == find(b):
            continue  # already in same cluster
        # Containment of smaller in larger
        if len(sa) <= len(sb):
            small, big = sa, sb
        else:
            small, big = sb, sa
        # Short-circuit on size disparity
        if len(small) / len(big) < 0.3:
            # Even perfect containment is unlikely to indicate same-article syndication
            pass  # still check — could be near-dupe with extra boilerplate
        inter = small & big
        cont  = len(inter) / max(len(small), 1)
        if cont >= CONTAINMENT_FLOOR:
            union(a, b)
            n_merged += 1
    print(f"  Pair-check done in {time.time()-t_check:.0f}s")

    # Group by cluster root
    clusters = defaultdict(list)
    for rid in rids:
        if sh.get(rid):
            clusters[find(rid)].append(rid)

    # Stats and outputs
    cluster_list = sorted(clusters.values(), key=len, reverse=True)
    multi = [c for c in cluster_list if len(c) > 1]
    print(f"\nClusters total: {len(cluster_list):,}")
    print(f"  Singletons:        {len(cluster_list) - len(multi):,}")
    print(f"  Clusters of 2+:    {len(multi):,}")
    print(f"  Largest cluster:   {len(cluster_list[0])} members")
    blacklist = []
    rows = []
    for cid, members in enumerate(multi):
        members_sorted = sorted(members)
        rep = members_sorted[0]
        dups = members_sorted[1:]
        blacklist.extend(dups)
        rows.append({
            "cluster_id": cid,
            "n_members":  len(members_sorted),
            "representative": rep,
            "members":    "|".join(members_sorted),
        })

    BL.write_text("\n".join(blacklist) + ("\n" if blacklist else ""), encoding="utf-8")
    pd.DataFrame(rows).to_csv(REPORT, index=False)
    print(f"\nBlacklist written: {BL}  ({len(blacklist):,} entries to skip)")
    print(f"Dedup report:      {REPORT}")
    print(f"  Top 10 clusters by size:")
    for r in rows[:10]:
        sample_titles = []
        for m in r["members"].split("|")[:2]:
            t = news.loc[news["record_id"] == m, "title"].iloc[0] if (news["record_id"] == m).any() else ""
            sample_titles.append(str(t)[:60])
        print(f"    cluster {r['cluster_id']:>3}: {r['n_members']:>3} members, rep={r['representative']}, sample title='{sample_titles[0]}'")

    print(f"\nTotal wall time: {time.time()-t0:.0f}s")
    print(f"Effective dedup: keep {len(rids) - len(blacklist):,} of {len(rids):,} news rows "
          f"({100*(len(rids)-len(blacklist))/len(rids):.1f}%)")


if __name__ == "__main__":
    main()
