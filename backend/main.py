from fastapi import FastAPI, UploadFile, File, Form, Body, Header, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from llama_index.core import VectorStoreIndex, Settings, PromptTemplate
from llama_index.core.vector_stores import MetadataFilters, MetadataFilter, FilterOperator
from llama_index.vector_stores.pinecone import PineconeVectorStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.groq import Groq
from pinecone import Pinecone
from dotenv import load_dotenv

# Date / academic-term awareness. Optional: if the module is missing the
# assistant still runs, just without the "today / current term" directive.
try:
    from academic_calendar import calendar_directive
except Exception:
    def calendar_directive(*a, **k):
        return ""
import os
import re
import sys
import json
import time
import hmac
import hashlib
import base64
import asyncio
import httpx
import keywords as kw
from fastapi import Request
from fastapi.responses import JSONResponse

load_dotenv()

# Date/term awareness: gives the model today's date and the current/upcoming
# FGCU term. Optional - if the module is missing, the app still runs.
try:
    from academic_calendar import calendar_directive
except Exception:
    def calendar_directive(today=None):
        return ""

# Windows consoles default to cp1252 and crash printing non-Latin scripts in
# terminal chat mode. Force UTF-8 so any language prints correctly.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── Setup ──────────────────────────────────────────────────
print("Loading embedding model...")
Settings.embed_model = HuggingFaceEmbedding(
    model_name="intfloat/multilingual-e5-large",
    trust_remote_code=True,
    # e5 is trained with asymmetric prefixes: queries get "query: ", documents
    # get "passage: ". Omitting them measurably degrades ranking — worst for
    # near-duplicates, cross-language queries, and entities buried in a chunk.
    # These MUST match ingest.py, and changing them requires a re-ingest.
    query_instruction="query: ",
    text_instruction="passage: ",
)
Settings.chunk_size = 400
Settings.chunk_overlap = 50

# LLM with automatic fallback.
#   PRIMARY: llama-3.3-70b-versatile  — preferred while it lasts. Groq is
#            decommissioning it on 2026-08-16; after that the startup probe below
#            fails and we use the backup automatically (no code change needed).
#   BACKUP : openai/gpt-oss-120b      — used if Llama is unavailable at startup
#            OR if it fails mid-run (see _run() in answer_question).
# (Other tested option if you ever want it: qwen/qwen3.6-27b, reasoning_effort "none".)
_GROQ_KEY = os.getenv("GROQ_API_KEY")
_PRIMARY_MODEL = "llama-3.3-70b-versatile"
_BACKUP_MODEL = "openai/gpt-oss-120b"

def _make_groq(model, **extra):
    return Groq(model=model, api_key=_GROQ_KEY, **extra)

_LLM_PRIMARY = _make_groq(_PRIMARY_MODEL)
# gpt-oss is a reasoning model; "low" keeps it snappy. If your installed
# llama-index-llms-groq rejects additional_kwargs, delete that one line.
_LLM_BACKUP = _make_groq(_BACKUP_MODEL, additional_kwargs={"reasoning_effort": "low"})
_using_backup = False

def _probe_llm(llm):
    """Cheap liveness check — returns False if the model errors (e.g. decommissioned)."""
    try:
        llm.complete("ping")
        return True
    except Exception as e:
        print(f"  probe failed: {type(e).__name__}: {str(e)[:160]}")
        return False

def _activate_backup(reason=""):
    """Permanently switch to the backup model for the rest of this process."""
    global _using_backup
    if not _using_backup:
        _using_backup = True
        Settings.llm = _LLM_BACKUP
        print(f"  !! switched to backup model {_BACKUP_MODEL}"
              + (f" ({reason})" if reason else ""))

print(f"Connecting to Groq (primary: {_PRIMARY_MODEL})...")
if _probe_llm(_LLM_PRIMARY):
    Settings.llm = _LLM_PRIMARY
    print(f"  -> active model: {_PRIMARY_MODEL}")
else:
    Settings.llm = _LLM_BACKUP
    _using_backup = True
    print(f"  -> {_PRIMARY_MODEL} unavailable; using backup {_BACKUP_MODEL}")

print("Connecting to Pinecone...")
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
pinecone_index = pc.Index(os.getenv("PINECONE_INDEX_NAME"))
vector_store = PineconeVectorStore(pinecone_index=pinecone_index)
index = VectorStoreIndex.from_vector_store(vector_store)

# Cohere reranker: re-scores the 40 retrieved candidates against the question with
# a cross-encoder and keeps the best 8. This is what fixes both cross-content bleed
# (only the most relevant chunks reach the LLM) and exact-name/cross-language recall
# (the multilingual model scores a Spanish query against English passages directly).
# Optional by design: if the package or COHERE_API_KEY is missing, retrieval still
# works, just without reranking.
try:
    from llama_index.postprocessor.cohere_rerank import CohereRerank
    _reranker = (
        CohereRerank(api_key=os.getenv("COHERE_API_KEY"), top_n=8,
                     model="rerank-multilingual-v3.0")
        if os.getenv("COHERE_API_KEY") else None
    )
    # Calendar questions usually want one term's dates. Keeping fewer chunks
    # stops several terms (e.g. Spring 2026 + Spring 2027) from crowding the
    # context and tempting the model to mention more than one.
    _reranker_calendar = (
        CohereRerank(api_key=os.getenv("COHERE_API_KEY"), top_n=4,
                     model="rerank-multilingual-v3.0")
        if os.getenv("COHERE_API_KEY") else None
    )
    if _reranker:
        print("[startup] Cohere reranker enabled (rerank-multilingual-v3.0, top_n=8; calendar=4).")
    else:
        print("[startup] COHERE_API_KEY not set - running without reranker.")
except Exception as _e:
    _reranker = None
    _reranker_calendar = None
    print(f"[startup] Cohere reranker unavailable ({_e}); running without it.")

# Load the set of known professor names once, so we can match a name mentioned
# in a question (e.g. "Professor Paul Allen") to the stored metadata value
# (e.g. "allen paul") and filter retrieval to just that professor's chunks.
KNOWN_PROFESSORS = []
try:
    _probe = pinecone_index.query(vector=[0.1] * 1024, top_k=300,
                                  include_metadata=True,
                                  filter={"doc_type": "faculty"})
    KNOWN_PROFESSORS = sorted({m["metadata"].get("professor", "")
                               for m in _probe["matches"]
                               if m["metadata"].get("professor")})
    print(f"Loaded {len(KNOWN_PROFESSORS)} professor names for name filtering.")
except Exception as e:
    print(f"Could not preload professor names: {e}")

print("Ready.\n")

SYSTEM_PROMPT = """You are a friendly and knowledgeable assistant for the U.A. Whitaker College of Engineering at FGCU. You talk like a helpful person, not a website.

When answering:
- Use natural, conversational language, as if you are talking to a student
- Never mention links, "Learn More", "visit the page", or website navigation
- Never say "based on the context" or "according to the provided information"
- If you know the answer, just say it directly and naturally
- Do not help with homework
- Do not help with coding questions
- Never answer with code
- If you don't know, say so naturally, like "I'm not sure about that one"
- Keep answers concise but complete, in plain language — no bullet points unless you are naturally listing several items
- If a course is offered in multiple semesters, focus on the semester the student asked about
- If the student is asking a follow-up, do NOT repeat what you already told them earlier in the conversation. Answer only the new question, and give just the new information they asked for - don't restate your previous answer.

Language:
- You are fully multilingual. Reply in the language of the student's QUESTION, never the language of the reference material (which is always English). The question's language is identified for you in the instruction that accompanies this prompt — follow it: write your ENTIRE answer in that language, and never refuse, drift, mix languages, or switch partway through. Do not comment on or apologize for the language; just answer naturally in it.
- Keep course CODES exactly as written (e.g. COP 1500, EGN 3331C) and keep the proper names of people and places unchanged, since those are official identifiers. Translate everything else — including the descriptive course name — into the answer's language, and put the translated name first with the code in parentheses, e.g. "Intro to Computer Science (COP 1500)" for an English answer.

If a student seems to be in emotional distress or a mental health crisis, gently encourage them to contact FGCU Counseling and Psychological Services (CAPS) at 239-590-7950, or the CAPS crisis line at 239-745-3277 outside business hours, and to call 911 in an emergency.

Answer only using the provided context."""


# ── Smart query router (EN/ES/FR) ──────────────────────────
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


# Every "informational" page type (everything that isn't a course/faculty/club
# record). Used as the broad fallback so a general question can reach any page,
# including ones re-tagged to the new categories below.
INFO_DOC_TYPES = ["general", "campus", "program", "department", "student_life",
                  "admissions", "policy", "degree_map", "research"]


def route_query(question: str, routing_text: str = None):
    """Return (doc_types, program, term). Keywords come from keywords.py.
    routing_text (question + recent history) lets follow-ups resolve a professor
    mentioned earlier."""
    q = question.lower()
    rtext = (routing_text or question)

    has_course_code = bool(re.search(r'\b[a-z]{3}\s*[1-7]\d{3}[a-z]?\b', q))

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
    admissions_words   = any(w in q for w in kw.ALL_ADMISSIONS)
    student_life_words = any(w in q for w in kw.ALL_STUDENT_LIFE)
    event_words        = any(w in q for w in kw.ALL_EVENT)
    policy_words       = any(w in q for w in kw.ALL_POLICY)
    advising_words     = any(w in q for w in kw.ALL_ADVISING)
    calendar_words     = any(w in q for w in kw.ALL_CALENDAR)
    campus_words       = any(w in q for w in kw.ALL_CAMPUS)
    department_words   = any(w in q for w in kw.ALL_DEPARTMENT)
    program_words      = any(w in q for w in kw.ALL_PROGRAM)

    program = detect_program(q)
    term = detect_term(q)

    # If the student explicitly says "learning hub", that wins over everything
    # (even if they also mention a course code or a time word).
    if hub_override:
        return ["learning_support"], None, None

    if has_course_code and schedule_words:
        return ["course_offering"], None, term
    if has_course_code and description_words:
        return ["course_description"], None, None
    # Academic calendar: "when do classes start", "last day to drop", withdrawal
    # and finals dates. Must be checked before the schedule+term branch below, or
    # "when do classes start in the fall" would be mistaken for a course schedule.
    if calendar_words:
        return ["calendar", "advising", "general"], None, None
    # "What classes does Professor X teach?" — no course code, but a professor
    # is named (here or earlier) plus a teaching/schedule word. Route to the
    # course offerings so we can filter by that instructor.
    if schedule_words and not rating_words and detect_professor(rtext):
        return ["course_offering"], None, term
    # "Who teaches it / when is it offered?" — a schedule question whose course
    # code came up earlier in the conversation (e.g. asked about COP 1500, then
    # "who teaches it in fall 2026?"). Route to offerings, filtered by that code.
    if schedule_words and not rating_words and extract_course_code(rtext):
        return ["course_offering"], None, term
    # A schedule question pinned to a term but with no course code or professor
    # (e.g. "what classes are offered in fall 2026?"). Filter offerings by that
    # term only (not program) so every per-subject term rollup is reachable.
    if schedule_words and not rating_words and term:
        return ["course_offering"], None, term
    if help_words:
        return ["learning_support"], None, None
    if rating_words:
        return ["faculty_reviews"], None, None

    # Advising: "who/when can I meet my advisor", advising hours, appointments,
    # change-major and registration FAQs all live in the advising pages. Checked
    # before the faculty/department routes so "advisor" isn't mistaken for a
    # professor lookup. Keeps department + general in the pool for spillover.
    if advising_words:
        return ["advising", "department", "general"], None, None
    # "institut" (fr/de/sv for institute) is a substring of English
    # "institutional", so a policy question like "institutional ethics and
    # compliance policy" would otherwise route here. If it also reads as policy,
    # let the policy route (below) handle it.
    if institute_words and not policy_words:
        return ["department", "general"], None, None
    if curriculum_words:
        return ["degree_map"], program, None
    # Events live in the event-labeled involvement files, in admissions (Say Yes
    # to the Nest), and in club write-ups (club events). We deliberately EXCLUDE
    # student_life: those files (CAPS, dean of students, recreation, etc.) hold no
    # events and only dilute the pool, pushing real event chunks past top_k. This
    # keeps the pool ~42 chunks so top_k=40 covers nearly all of it.
    if event_words:
        return ["event", "admissions", "club", "general"], None, None
    if club_words:
        return ["club"], None, None
    # Faculty: either a faculty keyword, OR the question names a known professor
    # without one (e.g. "Who is Paul Allen?", "Tell me about Allen"). We check the
    # QUESTION (not history) so an unrelated follow-up after a professor was
    # mentioned earlier isn't pulled into the faculty route.
    if faculty_words or detect_professor(question):
        return ["faculty", "faculty_reviews"], None, None
    # ── Page-data topics (admissions, student life, policies, campus, etc.) ──
    # Each route stays broad (keeps "general" and related types in the mix) so
    # info scattered across pages — e.g. "Holmes" shows up in faculty office
    # lines AND the engineering pages — is never filtered out.
    if admissions_words:
        return ["admissions", "general"], None, None
    if policy_words:
        return ["policy", "general"], None, None
    # Student-life is checked before campus so a general student-life question
    # routes here (and still reaches the event-labeled involvement files via the
    # "event" type below), while a bare "Holmes" / "where is..." → campus.
    if student_life_words:
        return ["student_life", "club", "event", "general"], None, None
    if department_words:
        return ["department", "program", "general"], program, None
    if program_words:
        return ["program", "degree_map", "general"], program, None
    if campus_words:
        return ["campus", "general", "faculty", "student_life"], None, None
    if general_words:
        return INFO_DOC_TYPES, None, None
    return None, None, None


# Common 3-letter words (articles/prepositions across the supported languages)
# that can sit directly in front of a year and look like a course prefix. Real
# FGCU subject codes (COP, EGN, CES, ...) are never ordinary words, so excluding
# these removes false positives like "the 2026" while keeping real codes such as
# COP 2006 (whose number also happens to look year-like).
_NON_SUBJECT_PREFIXES = {
    "the", "for", "our", "his", "her", "its", "and", "are", "was", "you",
    "all", "any", "who", "how", "why", "out", "off", "per", "via", "but", "not",
    "del", "der", "die", "das", "les", "des", "los", "las", "dos", "una", "uno",
    "ein", "een", "den", "det", "ist",
}


def extract_course_code(question: str):
    """Pull a course code like 'cop 1500' from a question, normalized to
    lowercase with one space, to match the course_code metadata field.

    FGCU course codes are a 3-letter subject prefix + a 4-digit number whose
    first digit is 1-7 (course level). Two guards keep ordinary text out: the
    number's first digit must be 1-7, and the 3-letter prefix must not be a
    common word. So 'fall of 2026' and 'the 2026' are not misread, while real
    codes like COP 2006 still match. We scan every match so a real code later in
    the sentence is still found after skipping a word like 'the'."""
    for m in re.finditer(r'\b([a-zA-Z]{3})\s*([1-7]\d{3}[a-zA-Z]?)\b', question):
        prefix = m.group(1).lower()
        if prefix in _NON_SUBJECT_PREFIXES:
            continue
        return f"{prefix} {m.group(2).lower()}"
    return None


def detect_professor(question: str):
    """Match a professor name mentioned in the question against the known list.
    Stored names are 'lastname firstname' (lowercase), sometimes comma-formatted
    like 'islam, md baharul'. A student may say them in either order ('Professor
    Paul Allen' or 'Allen'). We normalise punctuation on BOTH sides so 'islam,'
    still matches 'islam', then require every significant name word in a known
    entry to appear in the question (a unique surname alone also counts)."""
    q = question.lower()
    for ch in ",.;:()?!¿¡\"'":
        q = q.replace(ch, " ")
    # strip common titles (word-bounded, so 'dr' inside 'address' is untouched)
    q = " " + q + " "
    for title in (" professor ", " prof ", " dr ", " instructor ", " teacher "):
        q = q.replace(title, " ")
    best = None
    best_score = 0
    for prof in KNOWN_PROFESSORS:
        clean = prof.lower().replace(",", " ").replace(".", " ")
        parts = [p for p in clean.split() if len(p) > 2]
        if not parts:
            continue
        hits = sum(1 for p in parts if (" " + p + " ") in q)
        # require every name part to be present (so "allen paul" needs both
        # 'allen' and 'paul'); a single distinctive surname also counts
        if hits == len(parts) and hits > best_score:
            best, best_score = prof, hits
    # fall back: a unique surname match (first word of stored name)
    if not best:
        for prof in KNOWN_PROFESSORS:
            clean = prof.lower().replace(",", " ").replace(".", " ").split()
            surname = clean[0] if clean else ""
            if len(surname) > 2 and (" " + surname + " ") in q:
                if best is None:
                    best = prof
                else:
                    return None  # ambiguous surname; don't guess
    return best


def make_engine(doc_types, program, term, course_code=None, professor=None,
                qa_template=None, postprocessors=None):
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
    if professor:
        # Faculty/course files tag the name "lastname firstname" but the
        # RateMyProfessors review files tag it "firstname lastname". To match
        # across both, filter on either word order.
        parts = professor.split()
        if len(parts) == 2:
            variants = [professor, f"{parts[1]} {parts[0]}"]
            filter_list.append(MetadataFilter(key="professor", value=variants,
                                              operator=FilterOperator.IN))
        else:
            filter_list.append(MetadataFilter(key="professor", value=professor,
                                              operator=FilterOperator.EQ))
    # Retrieve a wide candidate set (40); the Cohere reranker (a node
    # postprocessor) re-scores them against the question and keeps only the best
    # handful, so the LLM sees tight, on-topic context instead of 20 diluted hits.
    kwargs = {"similarity_top_k": 40}
    if qa_template is not None:
        kwargs["text_qa_template"] = qa_template
    if postprocessors:
        kwargs["node_postprocessors"] = postprocessors
    if filter_list:
        kwargs["filters"] = MetadataFilters(filters=filter_list, condition="and")
    return index.as_query_engine(**kwargs)


def detect_question_language(q: str) -> str:
    """Return a language name ONLY for non-Latin scripts, where the model
    sometimes drifts. For Latin-script text (English, Spanish, French, German,
    etc.) we return None and let the model detect it itself — it does this
    reliably, and forcing a guess here caused French questions to be mislabeled
    as English."""
    # Japanese uses kana (hiragana/katakana); Chinese does not. Check for kana
    # ANYWHERE before deciding on the shared CJK ideograph range, so a Japanese
    # sentence that begins with a kanji (e.g. "教授は…") isn't mislabeled Chinese.
    if any(0x3040 <= ord(ch) <= 0x30FF for ch in q):
        return "Japanese"
    for ch in q:
        o = ord(ch)
        if 0x4E00 <= o <= 0x9FFF: return "Chinese"
        if 0xAC00 <= o <= 0xD7AF: return "Korean"
        if 0x0600 <= o <= 0x06FF: return "Arabic"
        if 0x0900 <= o <= 0x097F: return "Hindi"
        if 0x0B80 <= o <= 0x0BFF: return "Tamil"
        if 0x0400 <= o <= 0x04FF: return "Russian or Ukrainian"
        if 0x0370 <= o <= 0x03FF: return "Greek"
    return None  # Latin script: let the model detect the exact language


# Optional: langdetect gives a far more reliable read of a question's language
# than function-word markers, especially for short inputs like "what class is
# cop 3003". It's optional — without it we fall back to the markers below and to
# the model's own detection. Install with: pip install langdetect
try:
    from langdetect import (detect as _langdetect, detect_langs as _langdetect_langs,
                            DetectorFactory as _LDFactory)
    _LDFactory.seed = 0  # make langdetect deterministic across runs
    _LANGDETECT_OK = True
except Exception:
    _LANGDETECT_OK = False

_ISO_TO_LANG = {
    "en": "English", "es": "Spanish", "pt": "Portuguese", "fr": "French",
    "de": "German", "it": "Italian", "ru": "Russian", "uk": "Ukrainian",
    "pl": "Polish", "el": "Greek", "nl": "Dutch", "sv": "Swedish",
    "tr": "Turkish", "zh": "Chinese", "zh-cn": "Chinese", "zh-tw": "Chinese",
    "tl": "Tagalog", "hi": "Hindi", "ta": "Tamil", "ko": "Korean",
    "ja": "Japanese", "ar": "Arabic",
}


def detect_language_name(q: str):
    """Identify the question's language as one of our supported names using
    langdetect. Returns None if langdetect isn't installed, if it returns a
    language we don't support, OR if the input is too short / low-confidence to
    trust. langdetect is unreliable on short queries ("when does it happen" ->
    nl:0.71, "tell me more" -> it:0.99), so we only trust it on inputs of a few
    words AND with high confidence; otherwise the caller falls back / inherits."""
    if not _LANGDETECT_OK:
        return None
    try:
        langs = _langdetect_langs(q)
    except Exception:
        return None
    if not langs:
        return None
    top = langs[0]
    if len(q.split()) < 5 or top.prob < 0.90:
        return None
    code = top.lang.lower()
    return _ISO_TO_LANG.get(code) or _ISO_TO_LANG.get(code.split("-")[0])


def _markers_language(q: str):
    """Marker-word vote for a NON-English Latin-script language, or None if
    nothing clearly wins. (English has no markers; it's the default elsewhere.)
    Needs at least two distinctive hits so a stray word can't flip the language."""
    ql = " " + q.lower() + " "
    # Detach sentence punctuation so a trailing "?" or leading "¿" doesn't fuse to a
    # marker word ("hay?" != " hay "). Keep "¿"/"¡" as their own tokens since they are
    # themselves Spanish markers.
    for _ch in "?!.,;:()\"":
        ql = ql.replace(_ch, " ")
    ql = ql.replace("¿", " ¿ ").replace("¡", " ¡ ")
    # Distinctive function words per language. We deliberately avoid words that
    # look similar across languages (like "professor") to prevent an English
    # question from matching another language by accident.
    markers = {
        "Spanish": [" el ", " la ", " qué ", " quién ", " cómo ", " dónde ", " es ", " cuál ", " profesor ", "¿", "ñ",
                    " hay ", " cuáles ", " cuándo ", " los ", " las ", " una ", " del ", " sobre ",
                    " estoy ", " estás ", " está ", " muy ", " mis ", " siento ", " tengo ", " necesito ",
                    " ayuda ", " gracias ", " hola ", " quiero ", " soy "],
        "French": [" le ", " qui ", " est ", " quel ", " quelle ", " où ", " quels ", " professeur ", " bonjour ", "ç",
                   " je ", " suis ", " très ", " merci ", " j'ai ", " besoin ", " aide ", " avec ", " pour "],
        "Portuguese": [" quem ", " qual ", " onde ", " você ", " obrigado ", " disciplina ", " ã ",
                       " estou ", " muito ", " sinto ", " preciso ", " olá ", " sou ", " quero ", " não ", " ajuda "],
        "German": [" der ", " wer ", " ist ", " wie ", " wo ", " welche ", " welcher ", " welches ",
                   " kurs ", " danke ", " ß ", " gibt ", " wann ", " warum ",
                   " veranstaltung ", " veranstaltungen ",
                   " ich ", " bin ", " sehr ", " hallo ", " brauche ", " hilfe ", " und ", " nicht ", " für "],
        "Italian": [" il ", " chi ", " cosa ", " dove ", " professore ", " corso ", " grazie ",
                    " sono ", " molto ", " ciao ", " bisogno ", " aiuto ", " perché ", " sto "],
        "Dutch": [" het ", " wie ", " wat ", " waar ", " hoe ", " docent ", " bedankt ",
                  " welke ", " biedt ", " aan ", " een ", " zijn ", " voor ", " heeft ",
                  " jullie ", " kunnen ", " opleiding ", " opleidingen ", " hoeveel ", " aanbod ",
                  " ik ", " ben ", " heel ", " hallo ", " hulp ", " nodig ", " niet "],
        "Polish": [" kto ", " co ", " gdzie ", " jak ", " dziękuję ", " ł ",
                   " jestem ", " bardzo ", " cześć ", " pomocy ", " potrzebuję ", " nie ", " mam "],
        "Swedish": [" vem ", " vad ", " var ", " hur ", " tack ",
                    " jag ", " är ", " mycket ", " hej ", " hjälp ", " behöver ", " inte "],
        "Turkish": [" kim ", " nerede ", " nasıl ", " profesör ", " ders ", " teşekkür ",
                    " ben ", " çok ", " merhaba ", " yardım ", " için ", " değil "],
        "Tagalog": [" ang ", " sino ", " ano ", " saan ", " paano ", " guro ", " salamat ",
                    " ako ", " kamusta ", " tulong ", " hindi ", " mga "],
    }
    best, best_score = None, 1  # need >= 2 hits to claim a language
    for lang, words in markers.items():
        score = sum(1 for w in words if w in ql)
        if score > best_score:
            best, best_score = lang, score
    return best


_EN_MARKERS = [
    " what ", "what is", "what's", "what are", "what does", " where ", "where is",
    " when ", " who ", " how ", " why ", " which ", " whose ", "tell me", "do you",
    "does ", " can i ", "can you", "could you", "how do i", " i need", " i want",
    " i'm ", " is the ", " are the ", " of the ",
]


def _english_markers(q: str) -> bool:
    """True if the question carries DISTINCTIVE English structure words (what /
    where / when / tell me / how do i ...). These are sentence-frame words, not
    the kind that appear inside an English proper noun, so a non-English question
    that merely contains an English event name (e.g. "Holmes is Your Home") won't
    trip them. Lets a short, clearly-English question ("What is Holmes Hall?")
    resolve to English instead of inheriting the conversation's language."""
    ql = " " + q.lower().strip() + " "
    return any(m in ql for m in _EN_MARKERS)


_UK_LETTERS = set("іїєґ")

def _cyrillic_name(q: str) -> str:
    """Tell Ukrainian from Russian within the shared Cyrillic block. Ukrainian
    uses i, ï, je, g-with-upturn (i ï є ґ) - letters Russian does not have - so
    their presence labels the text Ukrainian; otherwise we call it Russian. Both
    still answer fine; this only fixes the LABEL that drives the TTS voice and UI."""
    return "Ukrainian" if any(ch in _UK_LETTERS for ch in q.lower()) else "Russian"


def _detected_language(q: str):
    """A POSITIVE language read for a single question, or None if nothing is
    reliable. Unlike guess_ui_language this does NOT default to English, so
    callers can fall back to the conversation's language for short follow-ups."""
    script_lang = detect_question_language(q)
    if script_lang:
        return _cyrillic_name(q) if script_lang.startswith("Russian") else script_lang
    return (detect_language_name(q) or _markers_language(q)
            or ("English" if _english_markers(q) else None))


def _conversation_language(history):
    """The language of the most recent prior user turn we can read. Used to keep
    a short, ambiguous follow-up ("when does it happen") in the conversation's
    established language instead of re-guessing — langdetect flips short English
    to Dutch/Italian, which would switch the whole UI mid-chat."""
    for turn in reversed(history or []):
        q = turn.get("question", "") if isinstance(turn, dict) else ""
        lang = _detected_language(q) if q else None
        if lang:
            return lang
    return None


def guess_ui_language(q: str) -> str:
    """Best-effort language name for switching the UI text, defaulting to
    English. Drives only which language the interface displays, not how the
    model answers."""
    return _detected_language(q) or "English"


_ANAPHORA = {"it", "its", "it's", "that", "this", "they", "them", "those", "these",
             "he", "she", "him", "her", "his", "their", "theirs"}
_BARE_Q = {"when", "where", "how", "why", "who", "what", "which", "whose", "whom"}
_STOP = {"is", "are", "was", "were", "am", "be", "been", "being", "do", "does", "did",
         "the", "a", "an", "of", "for", "to", "about", "in", "on", "at", "with", "by",
         "and", "or", "please", "can", "could", "would", "there", "some", "any",
         "me", "tell", "give", "show", "i", "my", "get"}
_MORE = {"tell me more", "more", "go on", "and", "what else", "anything else",
         "continue", "more info", "more details"}


def _is_followup(q: str) -> bool:
    """True only for questions that genuinely depend on the previous turn, so we
    can safely fold in the prior question for retrieval.

    The test is whether the question carries its own subject. "who is paul allen"
    has content words (paul, allen) -> self-contained, even lowercased. "who is it"
    or "when?" reduces to nothing but pronouns and question words -> it leans on the
    previous turn. Relying on content words (not capitalization) means it also works
    when the user types in lower case, which is what leaked the ASCE answer into the
    Paul Allen question."""
    raw = q.strip()
    ql = raw.lower().rstrip("?.! ").strip()
    if not ql:
        return False
    if ql in _MORE:
        return True
    if '"' in raw:                       # a quoted subject stands on its own
        return False
    words = ql.split()
    if set(words) & _ANAPHORA:           # leans on a pronoun referring to prior turn
        return True
    content = [w for w in words if w not in _STOP and w not in _BARE_Q]
    return not content                   # only question/filler words left -> follow-up


# Backstop for the "never answer with code" rule (see _strip_code below).
_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```")
# Short refusal used only if an answer was essentially all code. Machine-assisted
# translations - flag for native review. Keys match the names answer_question
# resolves (Cyrillic maps to "Russian").
_CODE_REFUSAL = {
    "English": "I can help with questions about the college, its courses, and faculty, but I can't help with homework or coding.",
    "Spanish": "Puedo ayudarte con preguntas sobre la universidad, sus cursos y el profesorado, pero no puedo ayudarte con tareas ni con programación.",
    "Portuguese": "Posso ajudar com perguntas sobre a faculdade, os cursos e o corpo docente, mas não posso ajudar com tarefas ou programação.",
    "French": "Je peux répondre aux questions sur le collège, les cours et le corps professoral, mais je ne peux pas aider avec les devoirs ni la programmation.",
    "German": "Ich kann bei Fragen zum College, zu den Kursen und zum Lehrpersonal helfen, aber nicht bei Hausaufgaben oder beim Programmieren.",
    "Italian": "Posso aiutarti con domande sul college, sui corsi e sui docenti, ma non posso aiutarti con i compiti o la programmazione.",
    "Russian": "Я могу помочь с вопросами о колледже, его курсах и преподавателях, но не могу помочь с домашними заданиями или программированием.",
    "Ukrainian": "Я можу допомогти з питаннями про коледж, його курси та викладачів, але не можу допомогти з домашніми завданнями чи програмуванням.",
    "Polish": "Mogę pomóc w pytaniach o uczelnię, jej kursy i wykładowców, ale nie mogę pomóc w pracach domowych ani w programowaniu.",
    "Greek": "Μπορώ να βοηθήσω με ερωτήσεις για τη σχολή, τα μαθήματα και το διδακτικό προσωπικό, αλλά δεν μπορώ να βοηθήσω με εργασίες ή προγραμματισμό.",
    "Dutch": "Ik kan helpen met vragen over de opleiding, de vakken en de docenten, maar ik kan niet helpen met huiswerk of programmeren.",
    "Swedish": "Jag kan hjälpa till med frågor om högskolan, kurserna och lärarna, men jag kan inte hjälpa till med läxor eller programmering.",
    "Turkish": "Üniversite, dersler ve öğretim üyeleri hakkındaki sorularda yardımcı olabilirim, ancak ödev veya kodlama konusunda yardımcı olamam.",
    "Chinese": "我可以回答有关学院、课程和教师的问题，但无法帮助完成作业或编程。",
    "Tagalog": "Matutulungan kita sa mga tanong tungkol sa kolehiyo, mga kurso, at mga guro, ngunit hindi ako makakatulong sa homework o coding.",
    "Hindi": "मैं कॉलेज, उसके पाठ्यक्रमों और शिक्षकों से जुड़े सवालों में मदद कर सकता हूँ, लेकिन होमवर्क या कोडिंग में मदद नहीं कर सकता।",
    "Tamil": "கல்லூரி, அதன் பாடநெறிகள் மற்றும் ஆசிரியர்கள் பற்றிய கேள்விகளுக்கு உதவ முடியும், ஆனால் வீட்டுப்பாடம் அல்லது நிரலாக்கத்தில் உதவ முடியாது.",
    "Korean": "대학, 강좌, 교수진에 대한 질문은 도와드릴 수 있지만, 숙제나 코딩은 도와드릴 수 없습니다.",
    "Japanese": "大学やコース、教員に関する質問にはお答えできますが、宿題やコーディングのお手伝いはできません。",
    "Arabic": "يمكنني المساعدة في الأسئلة المتعلقة بالكلية ومقرراتها وأعضاء هيئة التدريس، لكن لا يمكنني المساعدة في الواجبات أو البرمجة.",
}


def _strip_code(answer: str, lang: str = "English") -> str:
    """Hard backstop for the 'never answer with code' rule. The system prompt
    already tells the model to decline homework/coding, but if it ever returns
    code anyway, we remove fenced code blocks before the answer reaches the user.
    If stripping the code leaves nothing meaningful (the whole answer was code),
    we substitute a short refusal in the user's language."""
    if "```" not in answer:
        return answer
    cleaned = _CODE_FENCE_RE.sub("", answer)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if len(cleaned) < 25:                       # answer was essentially all code
        return _CODE_REFUSAL.get(lang, _CODE_REFUSAL["English"])
    return cleaned


import difflib

def _sentences(text: str):
    parts = re.split(r"(?<=[.!?。！？])\s*", (text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def _dedup_followup(answer: str, history) -> str:
    """Deterministic backstop for the no-repeat rule. The prompt tells the model
    not to restate earlier answers, but it still sometimes re-gives a person's
    bio before answering a follow-up. Here we drop any LEADING answer sentences
    that closely match a sentence from the previous answer, keeping only the new
    content (and always keeping at least the final sentence)."""
    if not history:
        return answer
    last = history[-1]
    prev = (last.get("answer", "") if isinstance(last, dict) else "") or ""
    prev_sents = _sentences(prev)
    ans_sents = _sentences(answer)
    if not prev_sents or len(ans_sents) <= 1:
        return answer
    i = 0
    while i < len(ans_sents) - 1:          # never strip the last remaining sentence
        s = ans_sents[i].lower()
        if any(difflib.SequenceMatcher(None, s, p.lower()).ratio() > 0.8 for p in prev_sents):
            i += 1
        else:
            break
    trimmed = " ".join(ans_sents[i:]).strip()
    return trimmed or answer


def answer_question(question: str, history=None):
    history = history or []
    # For routing and entity detection, a follow-up ("what does he teach?")
    # may rely on a name mentioned earlier. We build a small context string of
    # recent turns and use it to help detect the course/professor when the
    # current question alone doesn't name one.
    recent = " ".join(
        (turn.get("question", "") + " " + turn.get("answer", ""))
        for turn in history[-3:]
    )
    routing_text = question + " " + recent

    doc_types, program, term = route_query(question, routing_text)
    # For course-specific routes, also filter to the exact course code so the
    # right course's chunk isn't buried among all courses in the same term.
    course_code = None
    if doc_types in (["course_offering"], ["course_description"]):
        course_code = extract_course_code(question) or extract_course_code(routing_text)
    # For faculty routes, filter to the named professor so their chunk isn't
    # buried among all faculty (same idea as the course-code filter). Fall back
    # to a professor named earlier in the conversation for follow-up questions.
    # Also applies to course_offering when the question is "what does X teach".
    professor = None
    if doc_types and ("faculty" in doc_types or "faculty_reviews" in doc_types
                      or doc_types == ["course_offering"]):
        professor = detect_professor(question) or detect_professor(routing_text)
    # If we're routing course offerings by professor, don't also force a course
    # code (we want ALL their courses, not one).
    if doc_types == ["course_offering"] and professor and not extract_course_code(question):
        course_code = None
    # Resolve the language once and use it for BOTH the answer directive and the
    # UI language we return. Non-Latin script is pinned directly (the model picks
    # ru/uk for the combined Cyrillic bucket). For Latin script we take a positive
    # read (confident langdetect, or distinctive markers); if a short, ambiguous
    # follow-up gives no read, we INHERIT the conversation's established language
    # instead of re-guessing — langdetect flips short English to Dutch/Italian,
    # which otherwise switches the whole answer and UI mid-chat.
    script_lang = detect_question_language(question)
    if script_lang:
        directive_lang = script_lang
        ui_lang = _cyrillic_name(question) if script_lang.startswith("Russian") else script_lang
    else:
        directive_lang = (detect_language_name(question) or _markers_language(question)
                          or ("English" if _english_markers(question) else None)
                          or _conversation_language(history))
        ui_lang = directive_lang or "English"

    if directive_lang:
        lang_directive = (
            f"\n\nThe student's question is in {directive_lang}. "
            f"Write your ENTIRE answer in {directive_lang}, regardless of the "
            f"language used in earlier turns of the conversation. Do not switch "
            f"languages or borrow words or characters from any other language or "
            f"script that may appear in the history."
        )
    else:
        lang_directive = (
            "\n\nAnswer in the SAME language as the CURRENT question below, and "
            "match ONLY the current question — earlier turns may be in other "
            "languages, but ignore that and do not let them change the language "
            "of your answer. Do not comment on which language it is — just answer "
            "naturally in that language."
        )
    # Build a short conversation transcript so the model can resolve follow-ups
    # ("he", "that course", "what about the fall?") against earlier turns.
    history_block = ""
    if history:
        lines = []
        for turn in history[-4:]:
            q = turn.get("question", "").strip()
            a = turn.get("answer", "").strip()
            if q:
                lines.append(f"Student: {q}")
            if a:
                lines.append(f"Assistant: {a}")
        if lines:
            history_block = (
                "\n\nConversation so far (for context only, to resolve references "
                "like 'he', 'she', 'that course'):\n" + "\n".join(lines)
                + "\n\nThis history is ONLY to help you understand the new "
                  "question. Do not repeat information you already gave above - "
                  "answer the student's new question directly with only the new "
                  "information they are now asking for."
                + "\n\nIMPORTANT: This history is ONLY for understanding what the "
                "student is referring to. Do NOT repeat, restate, or re-summarize "
                "anything you already told the student in an earlier turn. Do not "
                "reintroduce a person, course, or topic you already described. "
                "Answer ONLY the new question below, directly and on its own."
            )
    # Retrieval query = the QUESTION only, NOT the system prompt. Embedding the
    # whole system prompt pulled every query toward the same point and drowned out
    # the actual question - the single biggest retrieval fix here.
    #
    # For GENUINE follow-ups ("when is it?", "tell me more") we prepend the previous
    # question so references resolve. But we must NOT do this for self-contained
    # questions that merely happen to be short ("What is Eagle X?"), or the previous
    # topic bleeds into the answer. A question is a follow-up only if it leans on an
    # anaphor or is a bare interrogative AND names no subject of its own.
    retrieval_query = question
    followup = _is_followup(question)
    # Language-agnostic follow-up: _is_followup only recognises English anaphora
    # ("what does HE teach"), so a non-English teaching follow-up ("¿qué clases
    # enseña?", "quali corsi insegna?") looked self-contained and dropped the
    # subject, retrieving the wrong professor. If the current question is a
    # schedule/teaching question that names no professor or course of its own,
    # while the conversation already established one, treat it as a follow-up so
    # the prior question (which named the professor) is folded into the search.
    if history and not followup:
        sched = any(w in question.lower() for w in kw.ALL_SCHEDULE)
        own = detect_professor(question) or extract_course_code(question)
        established = detect_professor(routing_text) or extract_course_code(routing_text)
        if sched and established and not own:
            followup = True
    if history and followup:
        prev_q = history[-1].get("question", "").strip()
        retrieval_query = (prev_q + " " + question).strip()

    # System prompt + language directive + history go into the QA *template* (the
    # LLM still sees all of it) instead of into the retrieval query. Braces in that
    # text are escaped so PromptTemplate treats only {context_str}/{query_str} as
    # variables.
    # Date + current/upcoming-term awareness, prepended so the model always
    # knows "today" and which semester we're in.
    date_directive = calendar_directive()
    calendar_note = ""
    if doc_types and "calendar" in doc_types:
        calendar_note = (
            "\n\nThis is an academic-calendar question. Answer directly and concisely "
            "with only the date(s) the student asked about. If the student does not name "
            "a term, answer for the CURRENT term from the today's-date line above. Use "
            "full-term dates unless the student names a specific session (Session A, B, "
            "I, II, or Summer A, B, C). Do NOT mention, compare, or list any term or "
            "session other than the one being asked about, and do NOT narrate which term "
            "you are choosing or show your reasoning - state the answer in one or two "
            "sentences. When a term is named without a year (e.g. 'the spring semester'), "
            "use the next upcoming occurrence of that term based on today's date, and do "
            "not mention any past term that has already ended. 'Classes begin' means the "
            "regular first day of classes, not 'Saturday Classes Begin' and not any "
            "registration date."
        )
    _instr = (SYSTEM_PROMPT + date_directive + calendar_note + lang_directive + history_block).replace("{", "{{").replace("}", "}}")
    qa_template = PromptTemplate(
        _instr
        + "\n\nContext information from FGCU Engineering pages is below.\n"
          "---------------------\n{context_str}\n---------------------\n"
          "Using that context, answer the student's question.\n"
          "Question: {query_str}\nAnswer: "
    )
    _is_calendar = bool(doc_types and "calendar" in doc_types)
    _active_reranker = _reranker_calendar if (_is_calendar and _reranker_calendar) else _reranker
    _post = [_active_reranker] if _active_reranker else None

    def _run(dt, prog, trm, code, prof):
        try:
            return make_engine(dt, prog, trm, code, prof,
                               qa_template=qa_template,
                               postprocessors=_post).query(retrieval_query)
        except Exception as e:
            # If the primary model just died (e.g. Llama decommissioned mid-run),
            # switch to the backup once and retry this query immediately.
            if _using_backup:
                raise
            _activate_backup(type(e).__name__)
            return make_engine(dt, prog, trm, code, prof,
                               qa_template=qa_template,
                               postprocessors=_post).query(retrieval_query)

    def _no_match(r):
        # LlamaIndex returns the literal "Empty Response" (and no source nodes)
        # when the metadata filters match nothing.
        s = str(r).strip()
        return (not s) or s == "Empty Response" or not getattr(r, "source_nodes", None)

    response = _run(doc_types, program, term, course_code, professor)

    # Safety net: a course-code query that matched no chunks should not dead-end
    # as "Empty Response". This happens when we route to course_offering for a
    # course with no scheduled section (e.g. "who teaches COP 1500 and what's it
    # about", "what does COP 2006 cover", or a negated "I don't want the
    # schedule, just tell me what COP 1500 covers"). Retry across BOTH the
    # offering and the description for that code (dropping term/professor) so an
    # answerable course still answers instead of returning nothing.
    if course_code and _no_match(response):
        response = _run(["course_offering", "course_description"],
                        program, None, course_code, None)
    # Last resort: the course code alone, any doc type.
    if course_code and _no_match(response):
        response = _run(None, None, None, course_code, None)

    # General fail-safe (works for ANY topic in ANY language): if the routed,
    # filtered search still matched nothing — which can happen when a question
    # routes to a doc_type that holds no matching chunk, or when a non-English
    # phrasing routes imperfectly — fall back to an unfiltered search across
    # every document. The multilingual embedding model matches the question to
    # the closest content regardless of its language, so this keeps any file
    # reachable instead of dead-ending on "Empty Response".
    if _no_match(response):
        response = _run(None, None, None, None, None)

    answer = _dedup_followup(_strip_code(str(response), ui_lang), history)
    return answer, ui_lang


# ── Terminal chat mode ─────────────────────────────────────
def chat():
    print("=" * 60)
    print("FGCU Engineering Assistant — Terminal Chat")
    print("Type your question and press Enter. Type 'exit' to quit.")
    print("=" * 60)
    chat_history = []
    while True:
        try:
            question = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        if not question:
            continue
        if question.lower() in ("exit", "quit", "bye"):
            print("Goodbye!")
            break
        print("Thinking...")
        try:
            ans, _lang = answer_question(question, chat_history)
            print(f"\nAssistant: {ans}\n")
            chat_history.append({"question": question, "answer": ans})
            chat_history = chat_history[-6:]  # keep recent turns only
        except Exception as e:
            print(f"\nError: {e}\n")


# ── FastAPI app ────────────────────────────────────────────
app = FastAPI()
# CORS: set ALLOWED_ORIGINS in the environment to a comma-separated list of the
# exact frontend origins allowed to call this API, e.g.
#   ALLOWED_ORIGINS=https://ask-the-eagle.vercel.app,http://localhost:3000
# If unset (local dev), it falls back to "*" so nothing breaks on your machine.
_origins_env = os.getenv("ALLOWED_ORIGINS", "").strip()
_allowed_origins = [o.strip() for o in _origins_env.split(",") if o.strip()] or ["*"]
print(f"CORS allowed origins: {_allowed_origins}")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"]
)


# ─── Bot protection (Cloudflare Turnstile) ─────────────────────────────────
# A human solves the Turnstile widget once; the frontend exchanges that token at
# /verify for a short-lived signed session, then sends the session header with
# each /ask, /transcribe and /speak call. Those endpoints reject anything without
# a valid session, so bots can't hit the paid APIs (Groq / ElevenLabs) directly.
# If TURNSTILE_SECRET is unset (e.g. local dev) the check is skipped entirely, so
# nothing breaks while you develop without keys.
TURNSTILE_SECRET = os.getenv("TURNSTILE_SECRET", "")
SESSION_SECRET   = os.getenv("SESSION_SECRET", "dev-only-change-me")
SESSION_TTL      = 2 * 60 * 60          # how long one verified session lasts (s)


def _make_session() -> str:
    """A signed, expiring session token: base64(payload).hmac_sig."""
    exp = int(time.time()) + SESSION_TTL
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    sig = hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _valid_session(token: str) -> bool:
    if not token or "." not in token:
        return False
    payload, sig = token.rsplit(".", 1)
    expected = hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except Exception:
        return False
    return int(data.get("exp", 0)) > int(time.time())


async def require_human(x_session: str = Header(default="")):
    """Gate the costly endpoints: allow only requests carrying a valid session
    (issued by /verify after a Turnstile solve). No-op when Turnstile is not
    configured, so local development still works."""
    if not TURNSTILE_SECRET:
        return
    if not _valid_session(x_session):
        raise HTTPException(status_code=401, detail="Bot check required")


# ─── Usage logging (Supabase) ──────────────────────────────────────────────
# Every question is logged to a Supabase table (question, answer, language, the
# per-device client id, and a timestamp the DB fills in). Writes happen in a
# background task so they never slow down or break the user's answer, and the
# whole thing is a no-op if Supabase isn't configured.
SUPABASE_URL   = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY   = os.getenv("SUPABASE_KEY", "")
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE", "ask_logs")
SUPABASE_ISSUES_TABLE = os.getenv("SUPABASE_ISSUES_TABLE", "issue_reports")


async def log_interaction(client_id: str, question: str, answer: str, language: str, message_id: str = ""):
    """Best-effort insert of one row into Supabase. Never raises - logging must
    not affect the user's request. No-op when Supabase isn't configured."""
    if not (SUPABASE_URL and SUPABASE_KEY):
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                json={
                    "message_id": message_id or None,
                    "client_id": client_id or None,
                    "question": question,
                    "answer": answer,
                    "language": language,
                },
            )
    except Exception:
        pass  # logging is best-effort; swallow everything


# ─── Friendly error handling ───────────────────────────────────────────────
# If generation fails (e.g. a transient Groq/Pinecone/Cohere hiccup), the user
# should get a short, polite message in their own language instead of a raw 500.
_ERROR_TEXT = {
    "English":    "Sorry, something went wrong on my end. Please try again in a moment.",
    "Spanish":    "Lo siento, algo salió mal de mi lado. Inténtalo de nuevo en un momento.",
    "Portuguese": "Desculpe, algo deu errado do meu lado. Tente novamente em instantes.",
    "French":     "Désolé, un problème est survenu de mon côté. Veuillez réessayer dans un instant.",
    "German":     "Entschuldigung, bei mir ist etwas schiefgelaufen. Bitte versuche es gleich noch einmal.",
    "Italian":    "Scusa, qualcosa è andato storto da parte mia. Riprova tra un momento.",
    "Russian":    "Извините, у меня произошла ошибка. Попробуйте ещё раз через мгновение.",
    "Ukrainian":  "Вибачте, у мене сталася помилка. Спробуйте ще раз за мить.",
    "Polish":     "Przepraszam, coś poszło nie tak po mojej stronie. Spróbuj ponownie za chwilę.",
    "Greek":      "Συγγνώμη, κάτι πήγε στραβά από την πλευρά μου. Δοκιμάστε ξανά σε λίγο.",
    "Dutch":      "Sorry, er ging iets mis aan mijn kant. Probeer het zo meteen opnieuw.",
    "Swedish":    "Förlåt, något gick fel på min sida. Försök igen om en stund.",
    "Turkish":    "Üzgünüm, bir şeyler ters gitti. Lütfen birazdan tekrar deneyin.",
    "Chinese":    "抱歉，我这边出了点问题。请稍后再试。",
    "Tagalog":    "Pasensya na, may nangyaring mali sa panig ko. Pakisubukan ulit mamaya.",
    "Hindi":      "क्षमा करें, मेरी ओर से कुछ गलत हो गया। कृपया थोड़ी देर में फिर से प्रयास करें।",
    "Tamil":      "மன்னிக்கவும், என் பக்கத்தில் ஏதோ தவறு நடந்தது. சிறிது நேரத்தில் மீண்டும் முயற்சிக்கவும்.",
    "Korean":     "죄송합니다. 제 쪽에서 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.",
    "Japanese":   "申し訳ありません。こちらで問題が発生しました。少し待ってからもう一度お試しください。",
    "Arabic":     "عذرًا، حدث خطأ من جانبي. يرجى المحاولة مرة أخرى بعد قليل.",
}


def _safe_ui_lang(question: str) -> str:
    """Best-effort language of the question, for picking the error message.
    Never raises; defaults to English."""
    try:
        sl = detect_question_language(question)
        if sl:
            return _cyrillic_name(question) if sl.startswith("Russian") else sl
        return (detect_language_name(question) or _markers_language(question)
                or ("English" if _english_markers(question) else "English"))
    except Exception:
        return "English"


@app.exception_handler(Exception)
async def _unhandled_exception(request: Request, exc: Exception):
    """Catch-all so an unexpected error returns clean JSON, not an HTML stack
    trace. (FastAPI's own HTTPException responses are unaffected.)"""
    return JSONResponse(status_code=500, content={"error": "Something went wrong. Please try again."})


@app.post("/report")
async def report(body: dict = Body(default=None)):
    """Store a user-submitted issue report in Supabase."""
    data = body or {}
    description = (data.get("description") or "").strip()
    client_id = data.get("client_id") or ""
    if not description:
        raise HTTPException(status_code=400, detail="Empty description")
    if len(description) > 4000:
        description = description[:4000]
    if not (SUPABASE_URL and SUPABASE_KEY):
        return {"ok": True}                       # dev: nothing to write to
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{SUPABASE_URL}/rest/v1/{SUPABASE_ISSUES_TABLE}",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                json={"client_id": client_id or None, "description": description},
            )
        return {"ok": r.status_code in (200, 201, 204)}
    except Exception:
        return {"ok": False}


@app.post("/verify")
async def verify(body: dict = Body(default=None)):
    """Exchange a Turnstile token for a session token."""
    token = (body or {}).get("token", "")
    if not TURNSTILE_SECRET:
        return {"session": _make_session()}          # dev: Turnstile not configured
    if not token:
        raise HTTPException(status_code=400, detail="Missing Turnstile token")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={"secret": TURNSTILE_SECRET, "response": token},
        )
        result = resp.json()
    if not result.get("success"):
        raise HTTPException(status_code=403, detail="Bot check failed")
    return {"session": _make_session()}


@app.post("/ask")
async def ask(background: BackgroundTasks, question: str = "", body: dict = Body(default=None), _human=Depends(require_human)):
    # Accept either a query param (?question=) for backward compatibility, or a
    # JSON body {"question": ..., "history": [...], "client_id": "...",
    # "message_id": "..."}.
    history = []
    client_id = ""
    message_id = ""
    if body:
        question = body.get("question", question) or question
        history = body.get("history", []) or []
        client_id = body.get("client_id", "") or ""
        message_id = body.get("message_id", "") or ""
    # Generate the answer, retrying once on a transient failure (Groq/Pinecone/
    # Cohere hiccup). If it still fails, return a short, polite message in the
    # user's language instead of a raw 500.
    answer = None
    language = "English"
    for attempt in range(2):
        try:
            answer, language = answer_question(question, history)
            break
        except Exception:
            if attempt == 0:
                await asyncio.sleep(0.8)
                continue
            language = _safe_ui_lang(question)
            answer = _ERROR_TEXT.get(language, _ERROR_TEXT["English"])
    # Log the interaction after the response is sent (non-blocking).
    background.add_task(log_interaction, client_id, question, answer, language, message_id)
    return {"answer": answer, "language": language}


@app.post("/feedback")
async def feedback(body: dict = Body(default=None)):
    """Record a thumbs up/down for a previously logged answer, matched by the
    frontend's message_id. rating is 1 (up), -1 (down), or 0 (un-vote)."""
    data = body or {}
    message_id = (data.get("message_id") or "").strip()
    rating = data.get("rating")
    if not message_id or rating not in (1, -1, 0):
        raise HTTPException(status_code=400, detail="Bad feedback")
    if not (SUPABASE_URL and SUPABASE_KEY):
        return {"ok": True}                        # dev: nothing to write to
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.patch(
                f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?message_id=eq.{message_id}",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
                json={"rating": rating if rating in (1, -1) else None},
            )
        return {"ok": r.status_code in (200, 204)}
    except Exception:
        return {"ok": False}


# Whisper language codes for the supported languages (used when the user turns
# auto-detect OFF and picks a language, which improves accuracy with accents).
LANG_CODES = {
    "English": "en", "Spanish": "es", "Portuguese": "pt", "French": "fr",
    "German": "de", "Italian": "it", "Russian": "ru", "Ukrainian": "uk",
    "Polish": "pl", "Greek": "el", "Dutch": "nl", "Swedish": "sv",
    "Turkish": "tr", "Chinese": "zh", "Tagalog": "tl", "Hindi": "hi",
    "Tamil": "ta", "Korean": "ko", "Japanese": "ja", "Arabic": "ar",
}

# A vocabulary hint so Whisper spells our domain terms correctly even through
# an accent. Whisper biases toward words it sees in this prompt.
WHISPER_PROMPT = (
    "U.A. Whitaker College of Engineering, FGCU, Florida Gulf Coast University. "
    "Courses: COP 1500 Intro to Computer Science, COP 2006 Programming I, "
    "COP 3003 Programming II, EGN 3331C Mechanics of Materials, "
    "CES 4605C Steel Design, ENV 3006C Environmental Engineering, "
    "CDA 3104, CEN 3941, COT 3400. The Learning Hub. Professors Buckley, "
    "Sahiner, Tsegaye, Allen, Ciris, Dhakal, Ahuja."
)


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...), language: str = Form(""), _human=Depends(require_human)):
    audio_bytes = await audio.read()
    # The browser sends webm/opus from MediaRecorder. Give Whisper a filename
    # with a real extension so it detects the format correctly.
    filename = audio.filename or "audio.webm"
    content_type = audio.content_type or "audio/webm"
    form_data = {
        "model": "whisper-large-v3",
        "response_format": "json",
        "prompt": WHISPER_PROMPT,
    }
    # If the user picked a language (auto-detect off), force it for better
    # accuracy on accents. Otherwise Whisper auto-detects.
    code = LANG_CODES.get(language, "")
    if code:
        form_data["language"] = code
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
            files={"file": (filename, audio_bytes, content_type)},
            data=form_data
        )
    if resp.status_code != 200:
        print(f"[/transcribe] Groq error {resp.status_code}: {resp.text[:500]}")
        return {"text": "", "error": resp.text[:300]}
    text = resp.json().get("text", "")
    print(f"[/transcribe] ({language or 'auto'}) heard: {text!r}")
    return {"text": text}


# ── Text-to-speech: ElevenLabs primary, edge-tts fallback ──────────────────
# ElevenLabs (multilingual_v2, default voice "Sarah") is the primary voice. Its
# free tier is ~10k characters/month; when that quota is exhausted the API
# returns 401/402/429 (usually with "quota_exceeded" in the body). We then fall
# back to edge-tts (free Microsoft neural voices, no key, no character cap) so
# the demo never loses its voice. Unlike ElevenLabs' single multilingual voice,
# edge-tts uses one voice PER LANGUAGE, so we pick it from the answer's language
# via the existing guess_ui_language(), leaving the /speak signature unchanged.
try:
    import edge_tts
    _EDGE_TTS_AVAILABLE = True
except ImportError:
    _EDGE_TTS_AVAILABLE = False  # run: pip install edge-tts  to enable fallback

# Once ElevenLabs reports its quota is gone, skip it for the rest of this run to
# avoid a guaranteed-failing call on every request. Resets on server restart
# (which in practice lines up with the monthly quota reset).
_elevenlabs_quota_hit = False

# Native neural voice per language for the edge-tts fallback. Keys match the
# names guess_ui_language() returns. (It maps all Cyrillic to "Russian", so a
# Ukrainian answer currently uses the Russian voice — intelligible, not ideal.)
EDGE_VOICE_BY_LANG = {
    "English": "en-US-AriaNeural",         "Spanish": "es-ES-ElviraNeural",
    "Portuguese": "pt-BR-FranciscaNeural",  "French": "fr-FR-DeniseNeural",
    "German": "de-DE-KatjaNeural",         "Italian": "it-IT-ElsaNeural",
    "Russian": "ru-RU-SvetlanaNeural",     "Ukrainian": "uk-UA-PolinaNeural",
    "Polish": "pl-PL-ZofiaNeural",         "Greek": "el-GR-AthinaNeural",
    "Dutch": "nl-NL-ColetteNeural",        "Swedish": "sv-SE-SofieNeural",
    "Turkish": "tr-TR-EmelNeural",         "Chinese": "zh-CN-XiaoxiaoNeural",
    "Tagalog": "fil-PH-BlessicaNeural",    "Hindi": "hi-IN-SwaraNeural",
    "Tamil": "ta-IN-PallaviNeural",        "Korean": "ko-KR-SunHiNeural",
    "Japanese": "ja-JP-NanamiNeural",      "Arabic": "ar-EG-SalmaNeural",
}
EDGE_DEFAULT_VOICE = "en-US-AriaNeural"


async def _edge_tts_audio(text: str) -> bytes:
    """Synthesize MP3 bytes with edge-tts, choosing a voice that matches the
    language of the text so a non-English answer isn't read by an English voice.
    Raises if the stream fails."""
    voice = EDGE_VOICE_BY_LANG.get(guess_ui_language(text), EDGE_DEFAULT_VOICE)
    communicate = edge_tts.Communicate(text, voice)
    chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    return b"".join(chunks)


def _is_elevenlabs_quota_error(status_code: int, body: str) -> bool:
    """ElevenLabs signals an exhausted/blocked quota with 401/402/429, usually
    with 'quota_exceeded' in the body."""
    return status_code in (401, 402, 429) or "quota" in body.lower()


def _speakable(text: str) -> str:
    """Rewrite course codes so TTS spells the subject letters instead of reading
    them as a word: 'COP 1500' -> 'C O P 1500', 'EGN 3331C' -> 'E G N 3331 C'.

    We do this in the input text because neither engine can via markup:
    eleven_multilingual_v2 only supports phoneme tags for English (not this
    model), and edge-tts dropped custom SSML. Only the spoken audio changes —
    the on-screen answer still shows 'COP 1500'. The same prefix blocklist as
    extract_course_code keeps ordinary words (e.g. 'the 2026') from being spelled."""
    def repl(m):
        prefix, number, suffix = m.group(1), m.group(2), m.group(3)
        if prefix.lower() in _NON_SUBJECT_PREFIXES:
            return m.group(0)
        letters = " ".join(prefix.upper())
        tail = " " + " ".join(suffix.upper()) if suffix else ""
        return f"{letters} {number}{tail}"
    return re.sub(r'\b([A-Za-z]{3})\s*([1-7]\d{3})([A-Za-z]?)\b', repl, text)


@app.post("/speak")
async def speak(text: str, _human=Depends(require_human)):
    global _elevenlabs_quota_hit
    text = (text or "").strip()
    if not text:
        return Response(content=b'{"error": "empty text"}', status_code=400,
                        media_type="application/json")
    text = _speakable(text)  # spell course-code letters so they aren't read as words

    # 1) PRIMARY: ElevenLabs (skipped once we know its quota is gone).
    if not _elevenlabs_quota_hit:
        voice_id = "EXAVITQu4vr4xnSDxMaL"  # Sarah (default voice; free-tier safe)
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                    headers={"xi-api-key": os.getenv("ELEVENLABS_API_KEY")},
                    json={
                        "text": text,
                        "model_id": "eleven_multilingual_v2",
                        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
                    }
                )
            content_type = resp.headers.get("content-type", "")
            if resp.status_code == 200 and "audio" in content_type:
                return Response(content=resp.content, media_type="audio/mpeg")
            # Non-audio response: decide whether the quota ran out.
            body = resp.text[:500]
            print(f"[/speak] ElevenLabs error {resp.status_code}: {body}")
            if _is_elevenlabs_quota_error(resp.status_code, body):
                print("[/speak] ElevenLabs quota exhausted -> switching to edge-tts for this run.")
                _elevenlabs_quota_hit = True  # latch: stop retrying ElevenLabs
            # fall through to edge-tts for this request either way
        except Exception as e:
            # Transient failure (network/timeout): try edge-tts now, but do NOT
            # latch the quota flag — ElevenLabs may be fine on the next request.
            print(f"[/speak] ElevenLabs request failed ({e}) -> trying edge-tts.")

    # 2) FALLBACK: edge-tts (free, no key, no character cap, all 21 languages).
    if _EDGE_TTS_AVAILABLE:
        try:
            audio = await _edge_tts_audio(text)
            if audio:
                return Response(content=audio, media_type="audio/mpeg")
            print("[/speak] edge-tts returned no audio.")
        except Exception as e:
            print(f"[/speak] edge-tts fallback failed: {e}")
    else:
        print("[/speak] edge-tts not installed; run: pip install edge-tts")

    # 3) Both unavailable: degrade gracefully so the frontend can show
    #    "voice unavailable" instead of trying to play a broken audio body.
    return Response(content=b'{"error": "voice unavailable"}', status_code=503,
                    media_type="application/json")


# ── Run mode ───────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "chat":
        chat()
    else:
        print("Run with: python main.py chat")
        print("Or start API with: uvicorn main:app --reload --port 8000")
