# -*- coding: utf-8 -*-
"""
test_routing.py — Automated language QA for the "Ask the Eagle" router.

WHAT THIS DOES
  Exercises the REAL routing + detection logic from main.py
  (route_query, extract_course_code, detect_term, detect_professor,
   detect_question_language, guess_ui_language) against a battery of
   multilingual questions, and reports which ones route as expected.

WHY IT NEEDS NO API KEYS / NETWORK
  main.py connects to Pinecone/Groq and loads a HuggingFace model at import.
  Before importing it, this script installs lightweight stand-ins for those
  external libraries (and FastAPI), so importing main has no side effects.
  The routing/detection functions themselves are pure Python over keywords.py,
  so they run exactly as in production. The professor list (normally loaded
  from Pinecone) is replaced with a small fixed list below.

HOW TO RUN
  Put this file in your backend/ folder (next to main.py and keywords.py):
      python test_routing.py
  Optional: python test_routing.py --verbose   (print every case, incl. passes)

HOW TO READ RESULTS
  [PASS]  routed as expected
  [FAIL]  routed wrong  -> a real bug to fix (exit code becomes 1)
  [GAP]   a KNOWN limitation we documented; still behaving as the limitation
          predicts (NOT counted as failure). These are the language gaps to fix
          in keywords.py / main.py.
  [FIXED] a case marked as a known gap that now PASSES -> the gap closed; you
          can remove its known_gap flag.

  The FINDINGS list at the end collects every [GAP]/[FIXED] so you have a
  ready-made "language issues" checklist (useful for the report).

NOTE
  This tests ROUTING and DETECTION only. It does NOT test answer text, answer
  language fidelity, or STT/TTS — those need the live model and are a separate
  check.
"""

import sys
import types
import importlib
import io
import contextlib
from unittest.mock import MagicMock


# ───────────────────────────────────────────────────────────────────────────
# 1) Install stand-ins for external libraries BEFORE importing main.py
# ───────────────────────────────────────────────────────────────────────────
def _install_stubs():
    def mod(name):
        m = types.ModuleType(name)
        sys.modules[name] = m
        return m

    # --- llama_index.* (only attribute access / construction happens at import)
    li = mod("llama_index")
    li_core = mod("llama_index.core")
    li_core.VectorStoreIndex = MagicMock(name="VectorStoreIndex")
    li_core.Settings = MagicMock(name="Settings")           # allows attr assignment
    li.core = li_core

    li_vs = mod("llama_index.core.vector_stores")
    li_vs.MetadataFilters = MagicMock(name="MetadataFilters")
    li_vs.MetadataFilter = MagicMock(name="MetadataFilter")
    li_vs.FilterOperator = MagicMock(name="FilterOperator")
    li_core.vector_stores = li_vs

    li_vstores = mod("llama_index.vector_stores")
    li_pc = mod("llama_index.vector_stores.pinecone")
    li_pc.PineconeVectorStore = MagicMock(name="PineconeVectorStore")
    li_vstores.pinecone = li_pc
    li.vector_stores = li_vstores

    li_emb = mod("llama_index.embeddings")
    li_hf = mod("llama_index.embeddings.huggingface")
    li_hf.HuggingFaceEmbedding = MagicMock(name="HuggingFaceEmbedding")  # no model download
    li_emb.huggingface = li_hf
    li.embeddings = li_emb

    li_llms = mod("llama_index.llms")
    li_groq = mod("llama_index.llms.groq")
    li_groq.Groq = MagicMock(name="Groq")
    li_llms.groq = li_groq
    li.llms = li_llms

    # --- pinecone: Pinecone(...).Index(...).query(...) -> {"matches": []}
    pc_mod = mod("pinecone")

    class _Index:
        def query(self, *a, **k):
            return {"matches": []}   # -> KNOWN_PROFESSORS loads empty; we override below

    class _Pinecone:
        def __init__(self, *a, **k):
            pass

        def Index(self, *a, **k):
            return _Index()

    pc_mod.Pinecone = _Pinecone

    # --- dotenv
    dv = mod("dotenv")
    dv.load_dotenv = lambda *a, **k: None

    # --- httpx (only imported at top of main.py)
    mod("httpx")

    # --- fastapi (so @app.post decorators and Body()/File()/Form() defaults work)
    fa = mod("fastapi")

    class _App:
        def add_middleware(self, *a, **k):
            pass

        def _decorator(self, *a, **k):
            def deco(fn):
                return fn
            return deco

        post = _decorator
        get = _decorator

    fa.FastAPI = lambda *a, **k: _App()
    fa.UploadFile = object
    fa.File = lambda *a, **k: None
    fa.Form = lambda *a, **k: None
    fa.Body = lambda *a, **k: None

    fa_mw = mod("fastapi.middleware")
    fa_cors = mod("fastapi.middleware.cors")
    fa_cors.CORSMiddleware = object
    fa_mw.cors = fa_cors
    fa.middleware = fa_mw

    fa_resp = mod("fastapi.responses")
    fa_resp.Response = object
    fa.responses = fa_resp


_install_stubs()

# Import the real module (silence its startup prints) ------------------------
with contextlib.redirect_stdout(io.StringIO()):
    main = importlib.import_module("main")

# Replace the (empty) professor list with a fixed stand-in. In production this
# is loaded from Pinecone; format is "lastname firstname", lowercase.
main.KNOWN_PROFESSORS = [
    "allen paul",      # used for both name-order tests (the RateMyProf bug)
    "buckley first",   # placeholder first names; surname is what we match on
    "sahiner first",
    "tsegaye first",
    "ciris first",
    "dhakal first",
    "ahuja first",
]


# ───────────────────────────────────────────────────────────────────────────
# 2) Helpers that mirror how production calls the router
# ───────────────────────────────────────────────────────────────────────────
def route(question, history=None):
    """Replicates answer_question()'s routing_text construction, then routes."""
    history = history or []
    recent = " ".join(
        (t.get("question", "") + " " + t.get("answer", "")) for t in history[-3:]
    )
    routing_text = question + " " + recent
    doc_types, program, term = main.route_query(question, routing_text)
    return doc_types, program, term


# Expected doc_type shortcuts (must match the EXACT lists route_query returns)
CO = ["course_offering"]
CD = ["course_description"]
LS = ["learning_support"]
RV = ["faculty_reviews"]
GE = ["general"]
DM = ["degree_map"]
CL = ["club"]
FAC = ["faculty", "faculty_reviews"]
GEN3 = ["general", "degree_map", "research"]
NONE = None


# ───────────────────────────────────────────────────────────────────────────
# 3) ROUTING test cases
#    fields: (lang, question, expect_doc_types, expect_term, history, gap, note)
#    history: list of {"question","answer"} or None
# ───────────────────────────────────────────────────────────────────────────
HIST_COP1500 = [{"question": "Tell me about COP 1500", "answer": "It is Intro to Computer Science."}]
HIST_COP1500_AR = [{"question": "أخبرني عن COP 1500", "answer": "إنها مقدمة في علوم الحاسوب."}]

ROUTING_CASES = [
    # --- English backbone: one case per route -------------------------------
    ("en", "How do I use the Learning Hub?", LS, None, None, False, "hub override beats help"),
    ("en", "Is COP 1500 offered in fall 2026?", CO, "fall 2026", None, False, "course code + schedule"),
    ("en", "What is COP 2006 about?", CD, None, None, False, "course code + description"),
    ("en", "What does Professor Allen teach?", CO, None, None, False, "professor-teaches route"),
    ("en", "Who teaches it in fall 2026?", CO, "fall 2026", HIST_COP1500, False, "course code from history"),
    ("en", "Where can I get tutoring?", LS, None, None, False, "help route"),
    ("en", "What do students say about Professor Buckley?", RV, None, None, False, "rating route"),
    ("en", "Tell me about the Dendritic Institute.", GE, None, None, False, "institute -> general"),
    ("en", "What courses do I need for junior year?", DM, None, None, False, "curriculum route"),
    ("en", "Is there a robotics club?", CL, None, None, False, "club route"),
    ("en", "Who are the professors in software engineering?", FAC, None, None, False, "faculty route"),
    ("en", "Who is Paul Allen?", FAC, None, None, False,
     "bare-name query -> faculty even without the word 'professor'"),
    ("en", "Tell me about Allen.", FAC, None, None, False,
     "name without a faculty keyword -> faculty"),
    ("en", "What's the weather today?", NONE, None,
     [{"question": "Who is Paul Allen?", "answer": "He is a professor."}],
     False, "unrelated follow-up must NOT be hijacked to faculty by history"),
    ("en", "How do I apply for admission?", GEN3, None, None, False, "general route"),
    ("en", "Hello, how are you?", NONE, None, None, False, "greeting -> no route"),
    ("en", "What's the weather today?", NONE, None, None, False, "off-topic -> no route"),

    # --- Precedence / negative checks ---------------------------------------
    ("en", "I want to meet my advisor about research.", GEN3, None, None, False,
     "'meet' alone (no prof/code) must NOT hit schedule"),
    ("en", "Is he any good?", RV, None,
     [{"question": "What does Professor Allen teach?", "answer": "He teaches COT 3400."}],
     False, "casual rating phrasing 'any good' -> reviews (was a dead-end before)"),
    ("en", "What does Professor Allen teach, and is he a good professor?", RV, None, None, False,
     "rating short-circuits teach route (by design) - compound Q loses teach intent"),

    # --- professor-teaches across languages (schedule verb + named prof) ----
    ("es", "¿Qué enseña el profesor Allen?", CO, None, None, False, "es enseña"),
    ("pt", "O que o professor Allen ensina?", CO, None, None, False, "pt ensina"),
    ("fr", "Qu'enseigne le professeur Allen ?", CO, None, None, False, "fr enseigne"),
    ("de", "Was unterrichtet Professor Allen?", CO, None, None, False, "de unterrichtet (the fixed bug)"),
    ("de", "Was lehrt Professor Allen?", CO, None, None, False, "de lehrt"),
    ("it", "Cosa insegna il professore Allen?", CO, None, None, False, "it insegna"),
    ("ru", "Что преподает профессор Allen?", CO, None, None, False, "ru преподает"),
    ("pl", "Czego uczy profesor Allen?", CO, None, None, False, "pl uczy"),
    ("el", "Τι διδάσκει ο καθηγητής Allen;", CO, None, None, False, "el διδάσκει"),
    ("sv", "Vad undervisar professor Allen?", CO, None, None, False, "sv undervisar"),
    ("zh", "Allen教授教什么？", CO, None, None, False, "zh 教"),
    ("ar", "ماذا يدرّس الأستاذ Allen؟", CO, None, None, False, "ar يدرّس"),
    ("ko", "Allen 교수는 무엇을 가르치나요?", CO, None, None, False, "ko 가르치 stem matches conjugation"),
    ("hi", "प्रोफेसर Allen क्या पढ़ाता है?", CO, None, None, False, "hi पढ़ाता (informal form, listed)"),
    ("ja", "Allen教授は何を教える？", CO, None, None, False, "ja 教える (dictionary form, listed)"),

    # --- Teaching-verb forms now covered (regression guards for the fixes) ---
    ("tr", "Profesör Allen hangi dersi veriyor?", CO, None, None, False,
     "tr: added 'veriyor'/'okutuyor' so 'hangi dersi veriyor' routes to offerings"),
    ("hi", "प्रोफेसर Allen क्या पढ़ाते हैं?", CO, None, None, False,
     "hi: added respectful form 'पढ़ाते'"),
    ("ja", "Allen教授は何を教えますか？", CO, None, None, False,
     "ja: added '担当'; polite form also routes via the shared CJK '教'"),
    ("nl", "Welke vakken doceert professor Allen?", CO, None, None, False,
     "nl: added 'doceert'"),
    ("es", "¿Qué materias dicta el profesor Allen?", CO, None, None, False,
     "es: added 'imparte'/'dicta'"),
    ("pt", "Quais disciplinas o professor Allen leciona?", CO, None, None, False,
     "pt: added 'leciona'/'dá aula'"),

    # --- description across languages (always needs a course code) ----------
    ("es", "¿Qué es COP 2006?", CD, None, None, False, "es qué es"),
    ("fr", "Qu'est-ce que COP 2006 ?", CD, None, None, False, "fr qu'est-ce"),
    ("de", "Was ist COP 2006?", CD, None, None, False, "de was ist"),
    ("zh", "COP 2006 是什么？", CD, None, None, False, "zh 是什么"),
    ("ar", "ما هو COP 2006؟", CD, None, None, False, "ar ما هو"),

    # --- rating across languages --------------------------------------------
    ("es", "¿Qué dicen los estudiantes sobre el profesor Buckley?", RV, None, None, False, "es rating"),
    ("de", "Was sagen die Studenten über Professor Buckley?", RV, None, None, False, "de rating"),
    ("ja", "Buckley教授について学生はどう思いますか？", RV, None, None, False, "ja rating 学生はどう"),

    # --- help across languages ----------------------------------------------
    ("es", "¿Dónde puedo obtener ayuda con las clases?", LS, None, None, False, "es help"),
    ("fr", "Où puis-je obtenir de l'aide pour les cours ?", LS, None, None, False, "fr help"),

    # --- curriculum / club / general / institute in other languages ---------
    ("es", "¿Qué cursos necesito para el tercer año?", DM, None, None, False, "es curriculum"),
    ("de", "Welche Kurse brauche ich im dritten Jahr?", DM, None, None, False, "de curriculum (welche kurse)"),
    ("fr", "Y a-t-il un club de robotique ?", CL, None, None, False, "fr club"),
    ("de", "Gibt es einen Roboter-Verein?", CL, None, None, False, "de club (verein)"),
    ("es", "¿Cómo solicito la admisión?", GEN3, None, None, False, "es general (admisión)"),
    ("fr", "Comment postuler pour l'admission ?", GEN3, None, None, False, "fr general"),

    # --- course-from-history follow-up in Arabic (the regression bug) -------
    ("ar", "من يدرّسها في خريف 2026؟", CO, "fall 2026", HIST_COP1500_AR, False,
     "ar follow-up: course code from history + season"),
]


# ───────────────────────────────────────────────────────────────────────────
# 4) DETECTOR test cases: (fn_name, label, input, expected, gap, note)
# ───────────────────────────────────────────────────────────────────────────
DETECTOR_CASES = [
    # extract_course_code
    ("extract_course_code", "code", "Tell me about COP 1500", "cop 1500", False, ""),
    ("extract_course_code", "code", "COP1500 with no space", "cop 1500", False, "regex allows zero space"),
    ("extract_course_code", "code", "EGN 3331C mechanics of materials", "egn 3331c", False, "trailing letter"),
    ("extract_course_code", "code", "Is it offered in the fall of 2026?", None, False,
     "regression: a year must NOT be read as a course code"),
    ("extract_course_code", "code", "What's in the 2026 catalog?", None, False,
     "'the 2026' now rejected via the non-subject prefix blocklist"),

    # detect_term  (note: season comes back lowercase, e.g. 'fall 2026')
    ("detect_term", "term", "is it offered in fall 2026", "fall 2026", False, ""),
    ("detect_term", "term", "spring 2025 classes", "spring 2025", False, ""),
    ("detect_term", "term", "what about next year", None, False, "no season word"),
    ("detect_term", "term", "is it in the fall", None, False, "season but no year"),

    # detect_question_language  (None for Latin scripts; a name for non-Latin)
    ("detect_question_language", "lang", "What does the professor teach?", None, False, "Latin -> None"),
    ("detect_question_language", "lang", "Qu'enseigne le professeur ?", None, False,
     "regression: French is Latin -> None (was wrongly forced to English)"),
    ("detect_question_language", "lang", "ما هو هذا؟", "Arabic", False, ""),
    ("detect_question_language", "lang", "Что преподает он?", "Russian or Ukrainian", False, ""),
    ("detect_question_language", "lang", "Πότε γίνεται;", "Greek", False, ""),
    ("detect_question_language", "lang", "क्या पढ़ाते हैं?", "Hindi", False, ""),
    ("detect_question_language", "lang", "この授業について教えて", "Japanese", False, "leading kana -> Japanese"),
    ("detect_question_language", "lang", "教授は何を教えますか", "Japanese", False,
     "kana is checked before the CJK range, so kanji-leading Japanese -> Japanese"),

    # detect_professor  (KNOWN_PROFESSORS set above; 'allen paul')
    ("detect_professor", "prof", "What does Paul Allen teach?", "allen paul", False, "both name parts"),
    ("detect_professor", "prof", "What does Allen Paul teach?", "allen paul", False, "reversed order (the reviews bug)"),
    ("detect_professor", "prof", "Tell me about Professor Allen", "allen paul", False, "surname-only fallback"),
    ("detect_professor", "prof", "Who is the best teacher here?", None, False, "no name present"),

    # guess_ui_language  (drives UI text only)
    ("guess_ui_language", "ui", "¿Quién es el profesor?", "Spanish", False, ""),
    ("guess_ui_language", "ui", "Что преподает он?", "Russian", False, "Cyrillic bucket -> Russian"),
    ("guess_ui_language", "ui", "How are you?", "English", False, "default"),
]


# ───────────────────────────────────────────────────────────────────────────
# 5) Runner
# ───────────────────────────────────────────────────────────────────────────
def main_run(verbose=False):
    counts = {"PASS": 0, "FAIL": 0, "GAP": 0, "FIXED": 0}
    findings = []
    fails = []

    def classify(ok, gap):
        if ok and not gap:
            return "PASS"
        if ok and gap:
            return "FIXED"
        if not ok and gap:
            return "GAP"
        return "FAIL"

    print("=" * 78)
    print("ROUTING")
    print("=" * 78)
    for lang, q, exp, exp_term, hist, gap, note in ROUTING_CASES:
        doc_types, _program, term = route(q, hist)
        ok = (doc_types == exp) and (exp_term is None or term == exp_term)
        tag = classify(ok, gap)
        counts[tag] += 1
        if tag == "FAIL":
            fails.append((lang, q, exp, doc_types, exp_term, term, note))
        if tag in ("GAP", "FIXED"):
            findings.append((tag, lang, q, note))
        if verbose or tag in ("FAIL", "GAP", "FIXED"):
            got = doc_types if exp_term is None else f"{doc_types} term={term!r}"
            want = exp if exp_term is None else f"{exp} term={exp_term!r}"
            print(f"[{tag:5}] {lang:3} | {q}")
            if tag != "PASS":
                print(f"         expected: {want}")
                print(f"         got:      {got}")
                if note:
                    print(f"         note:     {note}")

    print()
    print("=" * 78)
    print("DETECTORS")
    print("=" * 78)
    for fn_name, label, inp, exp, gap, note in DETECTOR_CASES:
        fn = getattr(main, fn_name)
        got = fn(inp)
        ok = (got == exp)
        tag = classify(ok, gap)
        counts[tag] += 1
        if tag == "FAIL":
            fails.append((label, inp, exp, got, None, None, f"{fn_name}: {note}"))
        if tag in ("GAP", "FIXED"):
            findings.append((tag, label, inp, f"{fn_name}: {note}"))
        if verbose or tag in ("FAIL", "GAP", "FIXED"):
            print(f"[{tag:5}] {fn_name}({inp!r})")
            if tag != "PASS":
                print(f"         expected: {exp!r}")
                print(f"         got:      {got!r}")
                if note:
                    print(f"         note:     {note}")

    # Summary -----------------------------------------------------------------
    total = sum(counts.values())
    print()
    print("=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"  total   {total}")
    print(f"  PASS    {counts['PASS']}")
    print(f"  FAIL    {counts['FAIL']}   (unexpected wrong routing -> fix these)")
    print(f"  GAP     {counts['GAP']}    (known language limitations, behaving as documented)")
    print(f"  FIXED   {counts['FIXED']}  (a known gap now passes -> remove its known_gap flag)")

    if findings:
        print()
        print("-" * 78)
        print("FINDINGS (language issues to address in keywords.py / main.py)")
        print("-" * 78)
        for tag, lang, q, note in findings:
            print(f"  [{tag}] {lang}: {q}")
            print(f"         -> {note}")

    if fails:
        print()
        print("-" * 78)
        print("FAILURES (unexpected)")
        print("-" * 78)
        for item in fails:
            print(f"  {item[0]} | {item[1]}")
            print(f"     expected {item[2]!r}, got {item[3]!r}  | {item[6]}")

    print()
    # Exit non-zero only on UNEXPECTED failures, so this can gate CI later.
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    sys.exit(main_run(verbose=verbose))