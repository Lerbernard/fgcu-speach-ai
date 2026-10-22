"""Pure helpers behind ingest.py / ingest_incremental.py."""
import pytest

import chunking


@pytest.mark.parametrize("filename,expected", [
    ("COP_1500_Fall_2025.md", "fall 2025"),
    ("BCN_3240C_Spring_2027.md", "spring 2027"),
    # calendar files are hyphenated; without this they had no term and every
    # calendar question naming a term matched nothing
    ("fall-2026.md", "fall 2026"),
    ("fall-2026-session-a-1st-7-weeks.md", "fall 2026"),
    ("upcoming-dates-spring-2027.md", "spring 2027"),
    ("00-about-the-calendar.md", ""),
    ("www_fgcu_edu_eng.md", ""),
    ("allen_paul.md", ""),
])
def test_get_term(filename, expected):
    assert chunking.get_term(filename) == expected


def test_get_doc_type_examples():
    assert chunking.get_doc_type("academic_calendar/fall-2026.md", "fall-2026.md") == "calendar"
    assert chunking.get_doc_type("courses/courses/courses_Fall_2026/COP_Fall_2026_courses/COP_1500_Fall_2026.md",
                                 "COP_1500_Fall_2026.md") == "course_offering"
    assert chunking.get_doc_type("course_descriptions/COP_descriptions/COP_1500_description.md",
                                 "COP_1500_description.md") == "course_description"
    assert chunking.get_doc_type("pages/engineering_student_life/engineering_student_life/events/ai-day.md",
                                 "ai-day.md") == "event"
    assert chunking.get_doc_type("pages/engineering_faculty/allen_paul.md", "allen_paul.md") == "faculty"


def test_build_chunks_ids_depend_on_path_not_just_filename():
    text = "# Title\n\nSome body text long enough to keep.\n\n**Section**\nMore text here."
    meta = {"source": "x.md"}
    a = chunking.build_chunks("clubs/x.md", text, meta)
    b = chunking.build_chunks("events/x.md", text, meta)
    assert [c[0] for c in a] != [c[0] for c in b]          # same filename, different folders
    assert a == chunking.build_chunks("clubs/x.md", text, meta)  # deterministic
    titles = [c[2]["title"] for c in a]
    assert titles == ["Title", "Section"]                    # bold-only lines split sections


def test_normalize_event_dates_rewrites_grid_rows():
    row = "| AI Day | /img/ai.jpg | 02 | 11 | 2026 | 1 | 3 | Holmes Hall | A panelist talk |"
    out = chunking.normalize_event_dates(row)
    assert out.startswith("AI Day — November 2, 2026.")
    assert "Holmes Hall" in out and "/img/ai.jpg" not in out
    assert chunking.normalize_event_dates("plain text") == "plain text"
