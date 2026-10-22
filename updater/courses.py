"""
Course offerings from the Gulfline class-schedule search, one POST per term.
Writes the same tree the old build_courses.py produced:

    courses/courses/courses_<Term>/<SUBJ>_<Term>_courses/<SUBJ>_<NUM>_<Term>.md

Every section (CRN) of a course goes in that course's file.
"""
import os
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from common import abs_path, read_text, write_text, sha, now_iso, today

SOURCE = "courses"


def norm(s):
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def discover_form(html, form_url):
    """(action, default payload, {select name: [(value, label)]})."""
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form")
    action = urljoin(form_url, form.get("action") or form_url)
    defaults, selects = {}, {}
    for inp in form.find_all("input"):
        n = inp.get("name")
        if not n:
            continue
        t = (inp.get("type") or "text").lower()
        if t in ("checkbox", "radio") and not inp.has_attr("checked"):
            continue
        defaults[n] = inp.get("value", "")
    for sel in form.find_all("select"):
        n = sel.get("name")
        opts = [(o.get("value", ""), norm(o.get_text(" "))) for o in sel.find_all("option")]
        selects[n] = opts
        chosen = sel.find("option", selected=True)
        defaults[n] = chosen.get("value") if chosen else (opts[0][0] if opts else "")
    return action, defaults, selects


def split_schedule(cell):
    text = cell.get_text(" ")
    text = re.sub(r"\s*--\s*", " ", text)
    text = re.sub(r"(Class|Exam|Lab|Lecture|Studio)\s*:", r"\n\1:", text)
    parts = [norm(p) for p in text.split("\n") if norm(p)]
    parts = [p for p in parts if not re.fullmatch(r"(Class|Exam|Lab|Lecture|Studio):", p)]
    return "; ".join(parts) if parts else "TBA"


def parse_results(html):
    soup = BeautifulSoup(html, "html.parser")
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

        crn = gt("crn")
        if not re.fullmatch(r"\d{4,6}", crn) or crn in seen:
            continue
        seen.add(crn)
        mc = cells[col["meet"]] if "meet" in col and col["meet"] < len(cells) else None
        out.append({
            "crn": crn, "course": gt("course"), "title": gt("title"),
            "credits": gt("credits"), "instructor": gt("instructor") or "STAFF",
            "schedule": split_schedule(mc) if mc is not None else "TBA",
            "part": gt("part") or "Full Term",
        })
    return out


def course_parts(course):
    m = re.match(r"\s*([A-Za-z]{2,4})\s*([0-9]{3,4}[A-Za-z]?)", course or "")
    return (m.group(1).upper(), m.group(2).upper()) if m else (None, None)


def render_tree(term, sections):
    """{relative file path: markdown} for one term."""
    slug = re.sub(r"\s+", "_", term)
    by_course = {}
    for s in sections:
        subj, num = course_parts(s["course"])
        if subj:
            by_course.setdefault((subj, num), []).append(s)
    files = {}
    for (subj, num), ss in sorted(by_course.items()):
        ss.sort(key=lambda s: s["crn"])
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
        files[f"courses_{slug}/{subj}_{slug}_courses/{subj}_{num}_{slug}.md"] = "\n".join(L).rstrip() + "\n"
    return files


def wanted_terms(cfg, term_options):
    """Manifest terms plus, when auto_add_new_terms is on, any term the form
    offers for this year or later that the manifest doesn't list yet."""
    labels = {label: value for value, label in term_options if value}
    wanted = list(cfg.get("terms", []))
    if cfg.get("auto_add_new_terms", True):
        for label in labels:
            m = re.search(r"(20\d\d)", label)
            if m and int(m.group(1)) >= today().year and label not in wanted:
                wanted.append(label)
    return [(t, labels.get(t)) for t in wanted]


def run(manifest, state, fetch, report, dry_run=False, limit=None):
    cfg = manifest["courses"]
    root = abs_path(cfg["dir"])
    st = state.setdefault("courses", {})
    try:
        r = fetch.get(cfg["form_url"])
        r.raise_for_status()
        action, defaults, selects = discover_form(r.text, cfg["form_url"])
    except Exception as e:
        report.error(SOURCE, f"schedule form: {type(e).__name__}: {e}")
        return
    terms = wanted_terms(cfg, selects.get("Termcode", []))
    if limit:
        terms = terms[-limit:]
    st["last_checked"] = now_iso()
    st.setdefault("terms", {})

    for label, code in terms:
        if not code:
            report.warn(SOURCE, f"{label}: no longer offered by the schedule form; files kept as-is")
            continue
        payload = dict(defaults, Termcode=code, CollegeCode=cfg["college_code"])
        try:
            rr = fetch.post(action, payload)
            rr.raise_for_status()
            sections = parse_results(rr.text)
        except Exception as e:
            report.error(SOURCE, f"{label}: {type(e).__name__}: {e}")
            continue
        if not sections:
            report.warn(SOURCE, f"{label}: 0 sections returned; files kept as-is")
            continue
        files = render_tree(label, sections)
        term_dir = os.path.join(root, f"courses_{re.sub(r'\\s+', '_', label)}")
        written = updated = 0
        for rel, text in files.items():
            path = os.path.join(root, rel.replace("/", os.sep))
            old = read_text(path)
            if old is not None and sha(old) == sha(text):
                continue
            if not dry_run:
                write_text(path, text)
            if old is None:
                written += 1
            else:
                updated += 1
            report.written(SOURCE, f"{cfg['dir']}/{rel}", "updated" if old is not None else "new", quiet=True)
        removed = 0
        if os.path.isdir(term_dir):
            keep = {os.path.normpath(os.path.join(root, p)) for p in files}
            for dp, _, fns in os.walk(term_dir):
                for fn in fns:
                    p = os.path.normpath(os.path.join(dp, fn))
                    if fn.endswith(".md") and p not in keep:
                        if not dry_run:
                            os.remove(p)
                        removed += 1
                        report.removed(SOURCE, f"{cfg['dir']}/{os.path.relpath(p, root).replace(os.sep, '/')} (section no longer listed)", quiet=True)
        st["terms"][label] = {"code": code, "sections": len(sections), "files": len(files),
                              "last_checked": now_iso()}
        report.summary_line(SOURCE, f"{label}: {len(sections)} sections -> {len(files)} course files "
                                    f"({written} new, {updated} updated, {removed} removed)")
        if written or updated or removed:
            st["terms"][label]["last_changed"] = now_iso()
