"""
Incremental ingest: re-embed only the data files that changed since the last
run, delete vectors for files that were removed, leave everything else alone.
No index wipe, so the live assistant keeps answering throughout.

How it knows what changed: backend/ingest_state.json records a hash of every
file as of its last successful ingest. Compare, act, record. The state file is
committed, so CI runs stay incremental across machines.

Embeddings come from Pinecone's hosted multilingual-e5-large (the model the
index was built with), the same way main.py embeds queries - no torch needed.

    python ingest_incremental.py              # changed + deleted files
    python ingest_incremental.py --dry-run    # print the plan only
    python ingest_incremental.py --full       # re-upload every file (no wipe)

Env: PINECONE_API_KEY, PINECONE_INDEX_NAME (and optional PINECONE_NAMESPACE).
"""
import argparse
import hashlib
import json
import os
import sys
import time

from dotenv import load_dotenv
from pinecone import Pinecone

from chunking import iter_data_files, load_document, build_chunks, vector_metadata

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.normpath(os.path.join(HERE, "..", "data"))
STATE_PATH = os.path.join(HERE, "ingest_state.json")
EMBED_MODEL = "multilingual-e5-large"
EMBED_BATCH = 96          # Pinecone inference limit for this model
UPSERT_BATCH = 100
QUERY_TOP_K = 10000       # max matches per filtered query; no file has that many chunks

load_dotenv()


def file_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_state(path, index_name):
    """The state belongs to ONE index. If it was written for a different index
    (say a test index), its hashes mean nothing here, so start from scratch
    rather than skipping files the target index has never seen."""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
        if state.get("index") == index_name:
            return state
        print(f"state file was for index {state.get('index')!r}, not {index_name!r}; ignoring it")
    return {"index": index_name, "files": {}}


def save_state(state, path):
    state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(state, f, indent=1, sort_keys=True)
        f.write("\n")


def embed_passages(pc, texts):
    out = []
    for i in range(0, len(texts), EMBED_BATCH):
        resp = pc.inference.embed(model=EMBED_MODEL, inputs=texts[i:i + EMBED_BATCH],
                                  parameters={"input_type": "passage", "truncate": "END"})
        data = getattr(resp, "data", None) or list(resp)
        for item in data:
            v = getattr(item, "values", None)
            out.append(list(v if v is not None else item["values"]))
    return out


def ids_for_path(index, rel_path, dim, namespace):
    """Vector IDs currently stored for a file. Serverless indexes can't delete
    by metadata filter, so we look the IDs up with a filtered query first.
    Older vectors were written on Windows with backslash paths; match both."""
    variants = [rel_path, rel_path.replace("/", "\\")]
    resp = index.query(vector=[0.01] * dim, top_k=QUERY_TOP_K, include_values=False,
                       include_metadata=False, namespace=namespace,
                       filter={"path": {"$in": variants}})
    matches = resp.get("matches") if isinstance(resp, dict) else getattr(resp, "matches", [])
    return [m["id"] if isinstance(m, dict) else m.id for m in (matches or [])]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--full", action="store_true", help="treat every file as changed")
    ap.add_argument("--state", default=STATE_PATH,
                    help="state file (default backend/ingest_state.json; use another for a test index)")
    args = ap.parse_args(argv)

    index_name = os.getenv("PINECONE_INDEX_NAME")
    namespace = os.getenv("PINECONE_NAMESPACE", "")

    state = load_state(args.state, index_name)
    known = state.setdefault("files", {})

    docs = {}
    for fp in iter_data_files(DATA_DIR):
        loaded = load_document(fp, DATA_DIR)
        if loaded:
            rel, text, meta = loaded
            docs[rel] = (text, meta)
    hashes = {rel: file_hash(text) for rel, (text, _) in docs.items()}
    changed = [rel for rel, h in hashes.items() if args.full or known.get(rel) != h]
    deleted = [rel for rel in known if rel not in docs]
    print(f"{len(docs)} indexable files | {len(changed)} to (re)ingest | {len(deleted)} to delete")
    if args.dry_run:
        for rel in changed[:50]:
            print("  ingest:", rel, "(new)" if rel not in known else "")
        if len(changed) > 50:
            print(f"  ... and {len(changed) - 50} more")
        for rel in deleted:
            print("  delete:", rel)
        return 0
    if not changed and not deleted:
        return 0
    if not index_name or not os.getenv("PINECONE_API_KEY"):
        sys.exit("Set PINECONE_API_KEY and PINECONE_INDEX_NAME.")

    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index(index_name)
    stats = index.describe_index_stats()
    dim = int(stats["dimension"] if isinstance(stats, dict) else stats.dimension)

    done = failed = 0
    for n, rel in enumerate(changed, 1):
        text, meta = docs[rel]
        chunks = build_chunks(rel, text, meta)
        try:
            vectors = embed_passages(pc, [c for _, c, _ in chunks])
            old_ids = ids_for_path(index, rel, dim, namespace)
            new_ids = {vid for vid, _, _ in chunks}
            stale = [i for i in old_ids if i not in new_ids]
            if stale:
                index.delete(ids=stale, namespace=namespace)
            payload = [{"id": vid, "values": vec, "metadata": vector_metadata(c, md)}
                       for (vid, c, md), vec in zip(chunks, vectors)]
            for i in range(0, len(payload), UPSERT_BATCH):
                index.upsert(vectors=payload[i:i + UPSERT_BATCH], namespace=namespace)
            known[rel] = hashes[rel]
            done += 1
            print(f"[{n}/{len(changed)}] {rel}: {len(chunks)} chunks (+{len(payload)} / -{len(stale)})")
        except Exception as e:
            failed += 1
            print(f"[{n}/{len(changed)}] {rel}: FAILED {type(e).__name__}: {e}")
        if n % 10 == 0:
            save_state(state, args.state)   # keep progress if the run dies halfway

    for rel in deleted:
        try:
            ids = ids_for_path(index, rel, dim, namespace)
            if ids:
                index.delete(ids=ids, namespace=namespace)
            known.pop(rel, None)
            print(f"deleted {rel}: {len(ids)} vectors")
        except Exception as e:
            failed += 1
            print(f"delete {rel}: FAILED {type(e).__name__}: {e}")

    save_state(state, args.state)
    total = index.describe_index_stats()
    total = total["total_vector_count"] if isinstance(total, dict) else total.total_vector_count
    print(f"\nDone: {done} files ingested, {len(deleted)} removed, {failed} failed. "
          f"Vectors in index: {total}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
