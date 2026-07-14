#!/usr/bin/env python3
"""
Ask the Eagle: evaluation harness (ablation study).

Runs the gold set in eval_set.json through four configurations and reports
accuracy per configuration, so each component of the pipeline can be shown to
earn its place. This is the "compare with existing methods" the report rubric
asks for.

    C1  LLM only            no retrieval at all (closed-book baseline)
    C2  Naive RAG           vector search, top-k, no rerank, no rewrite
    C3  RAG + rerank        + Cohere reranking (standard RAG baseline)
    C4  Proposed (full)     + typo fix, query rewriting, filter re-derivation

RUN FROM THE backend/ FOLDER (next to main.py and .env).

Each configuration is run SEPARATELY so you can spread the API cost across
different keys. Each run writes its own results file; merge_eval.py then
combines them into the summary table and chart.

    python run_eval.py --configs C1        -> eval_results_C1.csv
    python run_eval.py --configs C2        -> eval_results_C2.csv
    python run_eval.py --configs C3        -> eval_results_C3.csv
    python run_eval.py --configs C4        -> eval_results_C4.csv
    python merge_eval.py                   -> summary + chart from all four

To use a different API key for a run, set it in the shell first. A shell
variable takes precedence over the one in .env:

    Windows  :  set GROQ_API_KEY=gsk_second_key_here
    Mac/Linux:  export GROQ_API_KEY=gsk_second_key_here

Other flags:
    --limit 3        only the first N questions (smoke test)
    --sleep 2        seconds between calls, raise this if you hit rate limits
    --out NAME.csv   override the output filename
"""
import argparse
import csv
import json
import os
import sys
import time

# --- import the live system -------------------------------------------------
try:
    import main as eagle          # noqa: F401  (main.py must be importable)
except Exception as e:
    sys.exit(f"Could not import main.py. Run this from the backend folder.\n{e}")

from llama_index.core import Settings

ABSTAIN_MARKERS = [
    "not sure", "don't have", "do not have", "not specified", "no information",
    "couldn't find", "could not find", "unable to find", "not listed",
    "check the", "i'm not certain", "not available",
]


# ---------------------------------------------------------------- grading ---
def norm(s):
    return " ".join((s or "").lower().split())


def is_abstention(answer):
    a = norm(answer)
    return any(m in a for m in ABSTAIN_MARKERS)


def grade(item, answer):
    """Correct if every required fact appears (any alternative counts), no
    excluded fact appears, and abstention items actually abstain."""
    a = norm(answer)
    if item.get("must_abstain"):
        return 1 if is_abstention(answer) else 0
    for bad_group in item.get("must_exclude", []):
        if any(norm(b) in a for b in bad_group):
            return 0
    for group in item.get("must_include", []):
        if not any(norm(g) in a for g in group):
            return 0
    return 1


# ------------------------------------------------------------- the configs --
def run_c1_llm_only(question, history):
    """Closed book: no retrieval. The model answers from parametric memory."""
    prompt = (
        "You are an assistant for FGCU's U.A. Whitaker College of Engineering. "
        "Answer the student's question. If you do not know, say so.\n\n"
    )
    for h in history:
        prompt += f"Student: {h['question']}\nAssistant: {h['answer']}\n"
    prompt += f"Student: {question}\nAssistant:"
    return str(Settings.llm.complete(prompt)).strip()


def _retrieve_answer(question, history, use_rerank):
    """Naive RAG: embed the question as-is, retrieve, optionally rerank, answer.
    Deliberately skips typo correction, query rewriting and filter routing.

    Both C2 and C3 place the SAME number of passages (8) in front of the
    generator, so the comparison isolates HOW those passages were selected:
      C2  top-8 by embedding similarity alone.
      C3  top-40 by embedding, reranked by a cross-encoder down to 8.
    Giving C2 all 40 unranked chunks would confound selection quality with
    context length, and costs roughly five times as many tokens per question."""
    if use_rerank:
        engine = eagle.index.as_query_engine(
            similarity_top_k=40,
            node_postprocessors=[eagle._reranker] if getattr(eagle, "_reranker", None) else None,
        )
    else:
        engine = eagle.index.as_query_engine(similarity_top_k=8)

    convo = ""
    for h in history:
        convo += f"Student: {h['question']}\nAssistant: {h['answer']}\n"
    q = (convo + "Student: " + question).strip() if convo else question
    return str(engine.query(q)).strip()


def run_c0_question_only(question, history):
    """Naive RAG, QUESTION ONLY: the current turn is embedded on its own, with no
    dialogue history. This is the baseline the paper's premise assumes, in which
    an elliptical follow-up ("who teaches it?") carries no retrievable signal.
    Contrast with C2, which concatenates the history and therefore hands the
    retriever the referent for free."""
    engine = eagle.index.as_query_engine(similarity_top_k=8)
    return str(engine.query(question)).strip()


def run_c2_naive_rag(question, history):
    return _retrieve_answer(question, history, use_rerank=False)


def run_c3_rag_rerank(question, history):
    return _retrieve_answer(question, history, use_rerank=True)


def run_c4_full(question, history):
    """The proposed system, exactly as deployed."""
    answer, _lang = eagle.answer_question(question, history, correct=True)
    return answer


CONFIGS = {
    "C1": ("LLM only (no retrieval)", run_c1_llm_only),
    "C0": ("Naive RAG (question only)", run_c0_question_only),
    "C2": ("Naive RAG (+ history)", run_c2_naive_rag),
    "C3": ("RAG + reranking", run_c3_rag_rerank),
    "C4": ("Proposed (full)", run_c4_full),
}


# ------------------------------------------------------------------- main ---
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="eval_set.json")
    ap.add_argument("--configs", nargs="*", default=list(CONFIGS))
    ap.add_argument("--limit", type=int, default=0, help="only first N items (smoke test)")
    ap.add_argument("--sleep", type=float, default=1.0, help="seconds between calls (rate limits)")
    ap.add_argument("--out", default=None, help="output CSV name (default: eval_results_<CONFIGS>.csv)")
    ap.add_argument("--restart", action="store_true",
                    help="ignore existing results and start this config over")
    args = ap.parse_args()

    data = json.load(open(args.set, encoding="utf-8"))
    items = []
    for it in data.get("single_turn", []):
        it["history"] = []
        items.append(it)
    items += data.get("multi_turn", [])
    if args.limit:
        items = items[: args.limit]

    out = args.out or f"eval_results_{'_'.join(args.configs)}.csv"
    FIELDS = ["config", "config_label", "id", "category", "question", "correct", "answer"]

    # ---- RESUME: skip anything already answered in a previous run ----------
    done = set()
    if os.path.exists(out) and not args.restart:
        with open(out, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if not r.get("answer", "").startswith("[ERROR]"):
                    done.add((r["config"], r["id"]))
        if done:
            print(f"resuming {out}: {len(done)} question(s) already done\n")

    fresh = not os.path.exists(out) or args.restart
    fh = open(out, "w" if fresh else "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(fh, fieldnames=FIELDS)
    if fresh:
        writer.writeheader()
        fh.flush()

    todo = [(c, it) for c in args.configs for it in items if (c, it["id"]) not in done]
    print(f"{len(todo)} call(s) to make "
          f"({len(items)} questions x {len(args.configs)} config(s), minus {len(done)} done)\n")

    consecutive_errors = 0
    try:
        for cfg, it in todo:
            label, fn = CONFIGS[cfg]
            try:
                ans = fn(it["question"], it.get("history", []))
                consecutive_errors = 0
            except Exception as e:
                ans = f"[ERROR] {e}"
                consecutive_errors += 1

            ok = 0 if ans.startswith("[ERROR]") else grade(it, ans)
            writer.writerow({
                "config": cfg, "config_label": label,
                "id": it["id"], "category": it["category"],
                "question": it["question"], "correct": ok,
                "answer": ans.replace("\n", " ")[:400],
            })
            fh.flush()                    # write NOW, so a cutoff loses nothing
            os.fsync(fh.fileno())

            mark = "ERR " if ans.startswith("[ERROR]") else ("PASS" if ok else "FAIL")
            print(f"  {cfg} {it['id']:4} {mark}  {it['question'][:48]}")
            if ans.startswith("[ERROR]"):
                print(f"       {ans[:110]}")

            # API is out of credit / rate limited: stop cleanly, keep progress
            if consecutive_errors >= 3:
                print("\n3 errors in a row (likely out of API credit).")
                print(f"Progress is saved in {out}.")
                print(f"Swap the key in main.py, then re-run the SAME command to resume:")
                print(f"   python run_eval.py --configs {' '.join(args.configs)}")
                break

            time.sleep(args.sleep)
    finally:
        fh.close()

    # ---- summary of what is in the file now
    rows = []
    with open(out, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["correct"] = int(r["correct"])
            rows.append(r)

    print("=" * 58)
    for cfg in args.configs:
        sel = [r for r in rows if r["config"] == cfg and not r["answer"].startswith("[ERROR]")]
        ok = sum(r["correct"] for r in sel)
        pct = 100.0 * ok / len(sel) if sel else 0.0
        print(f"{CONFIGS[cfg][0]:28} {pct:5.1f}%   ({ok}/{len(sel)} of {len(items)} answered)")
    print("=" * 58)
    print(f"wrote {out}")
    remaining = len(items) * len(args.configs) - len([r for r in rows if not r["answer"].startswith("[ERROR]")])
    if remaining > 0:
        print(f"{remaining} question(s) still to do. Re-run the same command to resume.")
    else:
        print("This config is complete. When all four are done:  python merge_eval.py")


if __name__ == "__main__":
    main()
