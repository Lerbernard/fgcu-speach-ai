"""
Academic calendar. The main calendar page carries an "Important Upcoming
Dates" table, which becomes academic_calendar/upcoming-dates.md.

The per-term pages (terminfo?termid=NNN) hold the full date lists behind the
other files in that folder, but www.fgcu.edu/robots.txt disallows every URL
with a query string, so this updater does not fetch them. Instead it watches
the list of term links: when a new term appears, the report asks for a manual
top-up of academic_calendar/*.md and the TERMS table in backend/academic_calendar.py.
"""
import re

from bs4 import BeautifulSoup

from common import abs_path, read_text, write_text, sha, now_iso, today

SOURCE = "academic_calendar"
UPCOMING_FILE = "upcoming-dates.md"


def norm(s):
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def parse_upcoming(soup):
    """[(event, date)] from the first Event/Date table, exact repeats dropped
    (the page lists some rows once per session with identical text)."""
    for table in soup.select("table"):
        head = [norm(c.get_text()).lower() for c in table.find("tr").find_all(["th", "td"])] if table.find("tr") else []
        if head[:2] != ["event", "date"]:
            continue
        seen, out = set(), []
        for tr in table.find_all("tr")[1:]:
            cells = [norm(c.get_text()) for c in tr.find_all(["td", "th"])]
            if len(cells) < 2 or (cells[0], cells[1]) in seen:
                continue
            seen.add((cells[0], cells[1]))
            out.append((cells[0], cells[1]))
        return out
    return []


def parse_term_links(soup):
    """{termid: label} for every per-term calendar page the site links to."""
    out = {}
    for a in soup.select('a[href*="terminfo?termid="]'):
        m = re.search(r"termid=(\d+)", a["href"])
        if m:
            out[m.group(1)] = norm(a.get_text())
    return out


def render_upcoming(rows, url):
    L = [f"<!-- source: {url} -->", "", "# FGCU Academic Calendar — Important Upcoming Dates", "",
         f"Key dates listed on the official academic calendar as of {today().isoformat()}. "
         "Full date lists for each term and session are in the other academic calendar files.", ""]
    for event, when in rows:
        L.append(f"- {event}: {when}")
    return "\n".join(L).rstrip() + "\n"


def run(manifest, state, fetch, report, dry_run=False, limit=None):
    cfg = manifest["academic_calendar"]
    st = state.setdefault("academic_calendar", {})
    try:
        r = fetch.get(cfg["url"])
        r.raise_for_status()
    except Exception as e:
        report.error(SOURCE, f"{type(e).__name__}: {e}")
        return
    soup = BeautifulSoup(r.text, "html.parser")
    st["last_checked"] = now_iso()

    rows = parse_upcoming(soup)
    if not rows:
        report.warn(SOURCE, "upcoming-dates table not found; file kept as-is")
    else:
        rel = f"{cfg['dir']}/{UPCOMING_FILE}"
        text = render_upcoming(rows, cfg["url"])
        path = abs_path(rel)
        old = read_text(path)
        # the "as of" date changes daily; compare everything below the header
        same = old is not None and old.split("\n", 6)[-1] == text.split("\n", 6)[-1]
        if same:
            report.unchanged(SOURCE)
        else:
            if not dry_run:
                write_text(path, text)
            report.written(SOURCE, rel, "updated" if old is not None else "new")
            st["last_changed"] = now_iso()

    links = parse_term_links(soup)
    prev = st.get("term_pages", {})
    for tid, label in links.items():
        if prev and tid not in prev:
            report.watch_changed(f"academic calendar term '{label}'", cfg["url"], None,
                                 detail="new term published: add its dates to academic_calendar/ and "
                                        "backend/academic_calendar.py TERMS (term pages are not fetched; robots.txt)")
    st["term_pages"] = links
