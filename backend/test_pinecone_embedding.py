"""
Sanity check: confirm Pinecone's hosted multilingual-e5-large produces query
embeddings compatible with the vectors already in your index.

Run it BEFORE deploying, from the backend/ folder with your .env in place:

    python test_pinecone_embedding.py

It embeds a few known questions via Pinecone Inference, queries your existing
index directly, and prints the top source files. If the right documents come
back (e.g. a Holmes question surfaces the Holmes event file), the hosted
embedding lines up with your index and you're safe to deploy. If results look
random/empty, stop — the embeddings don't match and we need to look closer.
"""
import os
from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(os.getenv("PINECONE_INDEX_NAME"))
namespace = os.getenv("PINECONE_NAMESPACE") or ""

QUESTIONS = [
    "When is Holmes is Your Home?",
    "Who teaches COP 3003 in Fall 2026?",
    "How many credits is COP 1500?",
]


def embed_query(text):
    resp = pc.inference.embed(
        model="multilingual-e5-large",
        inputs=[text],
        parameters={"input_type": "query", "truncate": "END"},
    )
    data = getattr(resp, "data", None) or list(resp)
    item = data[0]
    return list(getattr(item, "values", None) or item["values"])


def source_of(match):
    md = match.get("metadata", {}) or {}
    return md.get("source") or md.get("file_name") or md.get("path") or "?"


print(f"index namespace: {namespace!r}\n")
for q in QUESTIONS:
    vec = embed_query(q)
    res = index.query(vector=vec, top_k=3, include_metadata=True,
                      namespace=namespace)
    matches = res.get("matches", []) if isinstance(res, dict) else res.matches
    print(f"Q: {q}")
    print(f"   embedding dim: {len(vec)}")
    for m in matches:
        m = m if isinstance(m, dict) else m.to_dict()
        print(f"   {m.get('score', 0):.4f}  {source_of(m)}")
    print()

print("If the sources above are relevant to each question, the hosted "
      "embedding matches your index. You're clear to deploy.")
