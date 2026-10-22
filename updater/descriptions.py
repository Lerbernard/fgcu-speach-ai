"""
Catalog course descriptions for the College of Engineering, from the
CourseDescriptions search (one POST for the whole college). Writes one file
per course, course_descriptions/<SUBJ>_descriptions/<SUBJ>_<NUM>_description.md,
in the layout the existing files use.
"""
import os
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from common import abs_path, read_text, write_text, sha, now_iso

SOURCE = "course_descriptions"
MIN_COURSES = 100      # the college lists ~280; far fewer means the search broke
MAX_TERM_TRIES = 4     # newest terms may have no catalog yet; walk back a few


def norm(s):
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def term_options(html):
    soup = BeautifulSoup(html, "html.parser")
    sel = soup.select_one('select[name="term"]')
    return [(o.get("value", ""), norm(o.get_text())) for o in sel.find_all("option") if o.get("value")]


def parse_courses(html):
    """[{code, title, desc, extras: [(label, text)]}] from the results table.
    Rows come in runs: CatalogCourseTitle (code | 'Title - N credits(s)'),
    CatalogCourseDesc, then zero or more Catalog*Title / Catalog*Course pairs
    such as Prerequisite(s) / Corequisite(s)."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find(id="tblAcademicPeriod") or soup
    courses, cur = [], None
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        classes = " ".join(" ".join(td.get("class", [])) for td in tds)
        if "CatalogCourseTitle" in classes and len(tds) >= 2:
            cur = {"code": norm(tds[0].get_text()), "title": norm(tds[1].get_text()),
                   "desc": "", "extras": []}
            courses.append(cur)
        elif cur is None:
            continue
        elif "CatalogCourseDesc" in classes:
            cur["desc"] = norm(tds[-1].get_text())
        elif len(tds) >= 2 and re.search(r"Catalog\w+Title", classes):
            cur["extras"].append((norm(tds[0].get_text()), norm(tds[1].get_text())))
    return [c for c in courses if re.fullmatch(r"[A-Z]{3}\s?\d{4}[A-Z]?", c["code"])]


def render(c):
    code = re.sub(r"\s+", " ", c["code"])
    subj = code.split()[0]
    lines = [f"# {code} — Course Description", "", f"Subject: {subj} | Course: {code}", "",
             code, f" {c['title']}", f" {c['desc']}"]
    for label, text in c["extras"]:
        lines += [f" {label}", f" {text}"]
    return "\n".join(lines).rstrip() + "\n"


def run(manifest, state, fetch, report, dry_run=False, limit=None):
    cfg = manifest["course_descriptions"]
    root = abs_path(cfg["dir"])
    st = state.setdefault("course_descriptions", {})
    try:
        r = fetch.get(cfg["url"])
        r.raise_for_status()
        terms = term_options(r.text)
    except Exception as e:
        report.error(SOURCE, f"search form: {type(e).__name__}: {e}")
        return
    action = urljoin(cfg["url"], "SearchResults")
    # The newest term's catalog is often still being filled in, so take the
    # fullest listing among the newest few terms (ties go to the newest).
    courses, used_term = [], None
    for code, label in terms[:MAX_TERM_TRIES]:
        try:
            rr = fetch.post(action, {"term": code, "coll": cfg["college_code"], "srchtype": "0",
                                     "numb": "", "srchtext": ""})
            rr.raise_for_status()
        except Exception as e:
            report.error(SOURCE, f"{label}: {type(e).__name__}: {e}")
            continue
        found = parse_courses(rr.text)
        report.summary_line(SOURCE, f"{label}: {len(found)} courses listed")
        if len(found) > len(courses):
            courses, used_term = found, label
    if len(courses) < MIN_COURSES:
        report.error(SOURCE, f"no term returned a full catalog (best: {len(courses)}); files kept as-is")
        return
    st.update(last_checked=now_iso(), term=used_term, courses=len(courses))

    produced, new, updated = set(), 0, 0
    for c in courses[:limit] if limit else courses:
        code = re.sub(r"\s+", " ", c["code"])
        subj, num = code.split()
        rel = f"{subj}_descriptions/{subj}_{num}_description.md"
        produced.add(os.path.normpath(os.path.join(root, rel)))
        path = os.path.join(root, rel.replace("/", os.sep))
        text = render(c)
        old = read_text(path)
        if old is not None and sha(old) == sha(text):
            continue
        if not dry_run:
            write_text(path, text)
        new += old is None
        updated += old is not None
        report.written(SOURCE, f"{cfg['dir']}/{rel}", "updated" if old is not None else "new", quiet=True)

    removed = 0
    if not limit:
        for dp, _, fns in os.walk(root):
            for fn in fns:
                p = os.path.normpath(os.path.join(dp, fn))
                if fn.endswith("_description.md") and p not in produced:
                    if not dry_run:
                        os.remove(p)
                    removed += 1
                    report.removed(SOURCE, f"{cfg['dir']}/{os.path.relpath(p, root).replace(os.sep, '/')} (no longer in the catalog)", quiet=True)
    report.summary_line(SOURCE, f"{used_term}: {len(courses)} courses ({new} new, {updated} updated, {removed} removed)")
    if new or updated or removed:
        st["last_changed"] = now_iso()
