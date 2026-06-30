#!/usr/bin/env python3
"""
test_qwen.py  -  Is qwen/qwen3.6-27b good enough for Ask the Eagle?

Run this against the live backend AFTER switching main.py to the Qwen model.
It scores the things that would actually disqualify a model for this app:

  1. FACTS        - known answers come back correct (Islam's courses, fall start
                    date, programs, etc.). Wrong facts = disqualifying.
  2. LANGUAGE     - multilingual questions report the right language label.
  3. FOLLOW-UPS   - subject carries across turns (right professor) and answers
                    don't repeat the previous answer.
  4. GUARDRAILS   - homework/coding questions are refused, no code leaks through.
  5. REASONING    - NO chain-of-thought leaks into answers (Qwen is a reasoning
                    model; in non-thinking mode it should never show "thinking").
  6. LATENCY      - response times, so you can compare speed vs gpt-oss-120b.

At the end it prints a per-category scorecard and a GOOD ENOUGH / NEEDS REVIEW
verdict with reasons.

USAGE
-----
  uvicorn main:app --port 8080          # with Qwen active in main.py
  python test_qwen.py
  python test_qwen.py --base http://localhost:8080 --delay 2 --label "Qwen 3.6 27B"
"""

import argparse
import difflib
import json
import re
import statistics
import sys
import time
import urllib.error
import urllib.request

# ───────────────────────────── test data ─────────────────────────────
# FACTS: (question, [substrings], mode) — mode "any" = at least one must appear,
# "all" = all must appear (case-insensitive). These are verifiable for FGCU.
ISLAM_CODES = ["COP 3350", "CEN 4721", "COT 5405", "CAP 5415", "CAI 6930"]
FACTS = [
    ("What classes does Professor Islam teach?", ISLAM_CODES, "any"),
    ("When do fall classes start?",              ["17", "aug"], "all"),
    ("When does add/drop end for the fall?",     ["21"], "any"),
    ("What engineering programs does FGCU offer?", ["software", "engineering"], "all"),
    ("Tell me about the software engineering program.", ["software"], "any"),
    ("Who is Professor Islam?",                  ["islam"], "any"),
]

# CORE_QUALITY: (question, [keywords any]) — answer must be non-empty & on-topic.
CORE_QUALITY = [
    ("Who can I talk to about academic advising?", ["advis"]),
    ("What clubs can I join as an engineering student?", ["club", "society", "organization", "asce", "ieee"]),
    ("How do I apply to the engineering program?", ["appl", "admiss"]),
    ("Where is the engineering building?", ["holmes", "hall", "building"]),
    ("What is COP 3003?", ["program", "cop 3003", "course"]),
    ("Tell me about research opportunities.", ["research"]),
    ("What math courses will I take as a freshman?", ["mac", "calculus", "math"]),
    ("How many credits do I need to graduate?", ["credit"]),
]

# LANGS: (expected_language, question)
LANGS = [
    ("Spanish",    "¿Qué programas de ingeniería ofrece FGCU?"),
    ("French",     "Quels programmes d'ingénierie propose FGCU ?"),
    ("German",     "Welche Ingenieurstudiengänge bietet die FGCU an?"),
    ("Portuguese", "Quais programas de engenharia a FGCU oferece?"),
    ("Italian",    "Quali programmi di ingegneria offre la FGCU?"),
    ("Chinese",    "FGCU 提供哪些工程专业？"),
    ("Japanese",   "FGCUはどんな工学プログラムを提供していますか？"),
    ("Arabic",     "ما هي برامج الهندسة التي تقدمها FGCU؟"),
]

# CONVOS: each turn (expected_lang, question, gloss). Tests subject-carry + no-repeat.
CONVOS = [
    [
        ("English", "Who is Professor Islam?", "who is he"),
        ("English", "What classes does he teach?", "his classes (follow-up)"),
        ("English", "Which of those is in the fall?", "which in fall (follow-up)"),
    ],
    [
        ("Spanish", "¿Quién es el profesor Islam?", "who is he"),
        ("Spanish", "¿Qué clases enseña?", "his classes (follow-up)"),
    ],
]

# GUARDRAILS: (question, kind) — should be refused / contain no code.
GUARDRAILS = [
    ("Write me a Python function that sorts a list of numbers.", "code"),
    ("Can you do my calculus homework for me?", "homework"),
]

# Reasoning-leak signatures. HARD = explicit thinking tags (definite leak).
HARD_LEAK = [r"<\s*/?\s*think", r"<\s*/?\s*reasoning", r"◁think▷", r"<\s*/?\s*analysis"]
# SOFT = thinking-out-loud phrasing that shouldn't appear in a finished answer.
SOFT_LEAK = [
    r"\bthe user is asking\b", r"\blet me think\b", r"\blet me analyze\b",
    r"\bi need to figure out\b", r"\bchain of thought\b", r"\bokay, so\b",
    r"\blet me check the context\b", r"\breasoning:\b", r"\bas an ai\b",
    r"\bi'?ll start by\b", r"\bfirst,? i\b",
]

# ───────────────────────────── output ─────────────────────────────
class C:
    HEAD="\033[95m"; CYAN="\033[96m"; GREEN="\033[92m"; YEL="\033[93m"
    RED="\033[91m"; DIM="\033[2m"; BOLD="\033[1m"; END="\033[0m"
    @classmethod
    def off(cls):
        for k in ("HEAD","CYAN","GREEN","YEL","RED","DIM","BOLD","END"): setattr(cls,k,"")
OK = lambda: f"{C.GREEN}PASS{C.END}"
NO = lambda: f"{C.RED}FAIL{C.END}"
WARN = lambda: f"{C.YEL}WARN{C.END}"

def short(t, n=150):
    t = " ".join((t or "").split())
    return t if len(t) <= n else t[:n] + "…"

def has_any(text, subs):
    t = (text or "").lower()
    return any(s.lower() in t for s in subs)

def has_all(text, subs):
    t = (text or "").lower()
    return all(s.lower() in t for s in subs)

def code_in(text, code):
    return code.lower().replace(" ", "") in (text or "").lower().replace(" ", "")

def sentences(text):
    return [p.strip() for p in re.split(r"(?<=[.!?。！？])\s*", (text or "").strip()) if p.strip()]

def repeats(prev, ans):
    a, p = sentences(ans), sentences(prev)
    if not a or not p:
        return False
    return any(difflib.SequenceMatcher(None, a[0].lower(), s.lower()).ratio() > 0.8 for s in p)

def leak_check(text):
    """Return ('hard'|'soft'|None, matched_pattern)."""
    low = (text or "").lower()
    for pat in HARD_LEAK:
        if re.search(pat, low):
            return "hard", pat
    for pat in SOFT_LEAK:
        if re.search(pat, low):
            return "soft", pat
    return None, None

def has_code(text):
    return "```" in (text or "") or bool(re.search(r"\bdef \w+\s*\(", text or ""))

# ───────────────────────────── core ─────────────────────────────
def ask_once(base, q, history, timeout):
    payload = json.dumps({"question": q, "history": history,
                          "client_id": "qa-test", "message_id": "qa"}).encode("utf-8")
    req = urllib.request.Request(base.rstrip("/") + "/ask", data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8"))
    dt = time.time() - t0
    return d.get("answer", ""), d.get("language", ""), dt

def ask(base, q, history, timeout, retries, delay):
    last = None
    for attempt in range(1, retries + 2):
        try:
            return ask_once(base, q, history, timeout)
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 500 and attempt <= retries:
                time.sleep(delay * attempt); continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            if attempt <= retries:
                time.sleep(delay * attempt); continue
            raise
    raise last


def main():
    ap = argparse.ArgumentParser(description="Quality test for the Qwen model.")
    ap.add_argument("--base", default="http://localhost:8080")
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--label", default="Qwen 3.6 27B")
    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args()
    if args.no_color or not sys.stdout.isatty():
        C.off()

    print(f"{C.BOLD}Ask the Eagle - model fitness test: {args.label}{C.END}")
    print(f"{C.DIM}backend: {args.base}{C.END}")
    try:
        ask_once(args.base, "hello", [], min(args.timeout, 15))
    except urllib.error.URLError as e:
        print(f"\n{C.RED}Could not reach backend. Start it: uvicorn main:app --port 8080{C.END}\n{C.DIM}({e}){C.END}")
        sys.exit(1)
    except Exception:
        pass

    tally = {k: 0 for k in ("fact_p","fact_t","qual_p","qual_t","lang_p","lang_t",
                            "subj_p","subj_t","rep_p","rep_t","guard_p","guard_t",
                            "hard_leak","soft_leak","errors")}
    latencies = []

    def record_leak(ans, where):
        kind, pat = leak_check(ans)
        if kind == "hard":
            tally["hard_leak"] += 1
            print(f"      {C.RED}REASONING LEAK (hard){C.END} [{where}] matched {pat!r}")
        elif kind == "soft":
            tally["soft_leak"] += 1
            print(f"      {WARN()} possible reasoning text [{where}] matched {pat!r}")

    # 1. FACTS
    print(f"\n{C.HEAD}{C.BOLD}== 1. Factual accuracy =={C.END}")
    for q, subs, mode in FACTS:
        print(f"\n  {C.BOLD}{q}{C.END}")
        try:
            ans, lang, dt = ask(args.base, q, [], args.timeout, args.retries, args.delay)
            latencies.append(dt)
        except Exception as e:
            tally["errors"] += 1; print(f"    {NO()} ERROR: {e}"); time.sleep(args.delay); continue
        ok = has_all(ans, subs) if mode == "all" else has_any(ans, subs)
        tally["fact_t"] += 1; tally["fact_p"] += int(ok)
        print(f"    {OK() if ok else NO()+f' (missing {subs})'}  {C.DIM}{dt:.1f}s{C.END}")
        print(f"    {C.DIM}{short(ans)}{C.END}")
        record_leak(ans, "facts")
        time.sleep(args.delay)

    # 2. CORE QUALITY
    print(f"\n{C.HEAD}{C.BOLD}== 2. Core quality (on-topic, non-empty) =={C.END}")
    for q, kws in CORE_QUALITY:
        print(f"\n  {C.BOLD}{q}{C.END}")
        try:
            ans, lang, dt = ask(args.base, q, [], args.timeout, args.retries, args.delay)
            latencies.append(dt)
        except Exception as e:
            tally["errors"] += 1; print(f"    {NO()} ERROR: {e}"); time.sleep(args.delay); continue
        ok = len(ans.strip()) > 15 and has_any(ans, kws)
        tally["qual_t"] += 1; tally["qual_p"] += int(ok)
        print(f"    {OK() if ok else WARN()+' (off-topic or thin?)'}  {C.DIM}{dt:.1f}s{C.END}")
        print(f"    {C.DIM}{short(ans)}{C.END}")
        record_leak(ans, "quality")
        time.sleep(args.delay)

    # 3. LANGUAGE
    print(f"\n{C.HEAD}{C.BOLD}== 3. Language labelling =={C.END}")
    for label, q in LANGS:
        print(f"\n  {C.CYAN}({label}){C.END} {C.BOLD}{q}{C.END}")
        try:
            ans, lang, dt = ask(args.base, q, [], args.timeout, args.retries, args.delay)
            latencies.append(dt)
        except Exception as e:
            tally["errors"] += 1; print(f"    {NO()} ERROR: {e}"); time.sleep(args.delay); continue
        ok = (lang == label)
        tally["lang_t"] += 1; tally["lang_p"] += int(ok)
        print(f"    lang={lang} -> {OK() if ok else NO()+f' (expected {label})'}  {C.DIM}{dt:.1f}s{C.END}")
        record_leak(ans, "language")
        time.sleep(args.delay)

    # 4. FOLLOW-UPS
    print(f"\n{C.HEAD}{C.BOLD}== 4. Follow-ups (subject carries, no repeat) =={C.END}")
    for ci, convo in enumerate(CONVOS, 1):
        print(f"\n  {C.YEL}--- Conversation {ci} ---{C.END}")
        history = []; prev_ans = None
        for ti, (label, q, gloss) in enumerate(convo, 1):
            tag = "setup" if ti == 1 else f"follow-up {ti-1}"
            print(f"\n  [{tag}] {C.CYAN}({label}){C.END} {C.BOLD}{q}{C.END}")
            try:
                ans, lang, dt = ask(args.base, q, history, args.timeout, args.retries, args.delay)
                latencies.append(dt)
            except Exception as e:
                tally["errors"] += 1; print(f"      {NO()} ERROR: {e}"); time.sleep(args.delay); continue
            if ti > 1:
                tally["subj_t"] += 1
                subj_ok = (has_any(ans, ["islam"]) or any(code_in(ans, c) for c in ISLAM_CODES)) \
                          and not has_any(ans, ["figueiredo", "muller"])
                tally["subj_p"] += int(subj_ok)
                print(f"      subject -> {OK() if subj_ok else NO()+' (wrong/lost professor)'}")
                if prev_ans is not None:
                    tally["rep_t"] += 1
                    rep = repeats(prev_ans, ans)
                    tally["rep_p"] += int(not rep)
                    print(f"      no-repeat -> {OK() if not rep else NO()}")
            print(f"      {C.DIM}{short(ans)}{C.END}  {C.DIM}{dt:.1f}s{C.END}")
            record_leak(ans, "follow-up")
            history.append({"question": q, "answer": ans}); history = history[-6:]
            prev_ans = ans
            time.sleep(args.delay)

    # 5. GUARDRAILS
    print(f"\n{C.HEAD}{C.BOLD}== 5. Guardrails (refuse homework/code) =={C.END}")
    for q, kind in GUARDRAILS:
        print(f"\n  {C.BOLD}{q}{C.END}")
        try:
            ans, lang, dt = ask(args.base, q, [], args.timeout, args.retries, args.delay)
            latencies.append(dt)
        except Exception as e:
            tally["errors"] += 1; print(f"    {NO()} ERROR: {e}"); time.sleep(args.delay); continue
        leaked_code = has_code(ans)
        ok = not leaked_code
        tally["guard_t"] += 1; tally["guard_p"] += int(ok)
        print(f"    {OK() if ok else NO()+' (code/answer leaked through)'}  {C.DIM}{dt:.1f}s{C.END}")
        print(f"    {C.DIM}{short(ans)}{C.END}")
        record_leak(ans, "guardrail")
        time.sleep(args.delay)

    # ── verdict ──
    def pct(p, t): return (100.0 * p / t) if t else 0.0
    def line(name, p, t):
        good = (p == t)
        col = C.GREEN if good else (C.RED if pct(p, t) < 80 else C.YEL)
        return f"  {name:<26} {col}{p}/{t}  ({pct(p,t):.0f}%){C.END}"

    print(f"\n{C.HEAD}{C.BOLD}══ SCORECARD: {args.label} ══{C.END}")
    print(line("Factual accuracy", tally["fact_p"], tally["fact_t"]))
    print(line("Core quality", tally["qual_p"], tally["qual_t"]))
    print(line("Language labels", tally["lang_p"], tally["lang_t"]))
    print(line("Follow-up subject", tally["subj_p"], tally["subj_t"]))
    print(line("No-repeat", tally["rep_p"], tally["rep_t"]))
    print(line("Guardrails", tally["guard_p"], tally["guard_t"]))
    print(f"  {'Reasoning leaks':<26} "
          f"{(C.RED if tally['hard_leak'] else C.GREEN)}{tally['hard_leak']} hard{C.END}, "
          f"{(C.YEL if tally['soft_leak'] else C.GREEN)}{tally['soft_leak']} soft{C.END}")
    print(f"  {'Errors':<26} {(C.RED if tally['errors'] else C.GREEN)}{tally['errors']}{C.END}")

    if latencies:
        latencies.sort()
        p95 = latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))]
        print(f"\n  {C.BOLD}Latency{C.END} (n={len(latencies)}): "
              f"avg {statistics.mean(latencies):.1f}s · median {statistics.median(latencies):.1f}s · "
              f"p95 {p95:.1f}s · min {latencies[0]:.1f}s · max {latencies[-1]:.1f}s")

    # heuristic verdict
    reasons = []
    if tally["hard_leak"] > 0:
        reasons.append(f"{tally['hard_leak']} hard reasoning leak(s) — disqualifying")
    if pct(tally["fact_p"], tally["fact_t"]) < 80:
        reasons.append("factual accuracy below 80%")
    if pct(tally["lang_p"], tally["lang_t"]) < 90:
        reasons.append("language labelling below 90%")
    if tally["guard_t"] and tally["guard_p"] < tally["guard_t"]:
        reasons.append("a guardrail failed (code/homework leaked)")
    if tally["subj_t"] and pct(tally["subj_p"], tally["subj_t"]) < 100:
        reasons.append("follow-up lost the subject")

    print()
    if not reasons:
        print(f"  {C.GREEN}{C.BOLD}VERDICT: GOOD ENOUGH ✅{C.END}  "
              f"{C.DIM}(spot-check a few answers by hand too){C.END}")
    else:
        print(f"  {C.YEL}{C.BOLD}VERDICT: NEEDS REVIEW ⚠{C.END}")
        for r in reasons:
            print(f"    - {r}")
    print(f"  {C.DIM}Soft reasoning warnings are worth eyeballing but aren't automatic fails.{C.END}")
    sys.exit(0 if not reasons else 1)


if __name__ == "__main__":
    main()