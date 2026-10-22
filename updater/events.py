"""
WCE events, from the student-involvement page. Two generated files:

  events/wce-events-calendar.md  dated entries from the page's calendar table
  events/wce-annual-events.md    the "events you can attend" descriptions

The hand-written per-event files in the same folder are left alone; when a
calendar entry changes, the report names it so someone can refresh them.
"""
import re
from datetime import date

from bs4 import BeautifulSoup

from common import abs_path, read_text, write_text, sha, now_iso

SOURCE = "events"
CALENDAR_FILE = "wce-events-calendar.md"
ANNUAL_FILE = "wce-annual-events.md"
_MONTHS = ["", "January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]


def norm(s):
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def parse_calendar(soup):
    """Rows of the tiva-events-calendar-data table as dicts keyed by header."""
    table = soup.select_one("table.tiva-events-calendar-data")
    if table is None:
        return []
    rows = table.find_all("tr")
    headers = [norm(c.get_text()).lower() for c in rows[0].find_all(["th", "td"])]
    out = []
    for tr in rows[1:]:
        cells = [norm(c.get_text()) for c in tr.find_all(["td", "th"])]
        if len(cells) < len(headers):
            continue
        row = dict(zip(headers, cells))
        try:
            row["date"] = date(int(row["year"]), int(row["month"]), int(row["day"]))
        except (KeyError, ValueError):
            continue
        out.append(row)
    out.sort(key=lambda r: (r["date"], r.get("name", "")))
    return out


def parse_annual(soup):
    """[(heading, description)] from the Events accordion sections."""
    box = soup.find(id="Events") or soup.find(id="events")
    if box is None:
        return []
    out = []
    for sec in box.find_all("section"):
        head = sec.find(["h3", "h4", "h2", "strong"])
        if not head:
            continue
        title = norm(head.get_text())
        paras = [norm(p.get_text()) for p in sec.find_all("p")
                 if norm(p.get_text()) and head not in p.descendants and p is not head]
        if title and paras:
            out.append((title, " ".join(paras)))
    return out


def render_calendar(rows, url):
    L = ["<!-- source: %s -->" % url, "", "# WCE Events Calendar",
         "",
         "Official dates from the U.A. Whitaker College of Engineering events calendar. "
         "When another page gives a different date for one of these events, these dates are the current ones.",
         ""]
    # One bold-only line per event: ingest splits on those, so every event
    # becomes its own chunk titled with its name.
    for r in rows:
        d = r["date"]
        line = f"{r['name']} — {_MONTHS[d.month]} {d.day}, {d.year}"
        if r.get("time"):
            line += f" ({r['time']})"
        line += "."
        if r.get("location"):
            line += f" Location: {r['location']}."
        if r.get("description"):
            line += f" {r['description']}"
        L += [f"**{r['name']}**", line, ""]
    return "\n".join(L).rstrip() + "\n"


def render_annual(items, url):
    L = ["<!-- source: %s -->" % url, "", "# WCE Annual Events", "",
         "Events students can attend during the year, as described by the college. "
         "Exact dates for the current year are in the WCE Events Calendar.", ""]
    for title, desc in items:
        L += [f"**{title}**", desc, ""]
    return "\n".join(L).rstrip() + "\n"


def _write(rel, text, report, dry_run):
    path = abs_path(rel)
    old = read_text(path)
    if old is not None and sha(old) == sha(text):
        report.unchanged(SOURCE)
        return False
    if not dry_run:
        write_text(path, text)
    report.written(SOURCE, rel, "updated" if old is not None else "new")
    return True


def run(manifest, state, fetch, report, dry_run=False, limit=None):
    cfg = manifest["events"]
    st = state.setdefault("events", {})
    try:
        r = fetch.get(cfg["url"])
        r.raise_for_status()
    except Exception as e:
        report.error(SOURCE, f"{type(e).__name__}: {e}")
        return
    soup = BeautifulSoup(r.text, "html.parser")
    rows, annual = parse_calendar(soup), parse_annual(soup)
    st["last_checked"] = now_iso()
    if not rows:
        report.warn(SOURCE, "calendar table not found on the page; events files kept as-is")
    else:
        snapshot = {r["name"]: f"{r['date'].isoformat()} {r.get('time', '')} {r.get('location', '')}".strip()
                    for r in rows}
        prev = st.get("calendar", {})
        for name, val in snapshot.items():
            if name in prev and prev[name] != val:
                report.watch_changed(f"event '{name}'", cfg["url"], None,
                                     detail=f"{prev[name]} -> {val}; check the hand-written file for it")
            elif prev and name not in prev:
                report.summary_line(SOURCE, f"new calendar entry: {name} ({val})")
        for name in prev:
            if name not in snapshot:
                report.summary_line(SOURCE, f"calendar entry gone: {name}")
        st["calendar"] = snapshot
        if _write(f"{cfg['dir']}/{CALENDAR_FILE}", render_calendar(rows, cfg["url"]), report, dry_run):
            st["last_changed"] = now_iso()
    if not annual:
        report.warn(SOURCE, "annual events section not found; file kept as-is")
    elif _write(f"{cfg['dir']}/{ANNUAL_FILE}", render_annual(annual, cfg["url"]), report, dry_run):
        st["last_changed"] = now_iso()
