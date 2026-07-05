#!/usr/bin/env python3
"""
Build the FGCU engineering course-data TREE from saved schedule-results HTML.

Produces the nested layout used in the repo:

    <out>/
      courses_<Term>/                       (one folder per semester)
        <SUBJ>_<Term>_courses/              (one folder per subject)
          <SUBJ>_<NUMBER>_<Term>.md         (one file per course, ALL its sections)

e.g.  courses_Fall_2026/BME_Fall_2026_courses/BME_3100C_Fall_2026.md

Captures every section (by CRN) and splits the run-on Class/Exam meeting times.

USAGE:
    pip install beautifulsoup4
    python build_courses.py                     # reads *.htm/*.html in current folder
    python build_courses.py path/to/html_dir
    python build_courses.py a.htm b.htm
    python build_courses.py --out courses --zip fgcu_courses.zip

Each input filename must contain its term, e.g. "...fall2026.htm", "...spring 2025...".
"""
import argparse
import glob
import os
import re
import sys
import zipfile

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Missing dep. Run:  pip install beautifulsoup4")


# Anchor everything to WHERE THIS SCRIPT LIVES, not the current working dir, so
# it runs the same from a scraper/ folder regardless of where you launch it.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def find_html_dir():
    """Look for saved schedule HTML in the likely spots relative to this script:
    the scraper folder itself, then ../data/courses, ../data, ./data/courses."""
    candidates = [
        SCRIPT_DIR,
        os.path.join(SCRIPT_DIR, "..", "data", "courses"),
        os.path.join(SCRIPT_DIR, "..", "data"),
        os.path.join(SCRIPT_DIR, "data", "courses"),
        os.getcwd(),
    ]
    for c in candidates:
        c = os.path.normpath(c)
        if glob.glob(os.path.join(c, "*.htm")) or glob.glob(os.path.join(c, "*.html")):
            return c
    return None


def norm(s):
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def term_from_name(fn):
    m = re.search(r"(spring|summer|fall)\s*([0-9]{4})", fn, re.I)
    return f"{m.group(1).capitalize()} {m.group(2)}" if m else None


def split_schedule(cell):
    text = cell.get_text(" ")
    text = re.sub(r"\s*--\s*", " ", text)
    text = re.sub(r"(Class|Exam|Lab|Lecture|Studio)\s*:", r"\n\1:", text)
    parts = [norm(p) for p in text.split("\n") if norm(p)]
    parts = [p for p in parts if not re.fullmatch(r"(Class|Exam|Lab|Lecture|Studio):", p)]
    return "; ".join(parts) if parts else "TBA"


def course_parts(course):
    """'COP 1500' -> ('COP','1500'); 'BME 3100C' -> ('BME','3100C')."""
    m = re.match(r"\s*([A-Za-z]{2,4})\s*([0-9]{3,4}[A-Za-z]?)", course or "")
    return (m.group(1).upper(), m.group(2).upper()) if m else (None, None)


def parse_file(path):
    soup = BeautifulSoup(open(path, encoding="utf-8", errors="ignore").read(), "html.parser")
    trs = soup.find_all("tr")
    header_i, col = None, {}
    for i, tr in enumerate(trs):
        cells = tr.find_all(["td", "th"], recursive=False)
        texts = [norm(c.get_text(" ")).lower() for c in cells]
        if "crn" in texts:
            header_i = i
            for j, hh in enumerate(texts):
                if hh == "crn": col["crn"] = j
                elif hh == "course": col["course"] = j
                elif hh == "title": col["title"] = j
                elif "credit" in hh: col["credits"] = j
                elif hh == "instructor": col["instructor"] = j
                elif "meet" in hh: col["meet"] = j
                elif "part of term" in hh: col["part"] = j
            break
    if header_i is None:
        return []

    seen, out = set(), []
    for tr in trs[header_i + 1:]:
        cells = tr.find_all(["td", "th"], recursive=False)
        if not cells:
            continue
        texts = [norm(c.get_text(" ")) for c in cells]

        def gt(k):
            j = col.get(k)
            return texts[j] if (j is not None and j < len(texts)) else ""

        def gc(k):
            j = col.get(k)
            return cells[j] if (j is not None and j < len(cells)) else None

        crn = gt("crn")
        if not re.fullmatch(r"\d{4,6}", crn) or crn in seen:
            continue
        seen.add(crn)
        mc = gc("meet")
        out.append({
            "crn": crn, "course": gt("course"), "title": gt("title"),
            "credits": gt("credits"), "instructor": gt("instructor") or "STAFF",
            "schedule": split_schedule(mc) if mc else "TBA",
            "part": gt("part") or "Full Term",
        })
    return out


def write_tree(term, sections, out_dir):
    term_slug = re.sub(r"\s+", "_", term)
    by_course = {}
    for s in sections:
        subj, num = course_parts(s["course"])
        if not subj:
            continue
        by_course.setdefault((subj, num), []).append(s)

    written = []
    for (subj, num), ss in sorted(by_course.items()):
        ss.sort(key=lambda s: s["crn"])
        folder = os.path.join(out_dir, f"courses_{term_slug}", f"{subj}_{term_slug}_courses")
        os.makedirs(folder, exist_ok=True)
        title = ss[0]["title"] or f"{subj} {num}"
        L = [f"# {subj} {num} — {title} — {term}",
             f"Term: {term} | Subject: {subj} | Course: {subj} {num} | Sections: {len(ss)}",
             "---", ""]
        for s in ss:
            cr = f"{s['credits']} credits" if s["credits"] else "credits n/a"
            L += [f"{subj} {num} {term} — Instructor: {s['instructor']}",
                  f"Course: {s['title']} ({cr}) | CRN: {s['crn']}",
                  f"Schedule: {s['schedule']}",
                  f"Session: {s['part']}", ""]
        path = os.path.join(folder, f"{subj}_{num}_{term_slug}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(L).rstrip() + "\n")
        written.append(path)
    return written


def collect_inputs(inputs):
    files = []
    for item in (inputs or ["."]):
        if os.path.isdir(item):
            files += glob.glob(os.path.join(item, "*.htm")) + glob.glob(os.path.join(item, "*.html"))
        elif os.path.isfile(item):
            files.append(item)
    return sorted(set(files))


def main():
    ap = argparse.ArgumentParser(description="Build the nested course tree from saved schedule HTML.")
    ap.add_argument("inputs", nargs="*", help="HTML files or a folder (default: auto-detect)")
    ap.add_argument("--out", default=None, help="output root folder (default: <html dir>/courses)")
    ap.add_argument("--zip", default=None, help="zip name (default: <html dir>/fgcu_courses.zip)")
    args = ap.parse_args()

    if args.inputs:
        files = collect_inputs(args.inputs)
        base_dir = os.path.dirname(os.path.abspath(files[0])) if files else SCRIPT_DIR
    else:
        base_dir = find_html_dir()
        if not base_dir:
            sys.exit("No .htm/.html found. Put the saved pages next to this script or in "
                     "../data/courses, or pass a path:  python build_courses.py <folder>")
        files = collect_inputs([base_dir])

    if not files:
        sys.exit("No .htm/.html files found at that location.")

    out_dir = args.out or os.path.join(base_dir, "courses")
    zip_path = args.zip or os.path.join(base_dir, "fgcu_courses.zip")
    print(f"Reading HTML from: {base_dir}")
    print(f"Writing tree to  : {out_dir}\n")

    os.makedirs(out_dir, exist_ok=True)
    all_written, grand = [], 0
    for f in files:
        term = term_from_name(os.path.basename(f))
        if not term:
            print(f"skip (no term in name): {os.path.basename(f)}")
            continue
        secs = parse_file(f)
        grand += len(secs)
        w = write_tree(term, secs, out_dir)
        all_written += w
        print(f"{term:14} {len(secs):3} sections -> {len(w):3} course files  ({os.path.basename(f)})")

    if not all_written:
        sys.exit("Nothing parsed. Are these Gulfline results pages with a term in the filename?")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(all_written):
            z.write(p, os.path.relpath(p, out_dir))        # keep the folder tree in the zip
    print(f"\nDone: {grand} sections -> {len(all_written)} course files under {out_dir}/ and {zip_path}")


if __name__ == "__main__":
    main()