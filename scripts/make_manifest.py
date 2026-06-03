"""Checksum manifest for the bundled model artifacts (reproducibility + deterministic-artifact check).

The deployable package ships its model YAMLs as data. This records their SHA-256 so a build can prove
the artifacts are exactly the reviewed ones; editing a model without regenerating the manifest fails
`--check` (intended: forces a version bump + manifest refresh).

  python scripts/make_manifest.py          # write centenarian_phenotype/models/MANIFEST.sha256
  python scripts/make_manifest.py --check   # verify (exit 1 on mismatch) — run in CI

Large/restricted/gitignored data under data/ is intentionally NOT manifested here (it is not part of
the distributed package); regenerate it via the documented pipeline (see README "Reproducibility").
"""
from __future__ import annotations

import hashlib
import os
import sys

MODELS_DIR = os.path.join("centenarian_phenotype", "models")
MANIFEST = os.path.join(MODELS_DIR, "MANIFEST.sha256")


def _hash(path):
    # Normalize CRLF->LF so the digest is identical regardless of git autocrlf / platform.
    with open(path, "rb") as f:
        data = f.read().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def compute():
    rows = []
    for name in sorted(os.listdir(MODELS_DIR)):
        if name.endswith(".yaml"):
            rows.append((name, _hash(os.path.join(MODELS_DIR, name))))
    return rows


def main():
    rows = compute()
    body = "".join(f"{digest}  {name}\n" for name, digest in rows)
    if "--check" in sys.argv:
        if not os.path.exists(MANIFEST):
            sys.exit(f"missing {MANIFEST}; run: python scripts/make_manifest.py")
        current = open(MANIFEST, encoding="utf-8").read()
        if current != body:
            sys.exit("model artifacts changed but MANIFEST.sha256 is stale — "
                     "regenerate with: python scripts/make_manifest.py (and bump the model version)")
        print(f"manifest OK ({len(rows)} artifacts)")
    else:
        with open(MANIFEST, "w", encoding="utf-8") as f:
            f.write(body)
        print(f"wrote {MANIFEST} ({len(rows)} artifacts)")


if __name__ == "__main__":
    main()
