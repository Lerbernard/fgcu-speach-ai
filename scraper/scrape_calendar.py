"""
split_calendar.py — split the big academic_calendar.md into one readable file per term.

The scraper writes a single academic_calendar.md with one **Term** header per term.
This breaks it into small, skimmable files under a new academic_calendar/ folder
(one per term, plus an overview), which read better and chunk cleanly at ingest.

    python split_calendar.py                          # reads ./data/academic_calendar.md
    python split_calendar.py "C:\\path\\to\\data\\academic_calendar.md"

Output: a sibling folder  <data>/academic_calendar/  with files like
        fall-2026-full-term-15-weeks.md, spring-2027-full-term-15-weeks.md, ...
The original file is renamed to academic_calendar.md.bak so it isn't ingested twice.
Re-ingest afterwards.
"""

import os
import re
import sys

# A term header is either a bold-only line (**Fall 2026 ...**) — what the scraper
# emits — or a markdown ## / ### header, in case the file was hand-edited.
_BOLD = re.compile(r'^\s*\*\*(.+?)\*\*\s*$')
_HDR  = re.compile(r'^\s{0,3}#{2,3}\s+(\S.*?)\s*#*\s*$')


def slug(name):
    s = re.sub(r'[(),/]', ' ', name.lower())
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s or "term"


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join("data", "academic_calendar.md")
    if not os.path.isfile(src):
        sys.exit(f"Not found: {src}\nPass the path to academic_calendar.md as an argument.")

    text = open(src, encoding="utf-8").read()
    out_dir = os.path.join(os.path.dirname(src) or ".", "academic_calendar")
    os.makedirs(out_dir, exist_ok=True)

    preamble, sections = [], []          # sections: list of (name, [body lines])
    cur_name, cur_body = None, []
    for ln in text.splitlines():
        m = _BOLD.match(ln) or _HDR.match(ln)
        if m:
            if cur_name:
                sections.append((cur_name, cur_body))
            cur_name, cur_body = m.group(1).strip(), []
        elif cur_name is None:
            # drop the big top-level "# FGCU Academic Calendar" title line itself
            if not ln.lstrip().startswith("# "):
                preamble.append(ln)
        else:
            cur_body.append(ln)
    if cur_name:
        sections.append((cur_name, cur_body))

    intro = "\n".join(preamble).strip()
    src_line = "Source: https://www.fgcu.edu/academics/academiccalendar/"

    # overview file (the shared intro + how drop/withdraw works)
    if intro:
        with open(os.path.join(out_dir, "00-about-the-calendar.md"), "w", encoding="utf-8") as f:
            f.write(f"# FGCU Academic Calendar — Overview\n\n{intro}\n")

    count = 0
    for name, body in sections:
        body_text = "\n".join(body).strip()
        if not body_text:
            continue
        with open(os.path.join(out_dir, slug(name) + ".md"), "w", encoding="utf-8") as f:
            f.write(f"# {name}\n\n{src_line}\n\n{body_text}\n")
        count += 1
        n_dates = sum(1 for l in body if l.strip().startswith("-"))
        print(f"  wrote {slug(name)}.md  ({n_dates} dates)")

    # keep the original out of the ingest path so it isn't indexed twice
    bak = src + ".bak"
    try:
        os.replace(src, bak)
        print(f"\nRenamed original -> {bak} (so it isn't ingested twice).")
    except OSError as e:
        print(f"\nCould not rename {src} ({e}); delete or move it manually before re-ingesting.")

    print(f"{count} term files written to {out_dir}")
    print("Re-ingest so the split calendar files are indexed.")


if __name__ == "__main__":
    main()