import os
import re
from tqdm import tqdm
from llama_index.core import Document, Settings
from llama_index.core.node_parser import SentenceSplitter
from llama_index.vector_stores.pinecone import PineconeVectorStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()

print("=" * 60)
print("FGCU RAG Ingestion Pipeline")
print("=" * 60)


def get_doc_type(path, filename):
    """Classify each document so retrieval can tell types apart."""
    f = filename.lower()
    p = path.lower()
    # Course DESCRIPTIONS (what a course covers) — check before course_offering
    if "course_descriptions" in p or "_description" in f:
        return "course_description"
    # Learning Hub / tutoring / academic support
    if "learning_support" in p or "learning_hub" in f or "service_learning" in f:
        return "learning_support"
    # Course OFFERINGS (schedule: who teaches, when)
    # Anything under the courses/ tree is a course OFFERING — both the per-course
    # files (CES_…, COP_…) and the per-subject term rollups like
    # courses_Fall_2026_CES.md. (course_descriptions was already handled above.)
    if "courses" in p:
        return "course_offering"
    if filename.startswith("programs_") or "degree_map" in f:
        return "degree_map"
    if "ratemyprofessors" in p:
        return "faculty_reviews"
    if "faculty" in p:
        return "faculty"
    if "clubs" in p:
        return "club"
    if "research" in p:
        return "research"
    # ── Page sections that previously all fell into "general" ──
    if "admissions" in p:
        return "admissions"
    if "policies_legal" in p or "ethics" in f or "stateauthorization" in f \
       or "governmentrelations" in f:
        return "policy"
    if "student_life" in p or "student-involvement" in f or "student_involvement" in f:
        return "student_life"
    if "engineering_departments" in p:
        return "department"
    if "engineering_programs" in p or "academics" in p:
        return "program"
    if "engineering_main" in p or "about_fgcu" in p:
        return "campus"
    return "general"


def get_program(path, filename):
    """Tag which degree program a file belongs to."""
    f = (filename + " " + path).lower()
    if "software-engineering" in f or "software_engineering" in f:
        return "software_engineering"
    if "computer-science" in f or "computer_science" in f or "computerscience" in f:
        return "computer_science"
    if "civil" in f:
        return "civil_engineering"
    if "bioengineering" in f:
        return "bioengineering"
    if "construction" in f:
        return "construction_management"
    if "environmental" in f:
        return "environmental_engineering"
    return "general"


def get_professor(path, filename, content=""):
    """Extract professor name for filtering.

    Faculty files are named after the professor (allen_paul.md).
    Course-offering files name their instructor inside the text on a line like
    'CDA 3104 Fall 2025 — Instructor: Allen, Paul'. We tag those with the same
    'lastname firstname' format so a question like 'what does Allen teach'
    filters to his course too, not just his bio."""
    if "faculty" in path or "ratemyprofessors" in path:
        name = filename.replace(".md", "")
        name = re.sub(r'_part\d+$', '', name)
        name = name.replace("_", " ").strip()
        if name.startswith("www ") or "facultystaff" in name:
            return ""
        return name.lower()
    # Course-offering files: pull the instructor from the content.
    m = re.search(r'Instructor:\s*([A-Za-z\'-]+),\s*([A-Za-z\'-]+)', content)
    if m:
        last, first = m.group(1).strip().lower(), m.group(2).strip().lower()
        return f"{last} {first}"
    return ""


def get_term(filename):
    """Extract term and year from course filenames like COP_1500_Fall_2025.md."""
    m = re.search(r'(Fall|Spring|Summer)_(\d{4})', filename, re.IGNORECASE)
    if m:
        return f"{m.group(1).lower()} {m.group(2)}"
    return ""


def get_course_code(filename):
    """Extract a course code like 'cop 1500' from filenames such as
    COP_1500_Fall_2025.md or COP_1500_description.md. Stored lowercase with a
    single space so the router can filter on it. Returns '' if no code."""
    m = re.match(r'([A-Za-z]{2,4})_(\d{3,4}[A-Za-z]?)', filename)
    if m:
        return f"{m.group(1).lower()} {m.group(2).lower()}"
    return ""


# ── Embedding model ────────────────────────────────────────
print("\n[1/5] Loading embedding model...")
Settings.embed_model = HuggingFaceEmbedding(
    model_name="intfloat/multilingual-e5-large",
    trust_remote_code=True
)
Settings.chunk_size = 400
Settings.chunk_overlap = 50
print("      Done.")

# ── Load documents ─────────────────────────────────────────
print("\n[2/5] Loading documents from data\\ folder...")
data_dir = "..\\data"
documents = []
skipped_short = 0
skipped_dupe  = 0

all_files = []
for root, dirs, files in os.walk(data_dir):
    dirs[:] = [d for d in dirs if not d.startswith(".")]
    for filename in files:
        if filename.endswith(".md"):
            all_files.append(os.path.join(root, filename))

for filepath in tqdm(all_files, desc="      Reading", unit="file"):
    rel_path = os.path.relpath(filepath, data_dir)
    filename = os.path.basename(filepath)

    # Skip original subject-level course files if their split subfolder exists
    subj_match = re.match(r'courses_(.+?)_([A-Z]{2,4})\.md$', filename)
    if subj_match:
        term = subj_match.group(1)
        subj = subj_match.group(2)
        split_dir = os.path.join(os.path.dirname(filepath),
                                 f"{subj}_{term}_courses")
        if os.path.isdir(split_dir):
            skipped_dupe += 1
            continue

    # Skip the merged/per-term description files if the split individual files exist
    if filename.startswith("course_descriptions_") or \
       filename == "engineering_course_descriptions.md":
        individual_dir = os.path.join(os.path.dirname(filepath), "individual")
        if os.path.isdir(individual_dir):
            skipped_dupe += 1
            continue

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read().strip()
        if len(content) < 50:
            skipped_short += 1
            continue
        documents.append(Document(
            text=content,
            metadata={
                "source":    filename,
                "path":      rel_path,
                "folder":    os.path.basename(os.path.dirname(filepath)),
                "doc_type":  get_doc_type(rel_path, filename),
                "program":   get_program(rel_path, filename),
                "professor": get_professor(rel_path, filename, content),
                "term":      get_term(filename),
                "course_code": get_course_code(filename),
            }
        ))
    except Exception as e:
        tqdm.write(f"      Error: {rel_path} — {e}")

print(f"      Loaded: {len(documents)} | Skipped (too short): {skipped_short} | Skipped (duplicates): {skipped_dupe}")

if not documents:
    print("ERROR: No documents found. Check data\\ folder.")
    exit()

# ── Split into chunks ──────────────────────────────────────
print("\n[3/5] Splitting into chunks...")
splitter = SentenceSplitter(chunk_size=400, chunk_overlap=50)
nodes = []
for doc in tqdm(documents, desc="      Chunking", unit="doc"):
    nodes.extend(splitter.get_nodes_from_documents([doc]))
print(f"      Total chunks: {len(nodes)}")

# ── Generate embeddings ────────────────────────────────────
print("\n[4/5] Generating embeddings...")
embed_model = Settings.embed_model
texts       = [node.get_content() for node in nodes]
batch_size  = 32

for i in tqdm(range(0, len(texts), batch_size),
              desc="      Embedding", unit="batch",
              bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} batches [{elapsed}<{remaining}]"):
    batch     = texts[i:i + batch_size]
    batch_emb = embed_model.get_text_embedding_batch(batch)
    for j, node in enumerate(nodes[i:i + batch_size]):
        node.embedding = batch_emb[j]

print(f"      Generated {len(nodes)} embeddings.")

# ── Upload to Pinecone ─────────────────────────────────────
print("\n[5/5] Uploading to Pinecone...")
pc             = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
pinecone_index = pc.Index(os.getenv("PINECONE_INDEX_NAME"))

for i in tqdm(range(0, len(nodes), 100),
              desc="      Uploading", unit="batch",
              bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} batches [{elapsed}<{remaining}]"):
    batch   = nodes[i:i + 100]
    vectors = [{
        "id":     node.node_id,
        "values": node.embedding,
        "metadata": {
            "text":      node.get_content()[:1000],
            "source":    node.metadata.get("source", ""),
            "path":      node.metadata.get("path", ""),
            "folder":    node.metadata.get("folder", ""),
            "doc_type":  node.metadata.get("doc_type", "general"),
            "program":   node.metadata.get("program", "general"),
            "professor": node.metadata.get("professor", ""),
            "term":      node.metadata.get("term", ""),
            "course_code": node.metadata.get("course_code", ""),
        }
    } for node in batch]
    pinecone_index.upsert(vectors=vectors)

stats         = pinecone_index.describe_index_stats()
total_vectors = stats.get("total_vector_count", "unknown")

print("\n" + "=" * 60)
print("Ingestion complete!")
print(f"  Documents processed : {len(documents)}")
print(f"  Chunks created      : {len(nodes)}")
print(f"  Vectors in Pinecone : {total_vectors}")
print("=" * 60)