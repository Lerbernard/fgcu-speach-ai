import sys

try:
    from main import answer_question
except Exception as e:  # missing keys, deps, or index connection
    print("Could not import main.py / initialize the backend.")
    print(f"  reason: {e}")
    print("  -> activate your venv and make sure .env has PINECONE_API_KEY and")
    print("     GROQ_API_KEY, and that the index has been ingested.")
    sys.exit(1)


# (question, [expected substrings — any one counts] or None, category)
# Every probe targets a REAL named thing confirmed to exist in the data.
PROBES = [
    # ── admissions ──────────────────────────────────────────────────────────
    ("What is Say Yes to the Nest?",
     ["admit", "student day", "fgcu"], "admissions"),
    ("How do I accept my admission offer to FGCU?",
     ["accept", "admission", "deposit", "enroll"], "admissions"),

    # ── student-life events ────────────────────────────────────────────────
    ("What is Holmes is Your Home?",
     ["event", "student", "holmes", "involve"], "student_life"),
    ("Tell me about EagleHacks.",
     ["hackathon", "event", "comput", "coding", "csse"], "student_life"),

    # ── clubs ────────────────────────────────────────────────────────────────
    ("Tell me about the Society of Women Engineers.",
     ["women", "engineer", "society", "club", "swe"], "club"),
    ("Is there a computer science club?",
     ["computer", "software", "club", "csse"], "club"),

    # ── student services ──────────────────────────────────────────────────────
    ("What is CAPS / Counseling and Psychological Services?",
     ["counsel", "psycholog", "mental", "239-590-7950"], "student_life"),
    ("What are the Basic Needs Initiatives at FGCU?",
     ["basic needs", "food", "resource", "bni"], "student_life"),

    # ── departments ──────────────────────────────────────────────────────────
    ("What is the DENDRITIC Institute?",
     ["data science", "artificial intelligence", "research", "institute"], "department"),
    ("Tell me about the Department of Computing and Software Engineering.",
     ["computing", "software", "department"], "department"),

    # ── programs ──────────────────────────────────────────────────────────────
    ("What does the Bioengineering B.S. program cover?",
     ["bioengineer", "degree", "program", "credit"], "program"),
    ("How does academic advising work in engineering?",
     ["advis", "appointment", "schedule"], "program"),

    # ── campus / building ──────────────────────────────────────────────────────
    ("What is Holmes Hall?",
     ["holmes", "hall", "building", "engineering"], "campus"),
    ("Where is the U.A. Whitaker College of Engineering located?",
     ["holmes", "located", "building", "campus"], "campus"),

    # ── learning support ──────────────────────────────────────────────────────
    ("What is the Learning Hub?",
     ["tutor", "academic support", "fellow", "learning hub", "239-745-4310"], "learning_support"),

    # ── policy ────────────────────────────────────────────────────────────────
    ("What is FGCU's institutional ethics and compliance policy?",
     ["ethic", "complian", "conduct", "report"], "policy"),

    # ── research ──────────────────────────────────────────────────────────────
    ("What research does the engineering college do?",
     ["research"], "research"),

    # ── multilingual (same named things, non-English wrapper) ─────────────────
    # Proper-noun events stay in English; we only check the answer isn't empty
    # and isn't a don't-know, since the answer itself comes back translated.
    ("¿Qué es Say Yes to the Nest?", None, "admissions/es"),
    ("Qu'est-ce que Holmes is Your Home ?", None, "student_life/fr"),
    ("¿Qué es el DENDRITIC Institute?", None, "department/es"),
]

# English don't-know phrasings the model uses when it can't answer.
DONT_KNOW = [
    "not sure", "don't know", "do not know", "couldn't find", "could not find",
    "i don't have", "i do not have", "no information", "not able to find",
    "i'm not certain", "unable to find",
]


def classify(answer, expected):
    a = (answer or "").strip()
    low = a.lower()
    if not a or low == "empty response" or len(a) < 15:
        return "EMPTY"
    if any(p in low for p in DONT_KNOW):
        return "WEAK"
    if expected and not any(e in low for e in expected):
        return "NOKW"
    return "OK"


def run():
    counts = {"OK": 0, "NOKW": 0, "WEAK": 0, "EMPTY": 0, "ERROR": 0}
    print("=" * 78)
    print("LIVE DATA-COVERAGE PROBE  (route -> retrieve -> answer)")
    print("=" * 78)
    for q, expected, cat in PROBES:
        try:
            answer, lang = answer_question(q)
        except Exception as e:
            counts["ERROR"] += 1
            print(f"[ERROR] {cat:16} {q}\n        {e}\n")
            continue
        verdict = classify(answer, expected)
        counts[verdict] += 1
        snippet = " ".join((answer or "").split())[:170]
        print(f"[{verdict:5}] {cat:16} ({lang})  {q}")
        print(f"        {snippet}{'...' if len(answer or '') > 170 else ''}\n")

    print("=" * 78)
    print("SUMMARY")
    print("-" * 78)
    print(f"  OK     {counts['OK']:3}   answered and mentioned an expected term")
    print(f"  NOKW   {counts['NOKW']:3}   answered, no expected term (soft — phrasing/translation)")
    print(f"  WEAK   {counts['WEAK']:3}   model said it doesn't know  <-- investigate")
    print(f"  EMPTY  {counts['EMPTY']:3}   nothing retrieved           <-- investigate")
    print(f"  ERROR  {counts['ERROR']:3}   exception while answering   <-- investigate")
    print("=" * 78)
    bad = counts["WEAK"] + counts["EMPTY"] + counts["ERROR"]
    if bad == 0:
        print("All probes returned a substantive answer. Coverage looks good.")
    else:
        print(f"{bad} probe(s) did not return a usable answer — see the marked lines above.")
        print("If many are EMPTY, re-run ingest.py so the new doc_type labels are in the index.")
    return bad


if __name__ == "__main__":
    sys.exit(1 if run() else 0)