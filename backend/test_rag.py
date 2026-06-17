# -*- coding: utf-8 -*-
"""
test_rag.py — End-to-end multilingual test for the FGCU RAG assistant.

Asks one question in each of the 21 supported languages, runs it through the
SAME smart router used by main.py (imported keyword sets from keywords.py),
and checks that:
  1. the router picked a sensible doc_type
  2. chunks came back from Pinecone
  3. the model produced a non-empty answer

Run:  python test_rag.py
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
import sys
import keywords as kw

# Windows consoles default to cp1252, which cannot print non-Latin scripts
# (Chinese, Arabic, Hindi, etc.). Force stdout/stderr to UTF-8 so the test can
# print answers in every language without a UnicodeEncodeError.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

load_dotenv()

print("Loading embedding model...")
Settings.embed_model = HuggingFaceEmbedding(
    model_name="intfloat/multilingual-e5-large",
    trust_remote_code=True
)
Settings.chunk_size = 400
Settings.chunk_overlap = 50
Settings.llm = Groq(model="llama-3.3-70b-versatile", api_key=os.getenv("GROQ_API_KEY2"))

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
pinecone_index = pc.Index(os.getenv("PINECONE_INDEX_NAME"))
vector_store = PineconeVectorStore(pinecone_index=pinecone_index)
index = VectorStoreIndex.from_vector_store(vector_store)
print("Ready.\n")

SYSTEM_PROMPT = (
    "You are a friendly assistant for the U.A. Whitaker College of Engineering "
    "at FGCU. Answer only using the provided context. "
    "You are fully multilingual: detect the language of the student's question and "
    "write your ENTIRE answer in that exact language. Never refuse because of the "
    "language and never say you can only answer in English. Translate EVERYTHING "
    "into the student's language, INCLUDING course names (for example, translate "
    "'Intro to Computer Science' into the student's language). The only things you "
    "keep unchanged are the course codes (like COP 1500, EGN 3331C) and proper names "
    "of people and places, because those are official identifiers; put the translated "
    "course name first, then the code in parentheses. Do not apologize for or comment "
    "on the language. If the context lacks the answer, say you are not sure, in the "
    "student's language."
)


# ── Router (mirrors main.py, keywords from keywords.py) ────
def detect_program(q):
    for program, lang_words in kw.PROGRAM_WORDS.items():
        for word in kw.flatten(lang_words):
            if word in q:
                return program
    return None


def detect_term(q):
    season = None
    for season_name, lang_words in kw.SEASON_WORDS.items():
        if any(w in q for w in kw.flatten(lang_words)):
            season = season_name
            break
    year = re.search(r'(20\d{2})', q)
    if season and year:
        return f"{season} {year.group(1)}"
    return None


def route_query(question):
    q = question.lower()
    has_course_code = bool(re.search(r'[a-z]{2,4}\s*\d{3,4}', q))

    schedule_words    = any(w in q for w in kw.ALL_SCHEDULE)
    description_words = any(w in q for w in kw.ALL_DESCRIPTION)
    curriculum_words  = any(w in q for w in kw.ALL_CURRICULUM)
    faculty_words     = any(w in q for w in kw.ALL_FACULTY)
    rating_words      = any(w in q for w in kw.ALL_RATING)
    club_words        = any(w in q for w in kw.ALL_CLUB)
    institute_words   = any(w in q for w in kw.ALL_INSTITUTE)
    help_words        = any(w in q for w in kw.ALL_HELP)
    general_words     = any(w in q for w in kw.ALL_GENERAL)
    hub_override      = any(w in q for w in kw.ALL_HUB_OVERRIDE)

    program = detect_program(q)
    term = detect_term(q)

    if hub_override:
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


def extract_course_code(question):
    m = re.search(r'([a-zA-Z]{2,4})\s*(\d{3,4}[a-zA-Z]?)', question)
    if m:
        return f"{m.group(1).lower()} {m.group(2).lower()}"
    return None


def make_engine(doc_types, program, term, course_code=None):
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
    if course_code:
        filter_list.append(MetadataFilter(key="course_code", value=course_code,
                                          operator=FilterOperator.EQ))
    if filter_list:
        filters = MetadataFilters(filters=filter_list, condition="and")
        return index.as_query_engine(similarity_top_k=20, filters=filters)
    return index.as_query_engine(similarity_top_k=20)


# ── One test question per supported language, each hitting a DIFFERENT
#    part of the dataset so the whole index gets exercised. ──────────
# Format: (language, question, expected_doc_type_substring)
# expected is used as a soft check — the route should include it.
TESTS = [
    # --- Learning support ---
    ("English",    "What classes does the Learning Hub help with?", "learning_support"),
    # --- Course schedule (course_offering) ---
    ("Spanish",    "¿Quién enseña COP 1500 en otoño 2025?", "course_offering"),
    # --- Course description ---
    ("Portuguese", "Sobre o que é o COP 3003?", "course_description"),
    # --- Curriculum / degree map (with program) ---
    ("French",     "De quels cours ai-je besoin en troisième année de génie logiciel ?", "degree_map"),
    # --- Faculty ---
    ("German",     "Wer sind die Professoren in der Informatik?", "faculty"),
    # --- Faculty reviews ---
    ("Italian",    "Cosa dicono gli studenti del professor Buckley?", "faculty_reviews"),
    # --- Clubs ---
    ("Russian",    "Какие инженерные клубы есть в университете?", "club"),
    # --- General / admissions ---
    ("Ukrainian",  "Як подати заявку на вступ до FGCU?", "general"),
    # --- Research ---
    ("Polish",     "Jakie badania prowadzi wydział inżynierii?", "research"),
    # --- Curriculum (concentration) ---
    ("Greek",      "Ποιες είναι οι κατευθύνσεις στην επιστήμη υπολογιστών;", "degree_map"),
    # --- Learning support (tutoring phrasing) ---
    ("Dutch",      "Waar kan ik bijles krijgen voor mijn vakken?", "learning_support"),
    # --- Course schedule ---
    ("Swedish",    "Vilken tid hjälper lärcentrum med COP 2006?", "learning_support"),
    # --- Faculty ---
    ("Turkish",    "İnşaat mühendisliği bölümünde hangi profesörler var?", "faculty"),
    # --- General / advising ---
    ("Chinese",    "我如何联系工程学院的学术顾问？", "general"),
    # --- Clubs ---
    ("Tagalog",    "Anong mga club o organisasyon ang meron sa engineering?", "club"),
    # --- Course description ---
    ("Hindi",      "COP 1500 किस बारे में है?", "course_description"),
    # --- Learning support ---
    ("Tamil",      "கற்றல் மையம் எந்த வகுப்புகளுக்கு உதவுகிறது?", "learning_support"),
    # --- Faculty reviews ---
    ("Korean",     "Buckley 교수님에 대한 학생들의 평가는 어떤가요?", "faculty_reviews"),
    # --- Research ---
    ("Japanese",   "工学部はどんな研究をしていますか？", "research"),
    # --- General / admissions ---
    ("Arabic",     "كيف أتقدم بطلب للقبول في FGCU؟", "general"),
    # --- Degree map / curriculum ---
    ("Hebrew",     "אילו קורסים אני צריך בשנה השלישית להנדסת תוכנה?", "degree_map"),
]


def run():
    passed = 0
    failed = []
    for lang, question, expected in TESTS:
        print("=" * 70)
        print(f"[{lang}] {question}")
        print(f"  expected doc_type: {expected}")
        doc_types, program, term = route_query(question)
        print(f"  route: doc_types={doc_types}, program={program}, term={term}")

        route_match = doc_types is not None and expected in doc_types
        print(f"  route hits expected: {route_match}")

        course_code = None
        if doc_types in (["course_offering"], ["course_description"]):
            course_code = extract_course_code(question)
        engine = make_engine(doc_types, program, term, course_code)
        try:
            nodes = engine.retrieve(question)
        except Exception:
            nodes = []
        print(f"  retrieved: {len(nodes)} chunks")

        try:
            lang_directive = (f"\n\nThe student asked in {lang}. "
                              f"Write your entire answer in {lang}.")
            answer = str(engine.query(SYSTEM_PROMPT + lang_directive +
                                      "\n\nQuestion: " + question))
        except Exception as e:
            answer = ""
            print(f"  query error: {e}")

        # quality checks
        ans_l = answer.lower()
        routed = doc_types is not None
        got_chunks = len(nodes) > 0
        non_trivial = len(answer.strip()) > 15

        # refusal phrases (model declining due to language) — should never happen
        refusal_markers = [
            "i can only answer in english", "only answer questions in english",
            "केवल अंग्रेजी", "sa ingles",  # Hindi / Tagalog "in English"
        ]
        refused = any(m in ans_l for m in refusal_markers)

        # English leakage when the question was NOT English: raw source strings
        # copied verbatim instead of translated. These appear across several
        # source files, so they catch copy-instead-of-translate behavior.
        leak_markers = ["area: computing", "area: civil",
                        "help available monday", "located in holmes",
                        "currently offers help"]
        leaked = (lang != "English") and any(m in ans_l for m in leak_markers)

        ok = route_match and got_chunks and non_trivial and not refused and not leaked
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            reason = []
            if not route_match: reason.append(f"route-miss(got {doc_types})")
            if not got_chunks: reason.append("no-chunks")
            if not non_trivial: reason.append("empty")
            if refused: reason.append("refused-language")
            if leaked: reason.append("english-leak")
            failed.append(f"{lang} [{expected}] ({', '.join(reason)})")
        print(f"  [{status}] answer: {answer.strip()}")
        print()

    print("=" * 70)
    print(f"RESULT: {passed}/{len(TESTS)} languages passed")
    if failed:
        print(f"Failed: {', '.join(failed)}")
    print("=" * 70)


if __name__ == "__main__":
    run()