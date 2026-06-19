"""
Diagnostic: what doc_type labels are actually in the LIVE Pinecone index?

This answers the recurring question "did my re-ingest actually take effect?".
The category routes (event / club / admissions / ...) only work if the vectors
in Pinecone carry those doc_type labels. If everything is still "general" (or the
new labels like "event" are missing), every filtered route silently falls back to
fuzzy search over the whole index -- which looks exactly like: named things only
get found when you pad the question with extra words, and lookups return a
near-neighbour (e.g. "Society of Women Engineers" -> "Women in STEM").

Run it with the SAME env you run the backend with (PINECONE_API_KEY,
PINECONE_INDEX_NAME). It does NOT load the embedding model, so it's fast.

    python check_index.py
"""
import os
from collections import Counter

from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()

INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
NAMESPACE = os.getenv("PINECONE_NAMESPACE", "")  # default namespace if unset

# Labels the current ingest.py can assign. The first group is the page-section
# set whose presence proves a current-labels re-ingest happened.
NEW_LABELS = ["event", "club", "admissions", "policy", "student_life",
              "department", "program", "campus", "research"]
OTHER_LABELS = ["faculty", "faculty_reviews", "course_offering",
                "course_description", "degree_map", "learning_support", "general"]
ALL_LABELS = NEW_LABELS + OTHER_LABELS


def _matches(resp):
    try:
        return resp["matches"]
    except Exception:
        return getattr(resp, "matches", []) or []


def _meta(match):
    try:
        return match["metadata"] or {}
    except Exception:
        return getattr(match, "metadata", {}) or {}


def _stat(stats, key, default):
    try:
        return stats[key]
    except Exception:
        return getattr(stats, key, default)


def main():
    if not INDEX_NAME:
        print("PINECONE_INDEX_NAME is not set. Set it (and PINECONE_API_KEY) the "
              "same way the backend does, then re-run.")
        return

    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index(INDEX_NAME)

    stats = index.describe_index_stats()
    dim = int(_stat(stats, "dimension", 1024) or 1024)
    total = _stat(stats, "total_vector_count", 0)
    print(f"Index '{INDEX_NAME}'  |  vectors: {total}  |  dim: {dim}  "
          f"|  namespace: {NAMESPACE or '(default)'}\n")

    dummy = [0.01] * dim  # vector value is irrelevant for a metadata-filter check

    print("Which doc_type labels exist in the index?")
    present = []
    for dt in ALL_LABELS:
        try:
            resp = index.query(vector=dummy, top_k=1, include_metadata=False,
                               namespace=NAMESPACE, filter={"doc_type": {"$eq": dt}})
            hit = len(_matches(resp)) > 0
        except Exception:
            hit = False
        if hit:
            present.append(dt)
        print(f"   [{'x' if hit else ' '}] {dt}")

    # Eyeball a sample of real metadata so a wrong key name is obvious too.
    print("\nSample of up to 50 vectors' doc_type (unfiltered):")
    try:
        resp = index.query(vector=dummy, top_k=50, include_metadata=True,
                           namespace=NAMESPACE)
        c = Counter(_meta(m).get("doc_type", "<no doc_type key>") for m in _matches(resp))
        if not c:
            print("   (no vectors returned -- is the index empty or the namespace wrong?)")
        for k, v in c.most_common():
            print(f"   {v:3}  {k}")
    except Exception as e:
        print("   sample query failed:", e)

    print("\n" + "=" * 70)
    if "event" in present:
        print("VERDICT: 'event' label is present -> index re-ingested with the "
              "CURRENT ingest.py. If named events still miss, it's a recall/dup "
              "issue, not labels (see notes below).")
    elif set(NEW_LABELS) & set(present):
        print("VERDICT: some page labels exist but 'event' is MISSING. You "
              "re-ingested with an OLDER ingest.py. Re-run ingest.py so the "
              "student-involvement files get the 'event' label.")
    else:
        print("VERDICT: none of the page-section labels are present. The index "
              "was NOT re-ingested with the labelled ingest.py -- every category "
              "route is falling back to fuzzy search over the whole index. "
              "Re-run ingest.py.")
    print("Note: if you re-ingest without clearing first AND ingest.py doesn't use "
          "stable IDs, you'll ADD duplicate vectors that dilute the top-20. If "
          "unsure, recreate the index before re-ingesting.")


if __name__ == "__main__":
    main()