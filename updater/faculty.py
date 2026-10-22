"""
Faculty bios: the WCE faculty/staff list links to one directory profile per
person. Each profile becomes pages/engineering_faculty/<last_first>.md in the
same shape the old scrape_faculty.py + clean_faculty.py produced, which the
ingest pipeline reads the professor name from.
"""
import os
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from common import abs_path, read_text, write_text, sha, now_iso, shrink_check

SOURCE = "faculty"
MIN_LIST_LINKS = 30   # fewer than this means the list page broke, not that everyone left

# link-only lines the old clean_faculty.py dropped
_NAV_LINE = re.compile(r"^(View .*portfolio|View my publications\.?|Google Scholar|Linked-?In Profile:?|Back to List)$",
                       re.IGNORECASE)


def name_to_filename(name: str) -> str:
    """'Kagdi, Huzefa (Ph.D.)' -> 'kagdi_huzefa'; 'Al Suleh, Munir' -> 'al_suleh_munir'.
    ingest.get_professor() reverses this (underscores back to spaces)."""
    name = re.sub(r"\([^)]*\)", "", name)
    if "," in name:
        last, first = name.split(",", 1)
        name = f"{last} {first}"
    name = re.sub(r"[^\w\s]", "", name)
    return re.sub(r"\s+", "_", name.strip()).lower()


def list_profiles(html, list_url):
    """[(name, profile_url)] from the faculty list. Query strings (?list=1)
    are dropped: the plain /directory/<id> page has the same content and
    robots.txt disallows URLs with a query."""
    soup = BeautifulSoup(html, "html.parser")
    seen, out = set(), []
    for a in soup.select('a[href*="/directory/"]'):
        name = a.get_text(" ", strip=True)
        href = a.get("href", "")
        if not name or "," not in name:
            continue
        parts = urlsplit(urljoin(list_url, href))
        url = f"{parts.scheme}://{parts.netloc}{parts.path}"
        if url in seen or parts.path.rstrip("/").endswith("/directory"):
            continue
        seen.add(url)
        out.append((name, url))
    return out


def _text_lines(el):
    """Text of an element as lines: one per block child (div/p/li) when it has
    them, otherwise one per <br>. Newlines in the HTML source itself are just
    wrapping and are collapsed."""
    blocks = el.find_all(["div", "p", "li"], recursive=False)
    if blocks:
        lines = []
        for b in blocks:
            lines += _text_lines(b)
        return lines
    for br in el.find_all("br"):
        br.replace_with(" \x00 ")
    txt = re.sub(r"\s+", " ", el.get_text(" "))
    return [ln.strip() for ln in txt.split("\x00") if ln.strip()]


def _link_only(p):
    a = p.find("a")
    return a is not None and re.sub(r"\s+", " ", a.get_text(" ", strip=True)) == \
        re.sub(r"\s+", " ", p.get_text(" ", strip=True))


def profile_to_markdown(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    detail = soup.select_one("section.faculty-detail") or soup.select_one("main") or soup

    # ── header: name, title, department, phone / email / office ──
    head = detail.select_one(".news-events-detail-header-outer") or detail
    full = head.select_one("#fullname") or head.find(["h1", "h2"])
    fullname = full.get_text(" ", strip=True) if full else ""
    job = head.select_one("#jobtitle, .jobtitle")
    jobtitle = job.get_text(" ", strip=True) if job else ""
    out = [f"## {fullname}"]
    if jobtitle:
        out.append(f"**{jobtitle}**")
    dept = head.select_one("#department")
    if dept is not None:
        out += _text_lines(dept)
    bottom = head.select_one(".bottomprofile")
    if bottom is not None:
        out += _text_lines(bottom)
    elif dept is None:
        out += [ln for ln in _text_lines(head) if ln not in (fullname, jobtitle)]

    # ── body: bio paragraphs, then the accordion sections ──
    body = None
    for child in detail.find_all(True, recursive=False):
        if child is not head and child.get_text(strip=True):
            body = child
            break
    if body is None:
        return "\n".join(out).strip() + "\n"

    accordion = body.select_one(".accordion-wrapper")
    bio = []
    for p in body.find_all("p"):
        if accordion is not None and accordion in p.parents:
            continue
        if "accordion-title" in (p.get("class") or []) or _link_only(p):
            continue
        bio += [ln for ln in _text_lines(p) if not _NAV_LINE.match(ln)]
    if bio:
        out.append("\n".join(bio))

    if accordion is not None:
        for li in accordion.find_all("li"):
            title_el = li.find("p", class_="accordion-title", recursive=False)
            if title_el is None:
                continue
            title = re.sub(r"\s+", " ", title_el.get_text(" ", strip=True))
            info = li.select_one(".more-info")
            if info is None:
                continue
            lines = [ln for ln in _section_lines(info) if not ln.lower().startswith("toggle ")]
            if lines:
                out.append(f"\n**{title}**\n" + "\n".join(lines))
    return "\n".join(out).strip() + "\n"


def _section_lines(info):
    """Lines of an accordion section in document order: free text (split on
    <br>) and bullet lists interleave, e.g. 'Interests' list, then a
    'Memberships' label, then its list. A short label right before a list is
    bolded so ingest treats it as a sub-heading, as the old files did."""
    lines, buf = [], []

    def flush():
        txt = re.sub(r"\s+", " ", "".join(buf)).strip()
        buf.clear()
        if txt:
            lines.append(txt)

    def walk(node):
        for child in node.children:
            name = getattr(child, "name", None)
            if name is None:
                buf.append(str(child))
            elif name == "br":
                flush()
            elif name in ("ul", "ol"):
                flush()
                if lines and not lines[-1].startswith("- ") and len(lines[-1]) <= 40 \
                        and not lines[-1].endswith(".") and not lines[-1].startswith("**"):
                    lines[-1] = f"**{lines[-1]}**"
                for item in child.find_all("li"):
                    txt = " ".join(_text_lines(item))
                    if txt:
                        lines.append(f"- {txt}")
            elif name in ("p", "div"):
                flush()
                walk(child)
                flush()
            else:
                buf.append(child.get_text(" "))

    walk(info)
    flush()
    return lines


def run(manifest, state, fetch, report, dry_run=False, limit=None):
    cfg = manifest["faculty"]
    folder = abs_path(cfg["dir"])
    st = state.setdefault("faculty", {})
    try:
        r = fetch.get(cfg["list_url"])
        r.raise_for_status()
    except Exception as e:
        report.error(SOURCE, f"list page: {type(e).__name__}: {e}")
        return
    people = list_profiles(r.text, cfg["list_url"])
    if len(people) < MIN_LIST_LINKS:
        report.error(SOURCE, f"list page yielded only {len(people)} profiles; not touching faculty files")
        return
    st["list_count"] = len(people)
    st["last_checked"] = now_iso()

    produced, failed = set(), 0
    for name, url in people[:limit] if limit else people:
        fn = name_to_filename(name) + ".md"
        rel = f"{cfg['dir']}/{fn}"
        produced.add(fn)
        try:
            pr = fetch.get(url)
            if pr.status_code != 200:
                raise RuntimeError(f"HTTP {pr.status_code}")
            md = profile_to_markdown(pr.text)
        except Exception as e:
            failed += 1
            report.error(SOURCE, f"{name}: {type(e).__name__}: {e} ({url})")
            continue
        if len(md) < 60:
            failed += 1
            report.warn(SOURCE, f"{name}: profile came back nearly empty, kept old file")
            continue
        path = os.path.join(folder, fn)
        old = read_text(path)
        if old is not None and sha(old) == sha(md):
            report.unchanged(SOURCE)
            continue
        ok, why = shrink_check(old, md)
        if not ok:
            report.warn(SOURCE, f"{rel}: NOT replaced, {why}")
            continue
        if not dry_run:
            write_text(path, md)
        report.written(SOURCE, rel, "updated" if old is not None else "new")

    # People no longer on the list: remove their bio so the assistant stops
    # presenting them as current faculty. Only top-level profile files count:
    # the ratemyprofessors/ subfolder is hand-maintained and www_*.md is the
    # saved list page itself (an ordinary `pages` entry).
    if limit or failed:
        return
    for fn in sorted(os.listdir(folder)):
        if fn.endswith(".md") and not fn.startswith("www_") and fn not in produced:
            if not dry_run:
                os.remove(os.path.join(folder, fn))
            report.removed(SOURCE, f"{cfg['dir']}/{fn} (no longer on the faculty list)")
