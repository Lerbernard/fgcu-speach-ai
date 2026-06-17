"""
Debug tool for the FGCU RAG router.
Shows, for any question:
  1. What route_query() decided (doc_types, program, term)
  2. The metadata filter that gets sent to Pinecone
  3. The actual chunks retrieved — source file, doc_type, and score
  4. The final answer

Run:  python debug_rag.py
Then type questions. Type 'exit' to quit.
"""
from llama_index.core import VectorStoreIndex, Settings
from llama_index.core.vector_stores import MetadataFilters, MetadataFilter, FilterOperator
from llama_index.vector_stores.pinecone import PineconeVectorStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.groq import Groq
from pinecone import Pinecone
from dotenv import load_dotenv
import os
import re

load_dotenv()

print("Loading embedding model...")
Settings.embed_model = HuggingFaceEmbedding(
    model_name="intfloat/multilingual-e5-large",
    trust_remote_code=True
)
Settings.chunk_size = 400
Settings.chunk_overlap = 50
Settings.llm = Groq(model="llama-3.3-70b-versatile", api_key=os.getenv("GROQ_API_KEY"))

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
pinecone_index = pc.Index(os.getenv("PINECONE_INDEX_NAME"))
vector_store = PineconeVectorStore(pinecone_index=pinecone_index)
index = VectorStoreIndex.from_vector_store(vector_store)
print("Ready.\n")


# ---- paste the SAME router from main.py here ----
def detect_program(q):
    if "software engineering" in q or "ingeniería de software" in q or "génie logiciel" in q:
        return "software_engineering"
    if "computer science" in q or " cs " in q or "in cs" in q or \
       "ciencias de la computación" in q or "informática" in q or "informatique" in q:
        return "computer_science"
    if "civil" in q:
        return "civil_engineering"
    if "bioengineering" in q or "biomedical" in q or "bioingeniería" in q or "bio-ingénierie" in q:
        return "bioengineering"
    if "construction" in q or "construcción" in q:
        return "construction_management"
    if "environmental" in q or "ambiental" in q or "environnement" in q:
        return "environmental_engineering"
    return None


def detect_term(q):
    season = None
    if any(w in q for w in ["fall", "otoño", "automne"]):
        season = "fall"
    elif any(w in q for w in ["spring", "primavera", "printemps"]):
        season = "spring"
    elif any(w in q for w in ["summer", "verano", "été", "ete"]):
        season = "summer"
    year = re.search(r'(20\d{2})', q)
    if season and year:
        return f"{season} {year.group(1)}"
    return None


def route_query(question):
    q = question.lower()
    has_course_code = bool(re.search(r'[a-z]{2,4}\s*\d{3,4}', q))

    schedule_words = any(w in q for w in [
        "teach", "who teaches", "what time", "when does", "meet", "instructor",
        "crn", "schedule", "offered in",
        "enseña", "quién enseña", "qué hora", "horario", "imparte",
        "enseigne", "qui enseigne", "quelle heure", "horaire"])
    description_words = any(w in q for w in [
        "about", "cover", "describe", "description", "what is", "what's", "topics", "learn in",
        "se trata", "cubre", "describe", "descripción", "qué es", "de qué",
        "à propos", "couvre", "décrire", "qu'est-ce", "porte sur"])
    curriculum_words = any(w in q for w in [
        "junior year", "senior year", "sophomore", "freshman", "concentration",
        "degree map", "what classes", "what courses", "requirements", "curriculum",
        "combined", "bs/ms", "do i need", "year in",
        "tercer año", "cuarto año", "segundo año", "primer año", "concentración",
        "qué clases", "qué cursos", "requisitos", "plan de estudios", "necesito",
        "troisième année", "quatrième année", "deuxième année", "première année",
        "quels cours", "exigences", "programme", "j'ai besoin"])
    faculty_words = any(w in q for w in [
        "professor", "faculty", "who are", "profesor", "profesores", "facultad",
        "professeur", "professeurs", "faculté"])
    rating_words = any(w in q for w in [
        "students say", "reviews", "rating", "good professor", "what do students",
        "how is", "estudiantes dicen", "reseñas", "opiniones", "buen profesor",
        "qué dicen", "étudiants disent", "avis", "bon professeur", "que disent"])
    club_words = any(w in q for w in [
        "club", "organization", "society", "organización", "sociedad",
        "organisation", "société"])
    institute_words = any(w in q for w in [
        "institute", "dendritic", "eaglecybernest", "instituto", "institut"])
    help_words = any(w in q for w in [
        "learning hub", "tutor", "tutoring", "get help", "help with my classes",
        "help with classes", "academic support", "peer mentor", "fellows",
        "ayuda con", "tutoría", "aide", "tutorat", "soutien"])
    general_words = any(w in q for w in [
        "apply", "admission", "advisor", "advising", "research",
        "aplicar", "admisión", "asesor", "investigación",
        "postuler", "admission", "conseiller", "recherche"])

    program = detect_program(q)
    term = detect_term(q)

    # print which flags fired (debug)
    print(f"  flags: course_code={has_course_code} schedule={schedule_words} "
          f"desc={description_words} help={help_words} curriculum={curriculum_words} "
          f"rating={rating_words} faculty={faculty_words} club={club_words} "
          f"institute={institute_words} general={general_words}")
    print(f"  program={program} term={term}")

    if "learning hub" in q or "learning center" in q:
        return ["learning_support"], None, None
    if has_course_code and schedule_words:
        return ["course_offering"], None, term
    if has_course_code and description_words:
        return ["course_description"], None, None
    if help_words:
        return ["learning_support"], None, None
    if rating_words:
        return ["faculty_reviews"], None, None
    if institute_words:
        return ["general"], None, None
    if curriculum_words:
        return ["degree_map"], program, None
    if club_words:
        return ["club"], None, None
    if faculty_words:
        return ["faculty", "faculty_reviews"], None, None
    if general_words:
        return ["general", "degree_map", "research"], None, None
    return None, None, None


def make_filters(doc_types, program, term):
    filter_list = []
    if doc_types:
        if len(doc_types) == 1:
            filter_list.append(MetadataFilter(key="doc_type", value=doc_types[0],
                                              operator=FilterOperator.EQ))
        else:
            filter_list.append(MetadataFilter(key="doc_type", value=doc_types,
                                              operator=FilterOperator.IN))
    if program:
        filter_list.append(MetadataFilter(key="program", value=program,
                                          operator=FilterOperator.EQ))
    if term:
        filter_list.append(MetadataFilter(key="term", value=term,
                                          operator=FilterOperator.EQ))
    if filter_list:
        return MetadataFilters(filters=filter_list, condition="and")
    return None


def debug(question):
    print("=" * 70)
    print(f"QUESTION: {question}")
    print("-" * 70)
    doc_types, program, term = route_query(question)
    print(f"  ROUTE -> doc_types={doc_types}, program={program}, term={term}")
    print("-" * 70)

    filters = make_filters(doc_types, program, term)
    if filters:
        engine = index.as_query_engine(similarity_top_k=20, filters=filters)
    else:
        engine = index.as_query_engine(similarity_top_k=20)

    # retrieve raw chunks first
    retriever = engine.retriever if hasattr(engine, "retriever") else None
    nodes = engine.retrieve(question) if hasattr(engine, "retrieve") else \
            index.as_retriever(similarity_top_k=20, filters=filters).retrieve(question)

    print(f"  RETRIEVED {len(nodes)} chunks:")
    if not nodes:
        print("  *** ZERO chunks came back. Either no file has this doc_type in")
        print("  *** Pinecone (did you re-ingest?), or the filter is too strict.")
    for i, n in enumerate(nodes[:12], 1):
        src = n.metadata.get("source", "?")
        dt = n.metadata.get("doc_type", "?")
        score = getattr(n, "score", 0) or 0
        print(f"    {i:2}. [{score:.3f}] doc_type={dt:18} source={src}")
    print("-" * 70)

    SYSTEM = ("You are a helpful FGCU engineering assistant. Answer only from the "
              "context. If the context does not contain the answer, say you are not sure.")
    response = engine.query(SYSTEM + "\n\nQuestion: " + question)
    print(f"  ANSWER: {response}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    print("Debug RAG — type a question, or 'exit' to quit.\n")
    while True:
        try:
            q = input("Debug> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q or q.lower() in ("exit", "quit"):
            break
        try:
            debug(q)
        except Exception as e:
            print(f"  ERROR: {e}\n")