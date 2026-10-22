"""
Document loading + chunking shared by ingest.py (full rebuild) and
ingest_incremental.py (only changed files). Keeping both on one code path is
what makes an incremental update produce the SAME chunks, metadata and vector
IDs a full rebuild would, so the two can be mixed freely.
"""
import hashlib
import os
import re

# ── classification ─────────────────────────────────────────

def get_doc_type(path, filename):
    """Classify each document so retrieval can tell types apart."""
    f = filename.lower()
    # Normalize Windows backslashes to forward slashes so path checks like
    # "/events/" match on every OS.
    p = path.lower().replace("\\", "/")
    if "course_descriptions" in p or "_description" in f:
        return "course_description"
    if "learning_support" in p or "learning_hub" in f or "service_learning" in f:
        return "learning_support"
    if "advising" in p or "advising" in f or "advisor" in f:
        return "advising"
    if "academic_calendar" in p or "academiccalendar" in p \
       or "academic_calendar" in f or f == "calendar.md":
        return "calendar"
    if "courses" in p:
        return "course_offering"
    if filename.startswith("programs_") or "degree_map" in f:
        return "degree_map"
    if "ratemyprofessors" in p:
        return "faculty_reviews"
    if "faculty" in p:
        return "faculty"
    if "clubs" in p:
        return "club"
    if "research" in p:
        return "research"
    if "admissions" in p:
        return "admissions"
    if "policies_legal" in p or "ethics" in f or "stateauthorization" in f \
       or "governmentrelations" in f or "studentcomplaints" in f or "complaint" in f:
        return "policy"
    if "student-involvement" in f or "student_involvement" in f \
       or "/events/" in p or p.endswith("/events"):
        return "event"
    if "student_life" in p:
        return "student_life"
    if "engineering_departments" in p:
        return "department"
    if "engineering_programs" in p or "academics" in p:
        return "program"
    if "engineering_main" in p or "about_fgcu" in p:
        return "campus"
    return "general"


def get_program(path, filename):
    """Tag which degree program a file belongs to."""
    f = (filename + " " + path).lower()
    if "software-engineering" in f or "software_engineering" in f:
        return "software_engineering"
    if "computer-science" in f or "computer_science" in f or "computerscience" in f:
        return "computer_science"
    if "civil" in f:
        return "civil_engineering"
    if "bioengineering" in f:
        return "bioengineering"
    if "construction" in f:
        return "construction_management"
    if "environmental" in f:
        return "environmental_engineering"
    return "general"


def get_professor(path, filename, content=""):
    """Faculty files are named after the professor (allen_paul.md). Course
    offering files name their instructor on an 'Instructor: Allen, Paul' line;
    both are tagged 'lastname firstname' so a question about a professor
    filters to their courses too."""
    if "faculty" in path or "ratemyprofessors" in path:
        name = filename.replace(".md", "")
        name = re.sub(r'_part\d+$', '', name)
        name = name.replace("_", " ").strip()
        if name.startswith("www ") or "facultystaff" in name:
            return ""
        return name.lower()
    m = re.search(r'Instructor:\s*([A-Za-z\'-]+),\s*([A-Za-z\'-]+)', content)
    if m:
        return f"{m.group(1).strip().lower()} {m.group(2).strip().lower()}"
    return ""


def get_term(filename):
    """'COP_1500_Fall_2025.md' -> 'fall 2025'; also the hyphenated calendar
    files ('fall-2026-session-a-1st-7-weeks.md' -> 'fall 2026'). Without the
    hyphen form, calendar chunks had no term and any calendar question that
    named a term ("withdraw deadline for Fall 2026") matched nothing once the
    term filter was pinned."""
    m = re.search(r'(Fall|Spring|Summer)[_\- ](\d{4})', filename, re.IGNORECASE)
    return f"{m.group(1).lower()} {m.group(2)}" if m else ""


def get_course_code(filename):
    m = re.match(r'([A-Za-z]{2,4})_(\d{3,4}[A-Za-z]?)', filename)
    return f"{m.group(1).lower()} {m.group(2).lower()}" if m else ""


# ── date normalisation for calendar grids ──────────────────

_MONTHS = ["", "January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]


def normalize_event_dates(text: str) -> str:
    """Rewrite calendar-grid rows like
        | AI Day | ...img... | 02 | 11 | 2026 | 1 | 3 | A panelist... |
    into 'AI Day — November 2, 2026. A panelist...' so "when is X" queries
    embed and read well. Non-grid text is returned unchanged."""
    out = []
    for line in text.split("\n"):
        s = line.strip()
        if not (s.startswith("|") and s.count("|") >= 5):
            out.append(line)
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        date_str, di = None, -1
        for i in range(len(cells) - 2):
            a, b, c = cells[i], cells[i + 1], cells[i + 2]
            if a.isdigit() and b.isdigit() and c.isdigit():
                d, m, y = int(a), int(b), int(c)
                if 1 <= d <= 31 and 1 <= m <= 12 and 2000 <= y <= 2100:
                    date_str, di = f"{_MONTHS[m]} {d}, {y}", i
                    break
        if date_str is None:
            out.append(line)
            continue
        title = cells[0] if cells and cells[0] else "Event"
        time_str = next((c for c in cells if re.search(r"\d{1,2}:\d{2}\s*(am|pm)", c, re.I)), "")
        skip = {title, cells[di], cells[di + 1], cells[di + 2], time_str}
        desc = [c for c in cells if c and c not in skip and not c.isdigit()
                and not c.lower().endswith((".jpg", ".png", ".jpeg")) and not c.startswith("/")]
        line_out = f"{title} — {date_str}" + (f" ({time_str})" if time_str else "") + "."
        if desc:
            line_out += " " + ". ".join(desc)
        out.append(line_out)
    return "\n".join(out)


# ── document discovery ─────────────────────────────────────

def iter_data_files(data_dir):
    """Every .md under data/ that should be indexed, applying the same skip
    rules as the original ingest: hidden dirs, saved-webpage asset folders,
    schedule-search HTML dumps, and rolled-up files whose split versions exist."""
    for root, dirs, files in os.walk(data_dir):
        dirs[:] = [d for d in dirs
                   if not d.startswith(".")
                   and not d.endswith("_files")
                   and "schedule search" not in d.lower()]
        for filename in sorted(files):
            if not filename.endswith(".md"):
                continue
            filepath = os.path.join(root, filename)
            subj_match = re.match(r'courses_(.+?)_([A-Z]{2,4})\.md$', filename)
            if subj_match:
                split_dir = os.path.join(os.path.dirname(filepath),
                                         f"{subj_match.group(2)}_{subj_match.group(1)}_courses")
                if os.path.isdir(split_dir):
                    continue
            if filename.startswith("course_descriptions_") or filename == "engineering_course_descriptions.md":
                if os.path.isdir(os.path.join(os.path.dirname(filepath), "individual")):
                    continue
            yield filepath


def load_document(filepath, data_dir):
    """(rel_path, text, metadata) or None when the file is too short to index.
    rel_path always uses forward slashes so IDs match across OSes."""
    rel_path = os.path.relpath(filepath, data_dir).replace("\\", "/")
    filename = os.path.basename(filepath)
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read().strip()
    if len(content) < 50:
        return None
    doc_type = get_doc_type(rel_path, filename)
    if doc_type in ("event", "calendar", "admissions"):
        content = normalize_event_dates(content)
    meta = {
        "source": filename,
        "path": rel_path,
        "folder": os.path.basename(os.path.dirname(filepath)),
        "doc_type": doc_type,
        "program": get_program(rel_path, filename),
        "professor": get_professor(rel_path, filename, content),
        "term": get_term(filename),
        "course_code": get_course_code(filename),
    }
    return rel_path, content, meta


# ── header-aware chunking ──────────────────────────────────
# Fixed-size chunking buried named things (an event/org inside a 400-token
# slab). Splitting on markdown headers AND on lines that are entirely **bold**
# gives each event / org / section its own chunk with its title attached.

_HDR = re.compile(r'^\s{0,3}(#{1,6})\s+(\S.*?)\s*#*\s*$')
_BOLD = re.compile(r'^\s*\*\*(.+?)\*\*\s*$')


def _sections(text):
    sections, title, buf = [], "", []
    for ln in text.splitlines():
        h, b = _HDR.match(ln), _BOLD.match(ln)
        if h or b:
            if title or "".join(buf).strip():
                sections.append((title, "\n".join(buf)))
            title, buf = (h or b).group(2 if h else 1).strip(), []
        else:
            buf.append(ln)
    if title or "".join(buf).strip():
        sections.append((title, "\n".join(buf)))
    return sections


def _window(body, max_chars=1400, overlap=100):
    body = body.strip()
    if not body:
        return []
    pieces = []
    for p in re.split(r'\n\s*\n', body):
        if len(p) <= max_chars:
            pieces.append(p)
        else:
            s = 0
            while s < len(p):
                pieces.append(p[s:s + max_chars])
                if s + max_chars >= len(p):
                    break
                s += max_chars - overlap
    out, cur = [], ""
    for p in pieces:
        if cur and len(cur) + len(p) + 2 > max_chars:
            out.append(cur)
            cur = p
        else:
            cur = (cur + "\n\n" + p) if cur else p
    if cur:
        out.append(cur)
    return out


def header_chunks(text, max_chars=1400):
    chunks = []
    for title, body in _sections(text):
        windows = _window(body, max_chars) or ([""] if title else [])
        for w in windows:
            chunks.append((title, w))
    return chunks


def build_chunks(rel_path, text, meta):
    """[(vector_id, chunk_text, metadata)] for one document. IDs are
    deterministic (path + position + title) so re-ingesting a file overwrites
    its vectors instead of duplicating them. The path, not just the filename,
    is in the seed: several files share a name across folders."""
    out = []
    for idx, (title, body) in enumerate(header_chunks(text)):
        content = (title + "\n" + body).strip() if title else body.strip()
        if len(content) < 15:
            continue
        md = dict(meta, title=title)
        vid = hashlib.md5(f"{rel_path}|{idx}|{title[:60]}".encode("utf-8")).hexdigest()
        out.append((vid, content, md))
    return out


def vector_metadata(text, md):
    """The metadata stored on each Pinecone vector. 'text' is what the query
    engine hands the LLM as context."""
    return {
        "text":        text[:1000],
        "title":       md.get("title", ""),
        "source":      md.get("source", ""),
        "path":        md.get("path", ""),
        "folder":      md.get("folder", ""),
        "doc_type":    md.get("doc_type", "general"),
        "program":     md.get("program", "general"),
        "professor":   md.get("professor", ""),
        "term":        md.get("term", ""),
        "course_code": md.get("course_code", ""),
    }
