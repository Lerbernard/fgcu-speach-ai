#!/usr/bin/env python3
"""
FGCU Engineering course scraper — Gulfline class-schedule search.

Scrapes EVERY section (keyed by CRN) for the College of Engineering across all
2025 and 2026 terms, and writes one Markdown file per subject-per-term matching
the existing data format. Fixes the two problems in the old data:
  * only the first section per course was captured  -> now loops every CRN
  * the Meet Times "Class/Exam" lines ran together   -> now split cleanly

USAGE (run on a machine that can reach gulfline.fgcu.edu):
    pip install requests beautifulsoup4
    python scrape_courses.py                # full scrape -> ./courses_out/ + fgcu_courses.zip
    python scrape_courses.py --inspect      # just print the form fields/options (debugging)
    python scrape_courses.py --years 2026   # limit to certain years
    python scrape_courses.py --college "Engineering"   # override college match text

If the form's field names or the results table differ from what this expects,
run --inspect first: it prints the real <form> action, every input/select name,
and the term/college option values so you can adjust the CONFIG block below.
"""

import argparse
import os
import re
import sys
import zipfile
from urllib.parse import urljoin

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Missing deps. Run:  pip install requests beautifulsoup4")

# ---------------------------------------------------------------- CONFIG -----
FORM_URL = "https://gulfline.fgcu.edu/pls/fgpo/szkschd.p_showform"
OUT_DIR = "courses_out"
ZIP_NAME = "fgcu_courses.zip"
COLLEGE_MATCH = "engineering"          # option text (case-insensitive) that selects the college
YEARS = ("2025", "2026")               # term option text must contain one of these
HEADERS = {"User-Agent": "Mozilla/5.0 (course-scraper; educational use)"}
# -----------------------------------------------------------------------------


def get_soup(session, url, data=None):
    r = session.post(url, data=data, headers=HEADERS, timeout=30) if data \
        else session.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser"), r


def discover_form(session):
    """GET the form and pull out: action URL, all default fields, and the term
    + college <select> names and their option (value,label) pairs."""
    soup, _ = get_soup(session, FORM_URL)
    form = soup.find("form")
    if not form:
        sys.exit("No <form> found on the page. Run --inspect and check the URL.")
    action = urljoin(FORM_URL, form.get("action") or FORM_URL)

    defaults, selects = {}, {}
    for inp in form.find_all("input"):
        name = inp.get("name")
        if not name:
            continue
        t = (inp.get("type") or "text").lower()
        if t in ("checkbox", "radio") and not inp.has_attr("checked"):
            continue
        defaults[name] = inp.get("value", "")
    for sel in form.find_all("select"):
        name = sel.get("name")
        if not name:
            continue
        opts = [(o.get("value", ""), o.get_text(" ", strip=True)) for o in sel.find_all("option")]
        selects[name] = opts
        # default = selected option, else first
        chosen = next((v for v, _ in opts if False), None)
        selected = sel.find("option", selected=True)
        defaults[name] = (selected.get("value") if selected else (opts[0][0] if opts else ""))

    # heuristics: term select has year-bearing options; college select has "engineering"
    term_name = next((n for n, opts in selects.items()
                      if any(re.search(r"20\d\d", lbl) for _, lbl in opts)), None)
    college_name = next((n for n, opts in selects.items()
                         if any(COLLEGE_MATCH in lbl.lower() for _, lbl in opts)), None)
    return action, defaults, selects, term_name, college_name


def inspect(session):
    action, defaults, selects, term_name, college_name = discover_form(session)
    print(f"FORM action : {action}")
    print(f"term select : {term_name}")
    print(f"college sel  : {college_name}\n")
    for name, opts in selects.items():
        print(f"[select] {name}  ({len(opts)} options)")
        for v, lbl in opts[:40]:
            print(f"    {v!r:>12}  {lbl}")
    print("\n[default fields]")
    for k, v in defaults.items():
        if k not in selects:
            print(f"    {k} = {v!r}")


def norm(s):
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def split_schedule(cell):
    """Turn the Meet Times cell into a single clean line with each meeting
    (Class / Exam / Lab ...) separated by '; ' instead of running together."""
    text = cell.get_text("\n")
    text = re.sub(r"\s*--\s*", " ", text)                 # kill the ' -- ' separators
    # ensure each 'Class :' / 'Exam :' / 'Lab :' starts a new segment
    text = re.sub(r"(?<!^)\s*(Class|Exam|Lab|Lecture|Studio)\s*:", r"\n\1:", text)
    parts = [re.sub(r"^(Class|Exam|Lab|Lecture|Studio)\s*:", r"\1:", norm(p))
             for p in text.split("\n") if norm(p)]
    return "; ".join(parts) if parts else norm(cell.get_text(" "))


def parse_results(soup):
    """Find the results table and return a list of section dicts (one per CRN)."""
    tables = soup.find_all("table")
    target = None
    for t in tables:
        head = norm(t.get_text(" ")).lower()
        if "crn" in head and ("course" in head or "title" in head):
            target = t
            break
    if not target:
        return []

    rows = target.find_all("tr")
    # locate header row + map columns by header text
    header_idx, col = None, {}
    for i, tr in enumerate(rows):
        cells = [norm(c.get_text(" ")).lower() for c in tr.find_all(["th", "td"])]
        if "crn" in cells:
            header_idx = i
            for j, h in enumerate(cells):
                if "crn" in h: col["crn"] = j
                elif h.startswith("course"): col["course"] = j
                elif "title" in h: col["title"] = j
                elif "credit" in h: col["credits"] = j
                elif "instructor" in h: col["instructor"] = j
                elif "meet" in h or ("days" in h and "time" in h): col["meet"] = j
                elif "part of term" in h or h == "part of term": col["term_part"] = j
                elif h.startswith("status"): col["status"] = j
                elif "max seat" in h: col["max"] = j
                elif "seats avail" in h: col["avail"] = j
                elif "wl avail" in h: col["wl"] = j
            break
    if header_idx is None:
        return []

    sections = []
    for tr in rows[header_idx + 1:]:
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue

        def cellhtml(key):
            j = col.get(key)
            return cells[j] if (j is not None and j < len(cells)) else None

        def celltext(key):
            c = cellhtml(key)
            return norm(c.get_text(" ")) if c else ""

        crn = celltext("crn")
        if not re.fullmatch(r"\d{4,6}", crn):        # skip notes / spacer rows
            continue
        meet_cell = cellhtml("meet")
        sections.append({
            "crn": crn,
            "course": celltext("course"),
            "title": celltext("title"),
            "credits": celltext("credits"),
            "instructor": celltext("instructor") or "Staff",
            "schedule": split_schedule(meet_cell) if meet_cell else "",
            "term_part": celltext("term_part") or "Full Term",
            "status": celltext("status"),
            "max": celltext("max"),
            "avail": celltext("avail"),
            "wl": celltext("wl"),
        })
    return sections


def subject_of(course):
    m = re.match(r"\s*([A-Za-z]{2,4})\s*\d", course or "")
    return m.group(1).upper() if m else "MISC"


def write_markdown(term_label, sections, out_dir):
    """One .md per subject for this term, matching the existing data format."""
    by_subj = {}
    for s in sections:
        by_subj.setdefault(subject_of(s["course"]), []).append(s)

    written = []
    for subj, secs in sorted(by_subj.items()):
        secs.sort(key=lambda s: (s["course"], s["crn"]))
        lines = [
            f"# FGCU Engineering Course Schedule — {term_label} — {subj}",
            f"Term: {term_label}",
            f"Subject: {subj}",
            f"Sections: {len(secs)}",
            "---",
            f"## {subj} Courses — {term_label}",
            "",
        ]
        for s in secs:
            course = norm(s["course"]) or subj
            credits = f"{s['credits']} credits" if s["credits"] else "credits n/a"
            seats = ""
            if s["max"] or s["avail"]:
                seats = f"\nSeats: {s['avail'] or '?'} of {s['max'] or '?'} available"
                if s["wl"]:
                    seats += f" (waitlist {s['wl']})"
            lines.append(f"{course} {term_label} — Instructor: {s['instructor']}")
            lines.append(f"Course: {norm(s['title'])} ({credits}) | CRN: {s['crn']}")
            lines.append(f"Schedule: {s['schedule'] or 'TBA'}")
            lines.append(f"Session: {s['term_part']}{seats}")
            lines.append("")
        slug = re.sub(r"[^A-Za-z0-9]+", "_", term_label).strip("_")
        path = os.path.join(out_dir, f"{subj}_{slug}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines).rstrip() + "\n")
        written.append(path)
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inspect", action="store_true", help="print the form fields and exit")
    ap.add_argument("--years", nargs="*", default=list(YEARS))
    ap.add_argument("--college", default=COLLEGE_MATCH)
    args = ap.parse_args()
    years = tuple(str(y) for y in args.years)

    session = requests.Session()
    if args.inspect:
        inspect(session)
        return

    action, defaults, selects, term_name, college_name = discover_form(session)
    if not term_name:
        sys.exit("Couldn't find the term dropdown. Run --inspect and set it in CONFIG.")
    if not college_name:
        sys.exit("Couldn't find the college dropdown. Run --inspect and set it in CONFIG.")

    college_val = next((v for v, lbl in selects[college_name]
                        if args.college.lower() in lbl.lower()), None)
    if not college_val:
        sys.exit(f"No college option matched {args.college!r}. Run --inspect to see options.")

    terms = [(v, lbl) for v, lbl in selects[term_name]
             if v and any(y in lbl for y in years)]
    if not terms:
        sys.exit(f"No terms matched {years}. Run --inspect to see term options.")

    os.makedirs(OUT_DIR, exist_ok=True)
    all_written, grand_total = [], 0
    for term_val, term_lbl in terms:
        payload = dict(defaults)
        payload[term_name] = term_val
        payload[college_name] = college_val
        print(f"-> {term_lbl}  (college={college_val})")
        try:
            soup, _ = get_soup(session, action, data=payload)
            secs = parse_results(soup)
        except Exception as e:
            print(f"   !! failed: {e}")
            continue
        print(f"   {len(secs)} sections")
        grand_total += len(secs)
        all_written += write_markdown(norm(term_lbl), secs, OUT_DIR)

    if grand_total == 0:
        print("\nNo sections parsed. The results table may differ — run --inspect,\n"
              "or share one results HTML page and I'll match the parser.")
        return

    with zipfile.ZipFile(ZIP_NAME, "w", zipfile.ZIP_DEFLATED) as z:
        for p in all_written:
            z.write(p, os.path.join(OUT_DIR, os.path.basename(p)))
    print(f"\nDone: {grand_total} sections across {len(all_written)} files -> {ZIP_NAME}")


if __name__ == "__main__":
    main()
