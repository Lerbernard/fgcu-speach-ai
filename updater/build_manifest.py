"""
build_manifest.py - one-time helper that maps every existing data file back to
the web page it came from and writes updater/sources.yaml.

The original scrapers (crawl4ai scripts, never committed) named files after
their URL with every "/" and "." turned into "_", so the URL is recoverable by
trying each way of putting the slashes back and keeping the candidate that
exists in FGCU's sitemap. Hand-named files are covered by OVERRIDES. Whatever
still can't be matched is listed under `unmapped:` in the output for a human.

    python updater/build_manifest.py            # resolve via sitemap only (fast)
    python updater/build_manifest.py --verify   # also GET every URL, drop 404s

Run it once; afterwards edit sources.yaml by hand when pages are added.
"""
import argparse
import itertools
import os
import re
import sys
import time

import requests
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(HERE, "sources.yaml")
SITEMAP = "https://www.fgcu.edu/sitemap.xml"
UA = "Mozilla/5.0 (compatible; AskTheEagleBot/1.0; +https://github.com/Lerbernard/fgcu-speach-ai)"

# Hand-named files -> source URL. mode "watch" means the file was edited or
# restructured by hand after scraping, so the updater must never overwrite it;
# it only reports when the page changes so someone can refresh it manually.
OVERRIDES = {
    # advising (scrape_advising.py)
    "pages/engineering_programs/advising/eng_advising.md": ("https://www.fgcu.edu/eng/advising/", "watch"),
    "pages/engineering_programs/advising/eng_advising_advisingsyllabus.md": ("https://www.fgcu.edu/eng/advising/advisingsyllabus", "watch"),
    "pages/engineering_programs/advising/eng_advising_transientstudentinstructions.md": ("https://www.fgcu.edu/eng/advising/transientstudentinstructions", "watch"),
    "pages/engineering_programs/advising/academics_advising_holds.md": ("https://www.fgcu.edu/academics/advising/holdskey", "watch"),
    "pages/engineering_programs/advising/academics_advising_faq.md": ("https://www.fgcu.edu/academics/advising/faq", "watch"),
    "pages/engineering_programs/advising/studentcomplaints.md": ("https://www.fgcu.edu/studentcomplaints/", "watch"),
    # catalog program pages (scrape_programs.py / scrape_minors_grad.py / scrape_cs_program.py)
    "pages/engineering_programs/bioengineering_bs/programs_bioengineering-bs.md": ("https://catalog.fgcu.edu/programs/bioengineering-bs/", "watch"),
    "pages/engineering_programs/civil_engineering_bsce/programs_civil-engineering-bsce.md": ("https://catalog.fgcu.edu/programs/civil-engineering-bsce/", "watch"),
    "pages/engineering_programs/construction_management_bscm/programs_construction-management-bscm.md": ("https://catalog.fgcu.edu/programs/construction-management-bscm/", "watch"),
    "pages/engineering_programs/environmental_engineering_bsenve/programs_environmental-engineering-bsenve.md": ("https://catalog.fgcu.edu/programs/environmental-engineering-bsenve/", "watch"),
    "pages/engineering_programs/software_engineering_bs/programs_software-engineering-bs.md": ("https://catalog.fgcu.edu/programs/software-engineering-bs/", "watch"),
    "pages/engineering_programs/graduate/programs_civil_engineering_ms.md": ("https://catalog.fgcu.edu/programs/ms-civengr/", "watch"),
    "pages/engineering_programs/graduate/programs_computer_science_ms.md": ("https://catalog.fgcu.edu/programs/computer-science-ms/", "watch"),
    "pages/engineering_programs/minors/programs_bioengineering_minor.md": ("https://www.fgcu.edu/eng/bioengineering-civilengineering-environmentalengineering/bioengineering-minor", "watch"),
    "pages/engineering_programs/minors/programs_computer_science_minor.md": ("https://www.fgcu.edu/eng/computing-software-engineering/computerscience-minor", "watch"),
    "pages/engineering_programs/minors/programs_environmental_engineering_minor.md": ("https://www.fgcu.edu/eng/bioengineering-civilengineering-environmentalengineering/enve-minor", "watch"),
    "pages/engineering_programs/fgcu_engineering_graduate_programs.md": ("https://www.fgcu.edu/eng/graduateprograms/", "watch"),
    "pages/engineering_programs/computer_science_bs/programs_computer-science-bs_requirements.md": ("https://catalog.fgcu.edu/programs/computer-science-bs/", "watch"),
    "pages/engineering_programs/computer_science_bs/programs_computer-science-bs_concentrations.md": ("https://catalog.fgcu.edu/programs/computer-science-bs/", "watch"),
    "pages/engineering_programs/computer_science_bs/programs_computer-science-bs_ai_and_data_science_concentration.md": ("https://catalog.fgcu.edu/programs/computer-science-bs/", "watch"),
    "pages/engineering_programs/computer_science_bs/programs_computer-science-bs_computer_science_no_concentration.md": ("https://catalog.fgcu.edu/programs/computer-science-bs/", "watch"),
    "pages/engineering_programs/computer_science_bs/programs_computer-science-bs_cybersecurity_concentration.md": ("https://catalog.fgcu.edu/programs/computer-science-bs/", "watch"),
    "pages/engineering_programs/computer_science_bs/programs_computer-science-bs_software_engineering_concentration.md": ("https://catalog.fgcu.edu/programs/computer-science-bs/", "watch"),
    # department program pages (scrape_programs.py)
    "pages/engineering_programs/bioengineering_bs/eng_bioengineering-bs.md": ("https://www.fgcu.edu/eng/bioengineering-civilengineering-environmentalengineering/bioengineering-bs", "auto"),
    "pages/engineering_programs/civil_engineering_bsce/eng_civil-engineering-bsce.md": ("https://www.fgcu.edu/eng/bioengineering-civilengineering-environmentalengineering/civileng-bsce", "auto"),
    "pages/engineering_programs/computer_science_bs/eng_computerscience-bs.md": ("https://www.fgcu.edu/eng/computing-software-engineering/computerscience-bs", "auto"),
    "pages/engineering_programs/construction_management_bscm/eng_construction-management-bscm.md": ("https://www.fgcu.edu/eng/constructionmanagement/constructionmanagement-bs", "auto"),
    "pages/engineering_programs/environmental_engineering_bsenve/eng_environmental-engineering-bsenve.md": ("https://www.fgcu.edu/eng/bioengineering-civilengineering-environmentalengineering/enve-bs", "auto"),
    "pages/engineering_programs/software_engineering_bs/eng_software-engineering-bs.md": ("https://www.fgcu.edu/eng/computing-software-engineering/softwareengineering-bs", "auto"),
    # the university home page: an empty stem after stripping the host prefix
    "pages/about_fgcu/www_fgcu_edu.md": ("https://www.fgcu.edu/", "auto"),
    # the faculty LIST page (profiles themselves are generated by faculty.py)
    "pages/engineering_faculty/www_fgcu_edu_eng_facultystaff.md": ("https://www.fgcu.edu/eng/facultystaff/", "auto"),
    # student involvement / events (hand-written summaries of the involvement page)
    "pages/engineering_learning_support/learning_hub.md": ("https://www.fgcu.edu/eng/student-involvement/learning-hub/", "watch"),
    "pages/engineering_student_life/engineering_student_life/wce-ambassadors.md": ("https://www.fgcu.edu/eng/student-involvement/", "watch"),
    "pages/engineering_student_life/engineering_student_life/wce-involvement-overview.md": ("https://www.fgcu.edu/eng/student-involvement/", "watch"),
    "pages/engineering_student_life/engineering_student_life/wce-make-an-impact.md": ("https://www.fgcu.edu/eng/student-involvement/", "watch"),
    "pages/engineering_student_life/engineering_student_life/wce-news.md": ("https://www.fgcu.edu/eng/wce-news/", "watch"),
    "pages/engineering_student_life/engineering_student_life/internship-faq.md": ("https://www.fgcu.edu/eng/internships/", "watch"),
    "pages/engineering_student_life/engineering_student_life/research-opportunities.md": ("https://www.fgcu.edu/eng/research/", "watch"),
    "pages/engineering_student_life/engineering_student_life/events/order-of-the-engineer.md": ("https://www.fgcu.edu/eng/student-involvement/order-of-the-engineer/", "watch"),
    "pages/engineering_student_life/engineering_student_life/events/wce-day.md": ("https://www.fgcu.edu/eng/student-involvement/wce-day/", "watch"),
    "pages/engineering_student_life/engineering_student_life/events/concrete-expo.md": ("https://www.fgcu.edu/eng/internships/concrete-expo/", "watch"),
    "pages/engineering_student_life/engineering_student_life/events/concrete-expo-community.md": ("https://www.fgcu.edu/eng/internships/community-employer-involvement", "watch"),
}

# Folders/files the updater regenerates wholesale from a structured source, so
# they need no per-file entry here. Everything else unmatched gets reported.
GENERATED_PREFIXES = ("courses/", "course_descriptions/", "academic_calendar/",
                      "pages/engineering_faculty/")
# Hand-written files with no machine-readable source (club blurbs, calendar
# grid dump, per-event summaries). Listed under `manual:` so nobody wonders.
MANUAL_PREFIXES = ("pages/engineering_student_life/engineering_student_life/clubs/",
                   "pages/engineering_student_life/engineering_student_life/events/",
                   "pages/engineering_student_life/engineering_student_life/wce-calendar",
                   "pages/engineering_learning_support/service_learning")
MANUAL_FILES = {
    "pages/engineering_student_life/cssec-computer-science-software-engineering-club.md",
    "pages/engineering_student_life/holmes-is-your-home.md",
    "pages/engineering_student_life/swe-society-of-women-engineers-involvement.md",
}


def load_sitemap():
    r = requests.get(SITEMAP, headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    urls = set(re.findall(r"<loc>([^<]+)</loc>", r.text))
    # index both with and without trailing slash so either spelling matches
    return urls | {u.rstrip("/") for u in urls} | {u + "/" for u in urls if not u.endswith("/")}


def candidates(stem):
    """All URLs a scrape_all-style filename could have come from.
    'eng_technology_recommendations' -> eng/technology/recommendations,
    eng/technology_recommendations, eng_technology/recommendations, ..."""
    parts = stem.split("_")
    if len(parts) == 1:
        yield parts[0]
        return
    for seps in itertools.product(("/", "_"), repeat=len(parts) - 1):
        path = parts[0]
        for sep, p in zip(seps, parts[1:]):
            path += sep + p
        yield path


def resolve(stem, sitemap):
    """Pick the sitemap URL for a filename stem, fewest underscores first."""
    stem = re.sub(r"_part\d+$", "", stem)
    for prefix in ("www_fgcu_edu_", "fgcu_edu_", ""):
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
            break
    best = None
    for path in candidates(stem):
        for url in (f"https://www.fgcu.edu/{path}/", f"https://www.fgcu.edu/{path}"):
            if url in sitemap and (best is None or url.count("_") < best.count("_")):
                best = url
    return best


def verify(url):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30, allow_redirects=True)
        return r.status_code, r.url
    except requests.RequestException as e:
        return 0, str(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true", help="GET each URL and drop dead ones")
    args = ap.parse_args()

    sitemap = load_sitemap()
    print(f"sitemap: {len(sitemap)} url spellings")

    pages, manual, unmapped = [], [], []
    seen_paths = set()
    for root, dirs, files in os.walk(DATA):
        dirs[:] = [d for d in dirs if not d.startswith(".") and not d.endswith("_files")]
        for fn in sorted(files):
            if not fn.endswith(".md"):
                continue
            rel = os.path.relpath(os.path.join(root, fn), DATA).replace("\\", "/")
            if rel.startswith(GENERATED_PREFIXES) and rel not in OVERRIDES:
                continue
            if rel in MANUAL_FILES or rel.startswith(MANUAL_PREFIXES):
                if rel not in OVERRIDES:
                    manual.append(rel)
                    continue
            stem = fn[:-3]
            if rel in OVERRIDES:
                url, mode = OVERRIDES[rel]
            else:
                url, mode = resolve(stem, sitemap), "auto"
            if not url:
                unmapped.append(rel)
                continue
            base = re.sub(r"_part\d+(\.md)$", r"\1", rel)
            if base in seen_paths:        # _part2/_part3 collapse into the base file
                continue
            seen_paths.add(base)
            pages.append({"url": url, "path": base, "mode": mode})

    if args.verify:
        kept = []
        for i, p in enumerate(pages, 1):
            code, final = verify(p["url"])
            tag = "ok" if code == 200 else f"HTTP {code}"
            if code == 200 and final.rstrip("/") != p["url"].rstrip("/"):
                p["note"] = f"redirects to {final}"
                tag += f" -> {final}"
            print(f"[{i}/{len(pages)}] {tag}  {p['url']}")
            if code == 200:
                kept.append(p)
            else:
                p["note"] = f"dead ({tag})"
                unmapped.append(f"{p['path']}  ({p['url']} {tag})")
            time.sleep(0.5)
        pages = kept

    pages.sort(key=lambda p: p["path"])
    doc = {
        "version": 1,
        "defaults": {"user_agent": UA, "delay_seconds": 1.0, "timeout_seconds": 45},
        "pages": pages,
        "faculty": {
            "list_url": "https://www.fgcu.edu/eng/facultystaff/",
            "dir": "pages/engineering_faculty",
            "mode": "auto",
        },
        "courses": {
            "form_url": "https://gulfline.fgcu.edu/pls/fgpo/szkschd.p_showform",
            "college_code": "08",
            "dir": "courses/courses",
            "terms": ["Spring 2025", "Summer 2025", "Fall 2025",
                      "Spring 2026", "Summer 2026", "Fall 2026", "Spring 2027"],
            "auto_add_new_terms": True,
            "mode": "auto",
        },
        "course_descriptions": {
            "url": "https://fgcu-web02.fgcu.edu/CourseDescriptions/",
            "college_code": "08",
            "dir": "course_descriptions",
            "subjects": sorted(d[:-13] for d in os.listdir(os.path.join(DATA, "course_descriptions"))
                               if d.endswith("_descriptions")),
            "mode": "auto",
        },
        "academic_calendar": {
            "url": "https://www.fgcu.edu/academics/academiccalendar/",
            "dir": "academic_calendar",
            "mode": "auto",
        },
        "events": {
            "url": "https://www.fgcu.edu/eng/student-involvement/",
            "dir": "pages/engineering_student_life/engineering_student_life/events",
            "mode": "auto",
        },
        "manual": sorted(manual),
        "unmapped": sorted(unmapped),
    }
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("# Generated by updater/build_manifest.py - edit by hand after that.\n"
                "# mode: auto  = the updater rewrites the file when the page changes\n"
                "#       watch = hand-edited file; the updater only reports page changes\n")
        yaml.safe_dump(doc, f, sort_keys=False, allow_unicode=True, width=120)
    print(f"\npages: {len(pages)} ({sum(p['mode']=='auto' for p in pages)} auto, "
          f"{sum(p['mode']=='watch' for p in pages)} watch) | manual: {len(manual)} | unmapped: {len(unmapped)}")
    for u in unmapped:
        print("  UNMAPPED:", u)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    sys.exit(main())
