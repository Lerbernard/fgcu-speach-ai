from fastapi import FastAPI, UploadFile, File, Form, Body, Header, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from llama_index.core import VectorStoreIndex, Settings, PromptTemplate
from llama_index.core.vector_stores import MetadataFilters, MetadataFilter, FilterOperator
from llama_index.vector_stores.pinecone import PineconeVectorStore
from llama_index.llms.groq import Groq
from pinecone import Pinecone
from pinecone_embedding import PineconeInferenceEmbedding
from dotenv import load_dotenv

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

try:
    from academic_calendar import calendar_directive
except Exception:
    def calendar_directive(today=None):
        return ""

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

print("Connecting to Pinecone (client + hosted embedding)...")
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
# Embed queries with Pinecone's hosted multilingual-e5-large (same model the
# index was built with) instead of loading a ~2 GB local model. Keeps the
# container small enough for a 512 MB host and boots in seconds.
Settings.embed_model = PineconeInferenceEmbedding(pc)
Settings.chunk_size = 400
Settings.chunk_overlap = 50

_GROQ_KEY = os.getenv("GROQ_API_KEY")
_PRIMARY_MODEL = "llama-3.3-70b-versatile"
_BACKUP_MODEL = "openai/gpt-oss-120b"

def _make_groq(model, **extra):
    return Groq(model=model, api_key=_GROQ_KEY, **extra)

_LLM_PRIMARY = _make_groq(_PRIMARY_MODEL)
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

print("Opening Pinecone index...")
pinecone_index = pc.Index(os.getenv("PINECONE_INDEX_NAME"))
vector_store = PineconeVectorStore(pinecone_index=pinecone_index)
index = VectorStoreIndex.from_vector_store(vector_store)

try:
    from llama_index.postprocessor.cohere_rerank import CohereRerank
    _reranker = (
        CohereRerank(api_key=os.getenv("COHERE_API_KEY"), top_n=8,
                     model="rerank-multilingual-v3.0")
        if os.getenv("COHERE_API_KEY") else None
    )
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
- Only say you're unsure ("I'm not sure about that one") when the provided context genuinely does NOT contain the answer. If the context DOES contain it, answer directly with no "I'm not sure" preamble — never hedge and then answer anyway.
- Keep answers concise but complete, in plain language — no bullet points unless you are naturally listing several items
- If a course is offered in multiple semesters, focus on the semester the student asked about
- A course can have several sections (different CRNs), each with its own meeting time, and the same instructor may teach more than one section. When asked who teaches a course, list each DISTINCT instructor once. When asked about meeting times, give each section's time. Whenever you state a count (instructors, sections, or times), make the number match EXACTLY what you go on to list — never say "two" and then name three. If unsure of the count, just list the items without stating a number.
- If the student is asking a follow-up, do NOT repeat what you already told them earlier in the conversation. Answer only the new question, and give just the new information they asked for - don't restate your previous answer.
- Answer only about the exact thing the student asked. Never bring up, compare to, or disclaim a different but similarly-named show, product, movie, or event that is not in the context — for example, never mention "Say Yes to the Dress" when asked about "Say Yes to the Nest." Do not introduce any name or fact that is not in the provided context.

Language:
- You are fully multilingual. Reply in the language of the student's QUESTION, never the language of the reference material (which is always English). The question's language is identified for you in the instruction that accompanies this prompt — follow it: write your ENTIRE answer in that language, and never refuse, drift, mix languages, or switch partway through. Do not comment on or apologize for the language; just answer naturally in it.
- Keep course CODES exactly as written (e.g. COP 1500, EGN 3331C) and keep the proper names of people and places unchanged, since those are official identifiers. Translate everything else — including the descriptive course name — into the answer's language, and put the translated name first with the code in parentheses, e.g. "Intro to Computer Science (COP 1500)" for an English answer.

If a student seems to be in emotional distress or a mental health crisis, gently encourage them to contact FGCU Counseling and Psychological Services (CAPS) at 239-590-7950, or the CAPS crisis line at 239-745-3277 outside business hours, and to call 911 in an emergency.

Answer only using the provided context."""

def detect_program(q):
    for program, lang_words in kw.PROGRAM_WORDS.items():
        for word in kw.flatten(lang_words):
            if word in q:
                return program
    return None

_TERM_SEASONS = {"fall", "spring", "summer", "winter"}


def detect_term(q):
    # Strip course codes first. "COP 2006 in Fall 2026" would otherwise match
    # 2006 (the course NUMBER) as the year and filter on "fall 2006", which
    # matches nothing and makes retrieval return empty. Season words are kept,
    # so "fall 2026" survives the strip.
    ql = (q or "").lower()

    def _drop(m):
        return m.group(0) if m.group(1) in _TERM_SEASONS else " "

    ql = re.sub(r"\b([a-z]{2,4})\s*(\d{3,4}[a-z]?)\b", _drop, ql)

    season = None
    for season_name, lang_words in kw.SEASON_WORDS.items():
        if any(w in ql for w in kw.flatten(lang_words)):
            season = season_name
            break
    year = re.search(r'(20\d{2})', ql)
    if season and year:
        return f"{season} {year.group(1)}"
    return None

INFO_DOC_TYPES = ["general", "campus", "program", "department", "student_life",
                  "admissions", "policy", "degree_map", "research"]

# A chunk "carries a date" if it names a spelled-out month, OR contains a
# pipe-delimited numeric calendar date ("| 19 | 08 | 2026 |"), OR a clock time
# ("2:00 pm"). The calendar rows store dates numerically, so a month-name-only
# check missed them entirely and the dated event record never got boosted above
# its own undated description chunks (the "Holmes is Your Home" coin-flip).
_MONTH_RX = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\b", re.I)
_NUMDATE_RX = re.compile(r"\d{1,2}\s*\|\s*\d{1,2}\s*\|\s*20\d{2}\b")
_TIME_RX = re.compile(r"\b\d{1,2}:\d{2}\s*(?:am|pm)\b", re.I)

def _has_date(text: str) -> bool:
    t = text or ""
    return bool(_MONTH_RX.search(t) or _NUMDATE_RX.search(t) or _TIME_RX.search(t))

try:
    from llama_index.core.postprocessor.types import BaseNodePostprocessor

    class _DateBoost(BaseNodePostprocessor):
        def _postprocess_nodes(self, nodes, query_bundle=None):
            dated, undated = [], []
            for n in nodes:
                (dated if _has_date(n.node.get_content() or "") else undated).append(n)
            return dated + undated

    _DATE_BOOST = _DateBoost()
except Exception:
    _DATE_BOOST = None

def _wants_event_list(q: str) -> bool:
    ql = (q or "").lower()
    if "event" not in ql:
        return False
    return any(c in ql for c in ("upcoming", "coming up", "what", "which",
                                 "happening", "any", "list", "other"))


def _wants_date(q: str) -> bool:
    """Any question asking WHEN something happens. Dated chunks should outrank
    dateless descriptions for these. Without this, "when is Holmes is Your Home"
    returned the general description chunk and never the one carrying the date."""
    ql = (q or "").lower()
    return any(w in ql for w in ("when", "what date", "which date", "what day",
                                 "date of", "how soon"))

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

    if hub_override:
        return ["learning_support"], None, None

    if has_course_code and schedule_words:
        return ["course_offering"], None, term
    if has_course_code and description_words:
        return ["course_description"], None, None
    if calendar_words:
        return ["calendar", "advising", "general"], None, None
    if schedule_words and not rating_words and detect_professor(rtext):
        return ["course_offering"], None, term
    if schedule_words and not rating_words and extract_course_code(rtext):
        return ["course_offering"], None, term
    if schedule_words and not rating_words and term:
        return ["course_offering"], None, term
    if help_words:
        return ["learning_support"], None, None
    if rating_words:
        return ["faculty_reviews"], None, None

    if advising_words:
        return ["advising", "department", "general"], None, None
    if institute_words and not policy_words:
        return ["department", "general"], None, None
    if curriculum_words:
        return ["degree_map"], program, None
    if event_words:
        return ["event", "admissions", "club", "general"], None, None
    if club_words:
        return ["club"], None, None
    if faculty_words or detect_professor(question):
        return ["faculty", "faculty_reviews"], None, None
    if admissions_words:
        return ["admissions", "general"], None, None
    if policy_words:
        return ["policy", "general"], None, None
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
        if hits == len(parts) and hits > best_score:
            best, best_score = prof, hits
    if not best:
        for prof in KNOWN_PROFESSORS:
            clean = prof.lower().replace(",", " ").replace(".", " ").split()
            surname = clean[0] if clean else ""
            if len(surname) > 2 and (" " + surname + " ") in q:
                if best is None:
                    best = prof
                else:
                    return None
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
        parts = professor.split()
        if len(parts) == 2:
            variants = [professor, f"{parts[1]} {parts[0]}"]
            filter_list.append(MetadataFilter(key="professor", value=variants,
                                              operator=FilterOperator.IN))
        else:
            filter_list.append(MetadataFilter(key="professor", value=professor,
                                              operator=FilterOperator.EQ))
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
    return None

try:
    from langdetect import (detect as _langdetect, detect_langs as _langdetect_langs,
                            DetectorFactory as _LDFactory)
    _LDFactory.seed = 0
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
    for _ch in "?!.,;:()\"":
        ql = ql.replace(_ch, " ")
    ql = ql.replace("¿", " ¿ ").replace("¡", " ¡ ")
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
    best, best_score = None, 1
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
         "me", "tell", "give", "show", "i", "my", "get", "will", "many", "much", "going"}
_MORE = {"tell me more", "more", "go on", "and", "what else", "anything else",
         "continue", "more info", "more details"}
_RELATIVE = {"next", "one", "ones", "last", "first", "other", "another",
             "previous", "same", "upcoming", "each", "both", "all"}
_ATTRIBUTE = {"exam", "exams", "time", "times", "room", "rooms", "location",
              "locations", "credit", "credits", "instructor", "instructors",
              "professor", "professors", "teacher", "teachers", "section",
              "sections", "crn", "seat", "seats", "prerequisite", "prerequisites",
              "prereq", "prereqs", "schedule", "meet", "meets", "meeting", "offered",
              "teach", "teaches", "taught", "teaching", "instruct", "instructs"}

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
    if '"' in raw:
        return False
    words = ql.split()
    if set(words) & _ANAPHORA:
        return True
    content = [w for w in words if w not in _STOP and w not in _BARE_Q
               and w not in _RELATIVE and w not in _ATTRIBUTE]
    return not content

_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```")
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
    if len(cleaned) < 25:
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

    def _repeats(s: str) -> bool:
        for p in prev_sents:
            pl = p.lower()
            sm = difflib.SequenceMatcher(None, s, pl)
            if sm.ratio() > 0.8:
                return True
            if len(s) > 20 and sm.find_longest_match(0, len(s), 0, len(pl)).size / len(s) > 0.85:
                return True
        return False

    i = 0
    while i < len(ans_sents) - 1:
        if _repeats(ans_sents[i].lower()):
            i += 1
        else:
            break
    trimmed = " ".join(ans_sents[i:]).strip()
    return trimmed or answer

def _correct_typos(question: str) -> str:
    """Fix obvious typos before retrieval, so a misspelled word ('homlmes') still
    embeds near the right chunk. Works in any of the 20 languages because the LLM
    corrects in place. Best-effort: falls back to the ORIGINAL on any error or a
    suspicious result (empty, or far longer -> the model rambled/answered instead
    of just correcting)."""
    q = (question or "").strip()
    if len(q) < 4:
        return question
    prompt = (
        "You fix typos. Correct only obvious spelling and typing mistakes in the "
        "question below. Keep the SAME language, meaning, names and word order. Do "
        "not answer it, translate it, add or remove words, or change proper nouns. "
        "NEVER change a number, a course code (such as COP 2006), a year, or a "
        "date, even if it looks unusual. "
        "If nothing is misspelled, return it unchanged. Reply with ONLY the "
        "corrected question - no quotes, no explanation.\n\nQuestion: " + q
    )
    try:
        out = str(Settings.llm.complete(prompt)).strip().strip('"').strip()
    except Exception:
        return question
    if not out or len(out) > len(q) * 2 + 20:
        return question
    return out

def _condense_query(question: str, history) -> str:
    """Rewrite a follow-up into ONE standalone retrieval query using the recent
    conversation — resolving references ('it', 'the exams', 'each section', 'the
    next one', 'the professor') to the specific course / professor / event they
    point to. This is the robust successor to the keyword follow-up rules: it
    handles phrasings the word lists miss. Best-effort — returns the question
    unchanged when it's already self-contained or on any error, so it can never
    make retrieval worse.

    Skips the LLM call (returns as-is) when there's no history or the question
    already names its own course/professor, so the cost is paid only on the
    ambiguous follow-ups that actually need it."""
    if not history:
        return question
    if extract_course_code(question) or detect_professor(question):
        return question

    turns = []
    for h in history[-6:]:
        q = (h.get("question") or "").strip()
        a = (h.get("answer") or "").strip()
        if q:
            turns.append(f"Student: {q}")
        if a:
            turns.append(f"Assistant: {a[:300]}")
    convo = "\n".join(turns)
    if not convo:
        return question

    anchor_subject = ""
    for h in reversed(history):
        q = (h.get("question") or "")
        code = extract_course_code(q)
        prof = detect_professor(q)
        if code:
            anchor_subject = code
            break
        if prof:
            anchor_subject = prof
            break
    anchor_line = (f"\nThe subject the student is currently asking about is "
                   f"{anchor_subject}. Resolve pronouns like \"it\" to {anchor_subject} "
                   f"unless the latest question clearly names a different one.\n"
                   if anchor_subject else "\n")

    prompt = (
        "You rewrite the student's latest question into ONE standalone search "
        "query that makes sense on its own. Resolve every reference (it, that, the "
        "exams, each section, the next one, the professor) to the specific course "
        "code, professor, or event from the conversation. When the conversation "
        "mentions more than one course or professor, resolve references to the MOST "
        "RECENT one the student was asking about, not an earlier one. Keep the SAME "
        "language. Do not answer it, add facts, or explain. If it is already "
        "standalone, return it unchanged. Reply with ONLY the query."
        + anchor_line +
        f"\nConversation:\n{convo}\n\nLatest question: {question}\n\nStandalone query:"
    )
    try:
        out = str(Settings.llm.complete(prompt)).strip().strip('"').strip()
    except Exception:
        return question
    if not out or len(out) > len(question) * 6 + 80:
        return question
    return out

def _tense_term(question: str) -> str:
    ql = (question or "").lower()
    if not any(w in ql for w in ("teach", "instructor", "professor")):
        return ""
    ql_noc = re.sub(r"\b[a-z]{3}\s?\d{4}[a-z]?\b", " ", ql)
    if re.search(r"\b(20\d\d|spring|summer|fall|current|upcoming|next semester|"
                 r"this semester|current semester|next term|this term)\b", ql_noc):
        return ""
    if any(p in ql for p in ("going to", "gonna", "will ", "will be", "next")):
        return "upcoming"
    if any(p in ql for p in ("currently", "right now", "is teaching", "are teaching",
                             "teaches", "teaching")):
        return "current"
    return ""

def answer_question(question: str, history=None, correct=True):
    history = history or []
    raw_question = question
    if correct:
        question = _correct_typos(question)
    recent = " ".join(
        (turn.get("question", "") + " " + turn.get("answer", ""))
        for turn in history[-3:]
    )
    routing_text = question + " " + recent

    doc_types, program, term = route_query(question, routing_text)
    # Typo correction can delete a word from a named entity: the event
    # "When is Holmes is Your Home?" gets "corrected" to "Holmes Your Home"
    # (the doubled "is" looks like a stutter), which drops the event keyword and
    # sends "Holmes" to the faculty/building pool, so the dated event chunk is
    # never retrieved. Named-event/club routing is brittle to this, so when the
    # corrected question misses those bounded pools, re-route on the ORIGINAL
    # question, which still contains the intact entity name.
    if correct and raw_question != question and not (
            doc_types and ("event" in doc_types or "club" in doc_types)):
        raw_dt, raw_prog, raw_term = route_query(
            raw_question, raw_question + " " + recent)
        if raw_dt and ("event" in raw_dt or "club" in raw_dt):
            doc_types, program, term = raw_dt, raw_prog, raw_term

    course_code = None
    if doc_types in (["course_offering"], ["course_description"]):
        course_code = extract_course_code(question) or extract_course_code(routing_text)
    professor = None
    if doc_types and ("faculty" in doc_types or "faculty_reviews" in doc_types
                      or doc_types == ["course_offering"]):
        professor = detect_professor(question) or detect_professor(routing_text)
    if doc_types == ["course_offering"] and professor and not extract_course_code(question):
        course_code = None
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
    retrieval_query = question
    followup = _is_followup(question)
    if history and not followup:
        sched = any(w in question.lower() for w in kw.ALL_SCHEDULE)
        own = detect_professor(question) or extract_course_code(question)
        established = detect_professor(routing_text) or extract_course_code(routing_text)
        if sched and established and not own:
            followup = True
    if history:
        rewritten = _condense_query(question, history)
        if rewritten != question:
            retrieval_query = rewritten
            followup = True
        elif followup:
            prev_q = history[-1].get("question", "").strip()
            anchor = prev_q
            for h in reversed(history):
                hq = (h.get("question", "") or "").strip()
                if hq and (detect_professor(hq) or extract_course_code(hq) or not _is_followup(hq)):
                    anchor = hq
                    break
            retrieval_query = (anchor + " " + question).strip()

    if retrieval_query != question:
        doc_types, program, term = route_query(retrieval_query, retrieval_query)
        course_code = None
        if doc_types in (["course_offering"], ["course_description"]):
            course_code = extract_course_code(retrieval_query)
        professor = None
        if doc_types and ("faculty" in doc_types or "faculty_reviews" in doc_types
                          or doc_types == ["course_offering"]):
            professor = detect_professor(retrieval_query)
        if doc_types == ["course_offering"] and professor and not extract_course_code(retrieval_query):
            course_code = None

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
    tense_note = ""
    _tt = _tense_term(question)
    if _tt:
        # Only infer the term from tense when NO term is established anywhere.
        # Otherwise "who teaches each section" (present tense) would override a
        # Fall 2026 the student already named two turns ago and answer for the
        # current term instead.
        _known_term = detect_term(retrieval_query)
        if not _known_term:
            for h in history:
                if detect_term(h.get("question", "") or "") or detect_term(h.get("answer", "") or ""):
                    _known_term = True
                    break
        if _known_term:
            _tt = ""
    if _tt == "upcoming":
        tense_note = ("\n\nThe student's question is future tense (\"going to teach\") and names "
                      "no term, so answer for the UPCOMING term from the today's-date line above.")
    elif _tt == "current":
        tense_note = ("\n\nThe student's question is present tense (\"is teaching\"/\"teaches\") and "
                      "names no term, so answer for the CURRENT term from the today's-date line above.")
    _instr = (SYSTEM_PROMPT + date_directive + calendar_note + tense_note + lang_directive + history_block).replace("{", "{{").replace("}", "}}")
    qa_template = PromptTemplate(
        _instr
        + "\n\nContext information from FGCU Engineering pages is below.\n"
          "---------------------\n{context_str}\n---------------------\n"
          "Using that context, answer the student's question.\n"
          "Question: {query_str}\nAnswer: "
    )
    _is_calendar = bool(doc_types and "calendar" in doc_types)
    _active_reranker = _reranker_calendar if (_is_calendar and _reranker_calendar) else _reranker
    _post = [_active_reranker] if _active_reranker else []
    if _DATE_BOOST is not None and (_wants_event_list(question) or _wants_date(question)):
        _post.append(_DATE_BOOST)
    _post = _post or None

    def _run(dt, prog, trm, code, prof):
        try:
            return make_engine(dt, prog, trm, code, prof,
                               qa_template=qa_template,
                               postprocessors=_post).query(retrieval_query)
        except Exception as e:
            if _using_backup:
                raise
            _activate_backup(type(e).__name__)
            return make_engine(dt, prog, trm, code, prof,
                               qa_template=qa_template,
                               postprocessors=_post).query(retrieval_query)

    def _no_match(r):
        s = str(r).strip()
        return (not s) or s == "Empty Response" or not getattr(r, "source_nodes", None)

    _ABSTAIN_RX = re.compile(
        r"(don'?t have|do not have|no information|not sure|isn'?t any information|"
        r"is no information|not provided|not specified|couldn'?t find|could not find|"
        r"not available|unable to find)", re.I)

    def _abstained(r):
        return bool(_ABSTAIN_RX.search(str(r)))

    response = _run(doc_types, program, term, course_code, professor)

    if course_code and _no_match(response):
        response = _run(["course_offering", "course_description"],
                        program, None, course_code, None)
    if course_code and _no_match(response):
        response = _run(None, None, None, course_code, None)

    if _no_match(response):
        response = _run(None, None, None, None, None)

    # A filtered search can return chunks that are non-empty but wrong: the
    # metadata filter excludes the passage holding the answer, retrieval still
    # returns *something*, so _no_match is False and the fallbacks above never
    # fire. The model then truthfully reports that it has no information, even
    # though the answer is sitting in the index. If we filtered at all and the
    # model abstained, retry once with no filters and keep the relaxed answer
    # only when it actually resolves the question. Genuine unknowns still
    # abstain, because the unfiltered search will not find them either.
    _filtered = bool(doc_types or program or term or course_code or professor)
    if _filtered and _abstained(response):
        relaxed = _run(None, None, None, None, None)
        if not _no_match(relaxed) and not _abstained(relaxed):
            response = relaxed

    answer = _dedup_followup(_strip_code(str(response), ui_lang), history)
    return answer, ui_lang

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
            chat_history = chat_history[-6:]
        except Exception as e:
            print(f"\nError: {e}\n")

app = FastAPI()
_origins_env = os.getenv("ALLOWED_ORIGINS", "").strip()
_allowed_origins = [o.strip() for o in _origins_env.split(",") if o.strip()] or ["*"]
print(f"CORS allowed origins: {_allowed_origins}")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"]
)

TURNSTILE_SECRET = os.getenv("TURNSTILE_SECRET", "")
SESSION_SECRET   = os.getenv("SESSION_SECRET", "dev-only-change-me")
SESSION_TTL      = 2 * 60 * 60

def _make_session() -> str:
    """Signed, expiring token '<exp>.<hmac>'. Simple format (no JSON/base64) so a
    Vercel serverless function can mint the exact same token: Cloudflare is
    unreachable from this Space, so Turnstile is verified on Vercel and this
    backend only validates the resulting HMAC."""
    exp = str(int(time.time()) + SESSION_TTL)
    sig = hmac.new(SESSION_SECRET.encode(), exp.encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"

def _valid_session(token: str) -> bool:
    if not token or "." not in token:
        return False
    exp, sig = token.rsplit(".", 1)
    expected = hmac.new(SESSION_SECRET.encode(), exp.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        return int(exp) > int(time.time())
    except ValueError:
        return False

from collections import defaultdict, deque
_RL_WINDOW = 60
_RL_MAX = int(os.getenv("RATE_LIMIT_PER_MIN", "40"))
_rl_hits: "dict[str, deque]" = defaultdict(deque)

def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

def _rate_limited(ip: str) -> bool:
    now = time.time()
    dq = _rl_hits[ip]
    while dq and dq[0] < now - _RL_WINDOW:
        dq.popleft()
    if len(dq) >= _RL_MAX:
        return True
    dq.append(now)
    return False

async def require_human(request: Request, x_session: str = Header(default="")):
    """Gate the costly endpoints. Two layers: (1) a per-IP rate limit that always
    applies, and (2) a Turnstile session check when Turnstile is configured (no-op
    for local dev without TURNSTILE_SECRET)."""
    if _rate_limited(_client_ip(request)):
        raise HTTPException(status_code=429, detail="Too many requests — please slow down.")
    if not TURNSTILE_SECRET:
        return
    if not _valid_session(x_session):
        raise HTTPException(status_code=401, detail="Bot check required")

SUPABASE_URL   = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY   = os.getenv("SUPABASE_KEY", "")
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE", "ask_logs")
SUPABASE_ISSUES_TABLE = os.getenv("SUPABASE_ISSUES_TABLE", "issue_reports")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

def _check_admin(password: str) -> bool:
    """Constant-time password check for the admin dashboard endpoints."""
    if not ADMIN_PASSWORD:
        return False
    return hmac.compare_digest(str(password or ""), ADMIN_PASSWORD)

async def log_interaction(client_id: str, question: str, answer: str, language: str,
                          message_id: str = "", platform: str = "", browser: str = "",
                          user_agent: str = "", mode: str = "", corrected_question: str = ""):
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
                    "platform": platform or None,
                    "browser": browser or None,
                    "user_agent": (user_agent or "")[:500] or None,
                    "mode": mode or None,
                    "corrected_question": corrected_question or None,
                },
            )
    except Exception:
        pass

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
async def report(request: Request, body: dict = Body(default=None)):
    """Store a user-submitted issue report in Supabase."""
    data = body or {}
    description = (data.get("description") or "").strip()
    client_id = data.get("client_id") or ""
    mode = (data.get("mode") or "")
    platform = (data.get("platform", "") or "")[:40]
    browser = (data.get("browser", "") or "")[:40]
    user_agent = (request.headers.get("user-agent", "") if request else "")[:500]
    if not description:
        raise HTTPException(status_code=400, detail="Empty description")
    if len(description) > 4000:
        description = description[:4000]
    if not (SUPABASE_URL and SUPABASE_KEY):
        return {"ok": True}
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
                json={"client_id": client_id or None, "description": description, "mode": mode or None,
                      "platform": platform or None, "browser": browser or None, "user_agent": user_agent or None},
            )
        return {"ok": r.status_code in (200, 201, 204)}
    except Exception:
        return {"ok": False}

@app.post("/verify")
async def verify(body: dict = Body(default=None)):
    """Exchange a Turnstile token for a session token."""
    token = (body or {}).get("token", "")
    if not TURNSTILE_SECRET:
        return {"session": _make_session()}
    if not token:
        raise HTTPException(status_code=400, detail="Missing Turnstile token")
    try:
        transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
        async with httpx.AsyncClient(timeout=15, transport=transport) as client:
            resp = await client.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={"secret": TURNSTILE_SECRET, "response": token},
            )
        result = resp.json()
    except Exception as e:
        print(f"[verify] siteverify unreachable, failing open: {e!r}")
        return {"session": _make_session()}
    if not result.get("success"):
        codes = result.get("error-codes", [])
        print(f"[verify] siteverify rejected: {codes}")
        raise HTTPException(status_code=403, detail=f"Bot check failed: {codes}")
    try:
        return {"session": _make_session()}
    except Exception as e:
        print(f"[verify] make_session failed: {e!r}")
        raise HTTPException(status_code=500, detail=f"Session error: {e}")

@app.post("/ask")
async def ask(request: Request, background: BackgroundTasks, question: str = "", body: dict = Body(default=None), _human=Depends(require_human)):
    history = []
    client_id = ""
    message_id = ""
    platform = ""
    browser = ""
    mode = "text"
    if body:
        question = body.get("question", question) or question
        history = body.get("history", []) or []
        client_id = body.get("client_id", "") or ""
        message_id = body.get("message_id", "") or ""
        platform = (body.get("platform", "") or "")[:40]
        browser = (body.get("browser", "") or "")[:40]
        mode = (body.get("mode", "text") or "text")
    user_agent = request.headers.get("user-agent", "") if request else ""
    corrected_q = question if mode == "voice" else _correct_typos(question)
    answer = None
    language = "English"
    for attempt in range(2):
        try:
            answer, language = answer_question(corrected_q, history, correct=False)
            break
        except Exception:
            if attempt == 0:
                await asyncio.sleep(0.8)
                continue
            language = _safe_ui_lang(question)
            answer = _ERROR_TEXT.get(language, _ERROR_TEXT["English"])
    background.add_task(log_interaction, client_id, question, answer, language,
                        message_id, platform, browser, user_agent,
                        mode, corrected_q if corrected_q != question else "")
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
        return {"ok": True}
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

async def _sb_get(table: str, params: dict):
    """Read rows from a Supabase table via the REST API (service-role key)."""
    if not (SUPABASE_URL and SUPABASE_KEY):
        return []
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
            params=params,
        )
        if r.status_code == 200:
            return r.json()
        return []

@app.post("/admin/logs")
async def admin_logs(body: dict = Body(default=None)):
    """Return recent ask_logs rows for the dashboard. Requires the admin
    password. Filtering is done client-side in the dashboard; here we just
    return the most recent N rows."""
    data = body or {}
    if not _check_admin(data.get("password")):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        limit = int(data.get("limit", 3000))
    except (TypeError, ValueError):
        limit = 3000
    limit = max(1, min(limit, 10000))
    rows = await _sb_get(SUPABASE_TABLE, {
        "select": "created_at,client_id,message_id,question,answer,language,rating,platform,browser,mode,corrected_question",
        "order": "created_at.desc",
        "limit": str(limit),
    })
    return {"ok": True, "rows": rows}

@app.post("/admin/issues")
async def admin_issues(body: dict = Body(default=None)):
    """Return recent issue_reports rows for the dashboard. Requires the admin
    password."""
    data = body or {}
    if not _check_admin(data.get("password")):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        limit = int(data.get("limit", 1000))
    except (TypeError, ValueError):
        limit = 1000
    limit = max(1, min(limit, 5000))
    rows = await _sb_get(SUPABASE_ISSUES_TABLE, {
        "select": "created_at,client_id,description,mode,platform,browser",
        "order": "created_at.desc",
        "limit": str(limit),
    })
    return {"ok": True, "rows": rows}

LANG_CODES = {
    "English": "en", "Spanish": "es", "Portuguese": "pt", "French": "fr",
    "German": "de", "Italian": "it", "Russian": "ru", "Ukrainian": "uk",
    "Polish": "pl", "Greek": "el", "Dutch": "nl", "Swedish": "sv",
    "Turkish": "tr", "Chinese": "zh", "Tagalog": "tl", "Hindi": "hi",
    "Tamil": "ta", "Korean": "ko", "Japanese": "ja", "Arabic": "ar",
}

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
    filename = audio.filename or "audio.webm"
    content_type = audio.content_type or "audio/webm"
    form_data = {
        "model": "whisper-large-v3",
        "response_format": "json",
        "prompt": WHISPER_PROMPT,
    }
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

try:
    import edge_tts
    _EDGE_TTS_AVAILABLE = True
except ImportError:
    _EDGE_TTS_AVAILABLE = False

_elevenlabs_quota_hit = False

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
    text = _speakable(text)

    if not _elevenlabs_quota_hit:
        voice_id = "EXAVITQu4vr4xnSDxMaL"
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
            body = resp.text[:500]
            print(f"[/speak] ElevenLabs error {resp.status_code}: {body}")
            if _is_elevenlabs_quota_error(resp.status_code, body):
                print("[/speak] ElevenLabs quota exhausted -> switching to edge-tts for this run.")
                _elevenlabs_quota_hit = True
        except Exception as e:
            print(f"[/speak] ElevenLabs request failed ({e}) -> trying edge-tts.")

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

    return Response(content=b'{"error": "voice unavailable"}', status_code=503,
                    media_type="application/json")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "chat":
        chat()
    else:
        print("Run with: python main.py chat")
        print("Or start API with: uvicorn main:app --reload --port 8000")
