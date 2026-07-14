#!/usr/bin/env python3
"""
Merge the per-configuration evaluation runs into one summary.

Run this after all four configurations have been evaluated:

    python run_eval.py --configs C1        -> eval_results_C1.csv
    python run_eval.py --configs C2        -> eval_results_C2.csv
    python run_eval.py --configs C3        -> eval_results_C3.csv
    python run_eval.py --configs C4        -> eval_results_C4.csv
    python merge_eval.py

It picks up every eval_results_*.csv in the folder, so partial merges work too
(if you have only run C1 and C2, it will summarise those two).

Outputs:
    eval_results_all.csv    every question from every configuration
    eval_summary.csv        accuracy table
    eval_summary.md         markdown tables to paste into the paper
    eval_accuracy.png       grouped bar chart, overall and by category
"""
import csv
import glob
import os
import sys

# Displayed in increasing order of machinery, which is how the ablation reads.
CONFIG_ORDER = ["C1", "C0", "C2", "C3", "C4"]
CONFIG_LABEL = {
    "C1": "LLM only (no retrieval)",
    "C0": "Naive RAG (question only)",
    "C2": "Naive RAG (+ history)",
    "C3": "RAG + reranking",
    "C4": "Proposed (full)",
}
# Categories that exercise the conversational contribution of the paper.
CONVERSATIONAL = {
    "followup_pronoun", "followup_attribute", "followup_chain",
    "followup_event", "followup_professor", "course_switch",
}


def main():
    files = sorted(f for f in glob.glob("eval_results_*.csv")
                   if os.path.basename(f) != "eval_results_all.csv")
    if not files:
        sys.exit("No eval_results_*.csv found. Run run_eval.py --configs C1 (etc.) first.")

    rows = []
    for path in files:
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                r["correct"] = int(r["correct"])
                rows.append(r)
    print(f"merged {len(files)} file(s): {', '.join(files)}")

    # de-duplicate on (config, id) in case a config was re-run
    seen, deduped = set(), []
    for r in reversed(rows):                       # keep the most recent
        key = (r["config"], r["id"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    rows = list(reversed(deduped))

    cfgs = [c for c in CONFIG_ORDER if any(r["config"] == c for r in rows)]
    cats = sorted({r["category"] for r in rows})
    n_q = len({r["id"] for r in rows})
    print(f"{len(cfgs)} configuration(s), {n_q} question(s)\n")

    # warn if a config is missing questions the others have
    all_ids = {r["id"] for r in rows}
    for c in cfgs:
        have = {r["id"] for r in rows if r["config"] == c}
        missing = all_ids - have
        if missing:
            print(f"  ! {c} is missing {len(missing)} question(s): {sorted(missing)}")

    def acc(cfg, cat=None):
        sel = [r for r in rows if r["config"] == cfg
               and (cat is None or (r["category"] == cat if isinstance(cat, str)
                                    else r["category"] in cat))]
        return (100.0 * sum(r["correct"] for r in sel) / len(sel)) if sel else 0.0

    def count(cfg, cat=None):
        sel = [r for r in rows if r["config"] == cfg
               and (cat is None or (r["category"] == cat if isinstance(cat, str)
                                    else r["category"] in cat))]
        return sum(r["correct"] for r in sel), len(sel)

    # ---- combined per-question CSV
    with open("eval_results_all.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["id"], r["config"])))

    # ---- summary CSV
    with open("eval_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric"] + [CONFIG_LABEL[c] for c in cfgs])
        w.writerow(["Overall accuracy (%)"] + [f"{acc(c):.1f}" for c in cfgs])
        w.writerow(["Conversational subset (%)"] + [f"{acc(c, CONVERSATIONAL):.1f}" for c in cfgs])
        for cat in cats:
            w.writerow([f"{cat} (%)"] + [f"{acc(c, cat):.1f}" for c in cfgs])

    # ---- markdown for the paper
    with open("eval_summary.md", "w", encoding="utf-8") as f:
        f.write("## Table I. Overall accuracy\n\n")
        f.write("| Configuration | Accuracy (%) | Correct / Total |\n|---|---|---|\n")
        for c in cfgs:
            ok, tot = count(c)
            f.write(f"| {CONFIG_LABEL[c]} | {acc(c):.1f} | {ok}/{tot} |\n")

        f.write("\n## Table II. Conversational subset (follow-ups and entity switching)\n\n")
        f.write("| Configuration | Accuracy (%) | Correct / Total |\n|---|---|---|\n")
        for c in cfgs:
            ok, tot = count(c, CONVERSATIONAL)
            f.write(f"| {CONFIG_LABEL[c]} | {acc(c, CONVERSATIONAL):.1f} | {ok}/{tot} |\n")

        f.write("\n## Table III. Accuracy by question category\n\n")
        f.write("| Category | " + " | ".join(CONFIG_LABEL[c] for c in cfgs) + " |\n")
        f.write("|---" * (len(cfgs) + 1) + "|\n")
        for cat in cats:
            f.write(f"| {cat} | " + " | ".join(f"{acc(c, cat):.1f}" for c in cfgs) + " |\n")

    # ---- console
    print("=" * 60)
    print(f"{'Configuration':30} {'Overall':>9} {'Conversational':>15}")
    print("-" * 60)
    for c in cfgs:
        print(f"{CONFIG_LABEL[c]:30} {acc(c):8.1f}% {acc(c, CONVERSATIONAL):14.1f}%")
    print("=" * 60)

    # ---- chart
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        colors = {"C1": "#b0b0b0", "C0": "#e59866", "C2": "#7fb3d5",
                  "C3": "#5499c7", "C4": "#2ecc71"}
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5))

        ax1.bar([CONFIG_LABEL[c] for c in cfgs], [acc(c) for c in cfgs],
                color=[colors[c] for c in cfgs])
        ax1.set_ylabel("Accuracy (%)")
        ax1.set_title("Overall accuracy by configuration", pad=14)
        ax1.set_ylim(0, 112)
        ax1.set_yticks([0, 20, 40, 60, 80, 100])
        for i, c in enumerate(cfgs):
            ax1.text(i, acc(c) + 2.5, f"{acc(c):.1f}", ha="center", va="bottom", fontsize=9)
        ax1.tick_params(axis="x", rotation=20)

        x = np.arange(len(cats))
        width = 0.8 / max(1, len(cfgs))
        for i, c in enumerate(cfgs):
            ax2.bar(x + i * width, [acc(c, cat) for cat in cats], width,
                    label=CONFIG_LABEL[c], color=colors[c])
        ax2.set_xticks(x + width * (len(cfgs) - 1) / 2)
        ax2.set_xticklabels(cats, rotation=35, ha="right", fontsize=8)
        ax2.set_ylabel("Accuracy (%)")
        ax2.set_title("Accuracy by question category", pad=14)
        ax2.set_ylim(0, 112)
        ax2.set_yticks([0, 20, 40, 60, 80, 100])
        ax2.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.32),
                   ncol=min(len(cfgs), 4), frameon=False)

        plt.tight_layout()
        plt.savefig("eval_accuracy.png", dpi=200, bbox_inches="tight")
        print("wrote eval_accuracy.png")
    except ImportError:
        print("matplotlib not installed; skipped the chart (pip install matplotlib)")

    print("wrote eval_results_all.csv, eval_summary.csv, eval_summary.md")


if __name__ == "__main__":
    main()
