"""
Full rebuild of the Pinecone index from data/.

Loading, classification and chunking live in chunking.py and are shared with
ingest_incremental.py, so a full rebuild and an incremental update produce
identical chunks, metadata and vector IDs. Use this when you want a clean
index (it WIPES the index first); use ingest_incremental.py for day-to-day
updates of a few changed files.

Embeds locally with the HuggingFace multilingual-e5-large model (needs torch);
ingest_incremental.py uses Pinecone's hosted copy of the same model instead.
"""
import os

from tqdm import tqdm
from llama_index.core import Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from pinecone import Pinecone
from dotenv import load_dotenv

from chunking import iter_data_files, load_document, build_chunks, vector_metadata

load_dotenv()

print("=" * 60)
print("FGCU RAG Ingestion Pipeline")
print("=" * 60)

HERE = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.normpath(os.path.join(HERE, "..", "data"))

# ── Embedding model ────────────────────────────────────────
print("\n[1/5] Loading embedding model...")
Settings.embed_model = HuggingFaceEmbedding(
    model_name="intfloat/multilingual-e5-large",
    trust_remote_code=True,
    # e5 is trained with asymmetric prefixes: queries get "query: ", documents
    # get "passage: ". get_text_embedding_batch() below embeds passages, so the
    # "passage: " prefix is applied here. MUST match main.py's query side.
    query_instruction="query: ",
    text_instruction="passage: ",
)
Settings.chunk_size = 400
Settings.chunk_overlap = 50
print("      Done.")

# ── Load documents ─────────────────────────────────────────
print(f"\n[2/5] Loading documents from {data_dir} ...")
documents = []
skipped_short = 0
all_files = list(iter_data_files(data_dir))
for filepath in tqdm(all_files, desc="      Reading", unit="file"):
    try:
        loaded = load_document(filepath, data_dir)
    except Exception as e:
        tqdm.write(f"      Error: {filepath} — {e}")
        continue
    if loaded is None:
        skipped_short += 1
        continue
    documents.append(loaded)
print(f"      Loaded: {len(documents)} | Skipped (too short): {skipped_short}")

if not documents:
    print("ERROR: No documents found. Check the data folder.")
    raise SystemExit(1)

# ── Split into chunks (header-aware) ───────────────────────
print("\n[3/5] Splitting into chunks (header-aware)...")
chunks = []   # (vector_id, text, metadata)
for rel_path, text, meta in tqdm(documents, desc="      Chunking", unit="doc"):
    chunks.extend(build_chunks(rel_path, text, meta))
print(f"      Total chunks: {len(chunks)}")

# ── Generate embeddings ────────────────────────────────────
print("\n[4/5] Generating embeddings...")
embed_model = Settings.embed_model
texts = [c for _, c, _ in chunks]
embeddings = []
batch_size = 32
for i in tqdm(range(0, len(texts), batch_size),
              desc="      Embedding", unit="batch",
              bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} batches [{elapsed}<{remaining}]"):
    embeddings.extend(embed_model.get_text_embedding_batch(texts[i:i + batch_size]))
print(f"      Generated {len(embeddings)} embeddings.")

# ── Upload to Pinecone ─────────────────────────────────────
print("\n[5/5] Uploading to Pinecone...")
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
pinecone_index = pc.Index(os.getenv("PINECONE_INDEX_NAME"))

# Wipe the index before repopulating so vectors for files that no longer
# exist don't linger. Comment this out ONLY if you intend to ADD to an
# existing index rather than rebuild it from scratch.
print("      Clearing existing vectors (full rebuild)...")
try:
    pinecone_index.delete(delete_all=True)
except Exception as e:
    # A brand-new/empty index can raise "namespace not found" — safe to ignore.
    print(f"      (nothing to clear: {e})")

for i in tqdm(range(0, len(chunks), 100),
              desc="      Uploading", unit="batch",
              bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} batches [{elapsed}<{remaining}]"):
    batch = chunks[i:i + 100]
    vectors = [{"id": vid, "values": embeddings[i + j], "metadata": vector_metadata(text, md)}
               for j, (vid, text, md) in enumerate(batch)]
    pinecone_index.upsert(vectors=vectors)

stats = pinecone_index.describe_index_stats()
total_vectors = stats.get("total_vector_count", "unknown")

print("\n" + "=" * 60)
print("Ingestion complete!")
print(f"  Documents processed : {len(documents)}")
print(f"  Chunks created      : {len(chunks)}")
print(f"  Vectors in Pinecone : {total_vectors}")
print("=" * 60)
