"""Pure pieces of the updater: HTML -> Markdown cleanup, calendar grouping,
course/description rendering, faculty profile parsing."""
import calendar_dates
import common
import courses
import descriptions
import faculty


def test_unwrap_paragraphs_joins_prose_but_keeps_blocks():
    text = ("# Heading\n"
            "Florida Gulf Coast University\nis a public university.\n"
            "\n"
            "* one item\n  continued here\n"
            "* two\n"
            "| a | b |\n")
    out = common.unwrap_paragraphs(text)
    assert "Florida Gulf Coast University is a public university." in out
    assert "* one item continued here" in out
    assert out.count("# Heading") == 1 and "| a | b |" in out


def test_clean_markdown_keeps_one_word_content_bullets_drops_nav():
    md = "* Bioengineering\n* Tagalog\n* Home\n* Apply\nMenu\nReal sentence here."
    out = common.clean_markdown(md)
    assert "* Bioengineering" in out and "* Tagalog" in out
    assert "* Home" not in out and "* Apply" not in out and "Menu" not in out


def test_page_to_markdown_drops_calendar_data_table_and_feeds():
    html = """<html><body><main class="main-content"><article>
      <h1>U.A. Whitaker College</h1><p>Welcome to the college.</p>
      <table class="tiva-events-calendar-data"><tr><td>name</td><td>day</td><td>month</td></tr>
        <tr><td>WCE Career Expo</td><td>06</td><td>10</td></tr></table>
      <section class="text-container newsfeed"><p>Fan Fest tonight</p></section>
      <p>Open to all majors.</p></article></main></body></html>"""
    out = common.page_to_markdown(html, "https://www.fgcu.edu/eng/")
    assert out.startswith("<!-- source: https://www.fgcu.edu/eng/ -->")
    assert "Welcome to the college." in out and "Open to all majors." in out
    assert "06" not in out and "Fan Fest" not in out


def test_group_by_term_splits_rows_and_strips_hints():
    rows = [("Web Registration Begins (see the Eagle Priority Registration page for precise dates) - Spring 2027 (Full Term)",
             "Monday, 19 October 2026"),
            ("Study Day (no classes) - Fall 2026 (Session B)", "Tuesday, 27 October 2026"),
            ("Commencement", "Saturday, 5 December 2026")]
    g = calendar_dates.group_by_term(rows)
    assert g["Spring 2027"] == [("Web Registration Begins", "Full Term", "Monday, 19 October 2026")]
    assert g["Fall 2026"] == [("Study Day (no classes)", "Session B", "Tuesday, 27 October 2026")]
    assert g[""] == [("Commencement", "", "Saturday, 5 December 2026")]
    assert calendar_dates.upcoming_filename("Spring 2027") == "upcoming-dates-spring-2027.md"
    assert calendar_dates.upcoming_filename("") == "upcoming-dates.md"


def test_render_tree_matches_existing_course_file_layout():
    sections = [{"crn": "86052", "course": "BCN 1210C", "title": "Construction Materials", "credits": "4",
                 "instructor": "Wao, Joel", "schedule": "Class: M 01:30pm - 05:15pm Holmes Engineering 302",
                 "part": "Full Term"}]
    files = courses.render_tree("Fall 2026", sections)
    (path, text), = files.items()
    assert path == "courses_Fall_2026/BCN_Fall_2026_courses/BCN_1210C_Fall_2026.md"
    assert text.splitlines()[0] == "# BCN 1210C — Construction Materials — Fall 2026"
    assert "BCN 1210C Fall 2026 — Instructor: Wao, Joel" in text
    assert "Course: Construction Materials (4 credits) | CRN: 86052" in text
    assert courses.term_slug("Fall 2026") == "Fall_2026"


def test_render_description_layout():
    text = descriptions.render({"code": "COP 3530", "title": "Data Structures & Algorithms - 3 credits(s)",
                                "desc": "Data structure design.", "extras": [("Prerequisite(s)", "COP 3003")]})
    assert text.splitlines()[:5] == ["# COP 3530 — Course Description", "", "Subject: COP | Course: COP 3530",
                                     "", "COP 3530"]
    assert " Prerequisite(s)\n COP 3003" in text


PROFILE_HTML = """<html><body><section class="faculty-detail">
<div class="news-events-detail-header-outer"><div class="topprofile">
  <h2 id="fullname">Kagdi, Huzefa (Ph.D.)</h2>
  <div id="jobtitle"><strong>Dean, Professor</strong></div>
  <div><span id="department">Provost Office</span></div></div>
  <div class="bottomprofile"><div><a href="tel:1">239-745-4466</a></div>
  <div><a href="mailto:h@fgcu.edu">h@fgcu.edu</a></div><div><span> HOLMES 0209</span></div></div></div>
<div class="container-flex row">
  <p>First paragraph of the
     bio wraps in the source.<br/>Second paragraph.</p>
  <p><a href="x">View my portfolio</a></p>
  <div class="container-flex accordion-wrapper"><ul>
   <li><p class="accordion-title">Education</p><a class="toggle-accordion"><span>Toggle Education</span></a>
     <div class="more-info"><ul><li>Ph.D. CS</li><li>B.E. CE</li></ul></div></li>
   <li><p class="accordion-title">Research and Teaching Interests</p><a><span>Toggle Research</span></a>
     <div class="more-info"><ul><li>Software analytics</li></ul>Memberships<br/><ul><li>ACM</li></ul></div></li>
  </ul></div><a class="backbtn">Back to List</a></div></section></body></html>"""


def test_profile_to_markdown_layout_and_section_order():
    out = faculty.profile_to_markdown(PROFILE_HTML).splitlines()
    assert out[:6] == ["## Kagdi, Huzefa (Ph.D.)", "**Dean, Professor**", "Provost Office",
                       "239-745-4466", "h@fgcu.edu", "HOLMES 0209"]
    assert "First paragraph of the bio wraps in the source." in out
    assert "Second paragraph." in out
    assert "View my portfolio" not in "\n".join(out)
    body = "\n".join(out)
    assert body.index("**Education**") < body.index("- Ph.D. CS") < body.index("**Research and Teaching Interests**")
    # text label before a list inside a section becomes a bold sub-heading, in order
    assert body.index("- Software analytics") < body.index("**Memberships**") < body.index("- ACM")
    assert faculty.name_to_filename("Kagdi, Huzefa (Ph.D.)") == "kagdi_huzefa"
    assert faculty.name_to_filename("Al Suleh, Munir") == "al_suleh_munir"
