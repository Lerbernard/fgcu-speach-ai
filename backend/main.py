from fastapi import FastAPI, UploadFile, File, Form, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
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
import httpx
import keywords as kw

load_dotenv()

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
    trust_remote_code=True
)
Settings.chunk_size = 400
Settings.chunk_overlap = 50

print("Connecting to Groq (llama-3.3-70b-versatile)...")
Settings.llm = Groq(
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY")
)

print("Connecting to Pinecone...")
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
pinecone_index = pc.Index(os.getenv("PINECONE_INDEX_NAME"))
vector_store = PineconeVectorStore(pinecone_index=pinecone_index)
index = VectorStoreIndex.from_vector_store(vector_store)

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
- If you don't know, say so naturally, like "I'm not sure about that one"
- Keep answers concise but complete, in plain language — no bullet points unless you are naturally listing several items
- If a course is offered in multiple semesters, focus on the semester the student asked about

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
    policy_words       = any(w in q for w in kw.ALL_POLICY)
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
    if institute_words:
        return ["department", "general"], None, None
    if curriculum_words:
        return ["degree_map"], program, None
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
    # Student-life is checked before campus so "Holmes is Your Home" (an event)
    # routes to student life, while a bare "Holmes" / "where is..." → campus.
    if student_life_words:
        return ["student_life", "club", "general"], None, None
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
    Stored names are 'lastname firstname' (lowercase). A student may say them in
    either order ('Professor Paul Allen' or 'Allen'), so we check whether all the
    significant name words in a known entry appear in the question."""
    q = question.lower()
    # strip common titles so they don't interfere
    for title in ["professor", "prof", "dr.", "dr", "instructor", "teacher"]:
        q = q.replace(title, " ")
    best = None
    best_score = 0
    for prof in KNOWN_PROFESSORS:
        parts = [p for p in prof.split() if len(p) > 2]
        if not parts:
            continue
        hits = sum(1 for p in parts if p in q)
        # require every name part to be present (so "allen paul" needs both
        # 'allen' and 'paul'); a single distinctive surname also counts
        if hits == len(parts) and hits > best_score:
            best, best_score = prof, hits
    # fall back: a unique surname match (first word of stored name)
    if not best:
        for prof in KNOWN_PROFESSORS:
            surname = prof.split()[0] if prof.split() else ""
            if len(surname) > 2 and surname in q:
                if best is None:
                    best = prof
                else:
                    return None  # ambiguous surname; don't guess
    return best


def make_engine(doc_types, program, term, course_code=None, professor=None):
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
    if filter_list:
        filters = MetadataFilters(filters=filter_list, condition="and")
        return index.as_query_engine(similarity_top_k=20, filters=filters)
    return index.as_query_engine(similarity_top_k=20)


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
        if 0x0590 <= o <= 0x05FF: return "Hebrew"
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
    "ja": "Japanese", "ar": "Arabic", "he": "Hebrew", "iw": "Hebrew",
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
    # Distinctive function words per language. We deliberately avoid words that
    # look similar across languages (like "professor") to prevent an English
    # question from matching another language by accident.
    markers = {
        "Spanish": [" el ", " la ", " qué ", " quién ", " cómo ", " dónde ", " es ", " cuál ", " profesor ", "¿", "ñ",
                    " estoy ", " estás ", " está ", " muy ", " mis ", " siento ", " tengo ", " necesito ",
                    " ayuda ", " gracias ", " hola ", " quiero ", " soy "],
        "French": [" le ", " qui ", " est ", " quel ", " quelle ", " où ", " quels ", " professeur ", " bonjour ", "ç",
                   " je ", " suis ", " très ", " merci ", " j'ai ", " besoin ", " aide ", " avec ", " pour "],
        "Portuguese": [" quem ", " qual ", " onde ", " você ", " obrigado ", " disciplina ", " ã ",
                       " estou ", " muito ", " sinto ", " preciso ", " olá ", " sou ", " quero ", " não ", " ajuda "],
        "German": [" der ", " wer ", " ist ", " wie ", " wo ", " welche ", " kurs ", " danke ", " ß ",
                   " ich ", " bin ", " sehr ", " hallo ", " brauche ", " hilfe ", " und ", " nicht ", " für "],
        "Italian": [" il ", " chi ", " cosa ", " dove ", " professore ", " corso ", " grazie ",
                    " sono ", " molto ", " ciao ", " bisogno ", " aiuto ", " perché ", " sto "],
        "Dutch": [" het ", " wie ", " wat ", " waar ", " hoe ", " docent ", " bedankt ",
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


def _detected_language(q: str):
    """A POSITIVE language read for a single question, or None if nothing is
    reliable. Unlike guess_ui_language this does NOT default to English, so
    callers can fall back to the conversation's language for short follow-ups."""
    script_lang = detect_question_language(q)
    if script_lang:
        return "Russian" if script_lang.startswith("Russian") else script_lang
    return detect_language_name(q) or _markers_language(q)


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
        ui_lang = "Russian" if script_lang.startswith("Russian") else script_lang
    else:
        directive_lang = (detect_language_name(question) or _markers_language(question)
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
                "\n\nConversation so far (for context, to resolve references "
                "like 'he', 'she', 'that course'):\n" + "\n".join(lines)
            )
    prompt = (SYSTEM_PROMPT + lang_directive + history_block
              + "\n\nCurrent question: " + question)

    def _run(dt, prog, trm, code, prof):
        return make_engine(dt, prog, trm, code, prof).query(prompt)

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

    return str(response), ui_lang


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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)


@app.post("/ask")
async def ask(question: str = "", body: dict = Body(default=None)):
    # Accept either a query param (?question=) for backward compatibility, or a
    # JSON body {"question": ..., "history": [{"question":..,"answer":..}, ...]}.
    history = []
    if body:
        question = body.get("question", question) or question
        history = body.get("history", []) or []
    answer, language = answer_question(question, history)
    return {"answer": answer, "language": language}


# Whisper language codes for the supported languages (used when the user turns
# auto-detect OFF and picks a language, which improves accuracy with accents).
LANG_CODES = {
    "English": "en", "Spanish": "es", "Portuguese": "pt", "French": "fr",
    "German": "de", "Italian": "it", "Russian": "ru", "Ukrainian": "uk",
    "Polish": "pl", "Greek": "el", "Dutch": "nl", "Swedish": "sv",
    "Turkish": "tr", "Chinese": "zh", "Tagalog": "tl", "Hindi": "hi",
    "Tamil": "ta", "Korean": "ko", "Japanese": "ja", "Arabic": "ar",
    "Hebrew": "he",
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
async def transcribe(audio: UploadFile = File(...), language: str = Form("")):
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
    "Hebrew": "he-IL-HilaNeural",
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
async def speak(text: str):
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