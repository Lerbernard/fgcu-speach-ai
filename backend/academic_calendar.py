"""
academic_calendar.py
--------------------------------------------------------------------------
Gives the assistant a sense of "today" and which FGCU term we are in, so it
can answer "what semester is it?", "when does next semester start?",
"is registration open?", "this term / next term" correctly.

WHY THE DATES LIVE HERE (and aren't scraped live):
FGCU's per-term calendar pages (…/academiccalendar/terminfo?termid=NNN) block
automated access at runtime (robots), so the app can't pull term boundaries
live. They're maintained by hand below instead. Today's date is always read
from the clock, so it's never stale; only the term boundaries need a yearly
top-up.

The boundaries below were confirmed from the official calendar (scraped with
scrape_calendar_crawl4ai.py in June 2026): start = "Classes Begin", end = "Last
Day of the Semester" (for summer, the latest session's last day of classes).

>>> UPDATE THESE once a year: re-run scrape_calendar_crawl4ai.py, then copy the
    "Classes Begin" / "Last Day of the Semester" dates for each term into the
    table below. Official calendar: https://www.fgcu.edu/academics/academiccalendar/
--------------------------------------------------------------------------
"""

from datetime import date, datetime

try:
    from zoneinfo import ZoneInfo            # stdlib 3.9+
    _TZ = ZoneInfo("America/New_York")       # FGCU is Eastern
except Exception:
    _TZ = None


# Main full-term semesters only (sessions A/B/C overlap, so they'd make
# "current term" ambiguous). name, start, end (inclusive of finals week).
# end = last day of the term (≈ end of finals), start = first day of classes.
TERMS = [
    # name            start (classes begin)  end (last day of semester / latest session)
    # Confirmed from the official FGCU calendar (scraped June 2026).
    ("Spring 2026", date(2026, 1, 7),  date(2026, 5, 2)),
    ("Summer 2026", date(2026, 5, 11), date(2026, 8, 8)),
    ("Fall 2026",   date(2026, 8, 17), date(2026, 12, 4)),
    ("Spring 2027", date(2027, 1, 11), date(2027, 4, 30)),
    ("Summer 2027", date(2027, 5, 10), date(2027, 8, 14)),
    # Fall 2027 not yet published on the official calendar as of June 2026.
]


def today_eastern() -> date:
    """Current date in FGCU's timezone (falls back to naive local)."""
    now = datetime.now(_TZ) if _TZ else datetime.now()
    return now.date()


def _fmt(d: date) -> str:
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def _fmt_full(d: date) -> str:
    return f"{d.strftime('%A')}, {d.strftime('%B')} {d.day}, {d.year}"


def current_and_upcoming(today: date = None):
    """Return (current_term, upcoming_term, on_break).
    current_term is None when today falls in a break between terms."""
    if today is None:
        today = today_eastern()
    ordered = sorted(TERMS, key=lambda t: t[1])
    current = next((t for t in ordered if t[1] <= today <= t[2]), None)
    upcoming = next((t for t in ordered if t[1] > today), None)
    on_break = current is None
    return current, upcoming, on_break


def calendar_directive(today: date = None) -> str:
    """A short factual block to prepend to the model prompt. Today's date is
    authoritative (from the clock); term names/dates come from the table above."""
    if today is None:
        today = today_eastern()
    current, upcoming, on_break = current_and_upcoming(today)
    lines = [f"\n\nToday's date is {_fmt_full(today)}."]
    if current:
        lines.append(f"The current FGCU term is {current[0]} "
                     f"({_fmt(current[1])} – {_fmt(current[2])}).")
    else:
        lines.append("FGCU is between terms right now (semester break).")
    if upcoming:
        lines.append(f"The next/upcoming term is {upcoming[0]}, "
                     f"which begins {_fmt(upcoming[1])}.")
    lines.append("This today's-date line is the only source of truth for what "
                 "day it is and which term is current. Never infer the current "
                 "date or current semester from dates that appear in the context "
                 "documents. Use today's date and these terms when the student asks "
                 "about 'this semester', 'next semester', 'current term', when classes "
                 "start, or registration timing. If asked for an exact deadline "
                 "you don't have, point them to the FGCU Academic Calendar rather "
                 "than guessing.")
    return " ".join(lines)


if __name__ == "__main__":
    for t in ["2026-06-19", "2026-07-30", "2026-08-25", "2026-12-20", "2027-01-15"]:
        d = date.fromisoformat(t)
        c, u, br = current_and_upcoming(d)
        print(f"{t}: current={c[0] if c else 'BREAK':12} upcoming={u[0] if u else '-'}")
    print("\n--- directive (today) ---")
    print(calendar_directive(date(2026, 6, 19)))
