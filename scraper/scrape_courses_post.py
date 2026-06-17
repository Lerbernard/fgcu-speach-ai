import asyncio
import os
import re
import httpx
from bs4 import BeautifulSoup

RESULT_URL = "https://gulfline.fgcu.edu/pls/fgpo/szkschd.p_showresult"
OUTPUT_DIR = "..\\data\\courses"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://gulfline.fgcu.edu/pls/fgpo/szkschd.p_showform",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Origin": "https://gulfline.fgcu.edu",
}

# All available terms
TERMS = [
    ("202608", "Fall_2026"),
    ("202605", "Summer_2026"),
    ("202601", "Spring_2026"),
    ("202508", "Fall_2025"),
    ("202505", "Summer_2025"),
    ("202501", "Spring_2025"),
    ("202408", "Fall_2024"),
    ("202405", "Summer_2024"),
    ("202401", "Spring_2024"),
    ("202308", "Fall_2023"),
    ("202305", "Summer_2023"),
    ("202301", "Spring_2023"),
    ("202208", "Fall_2022"),
    ("202205", "Summer_2022"),
    ("202201", "Spring_2022"),
    ("202108", "Fall_2021"),
    ("202105", "Summer_2021"),
    ("202101", "Spring_2021"),
    ("202008", "Fall_2020"),
    ("202005", "Summer_2020"),
    ("202001", "Spring_2020"),
]

async def fetch_all_engineering(client, term_code):
    """Fetch ALL engineering classes — College=Engineering, Dept=empty."""
    form_data = {
        "Termcode":        term_code,
        "Sess":            "",
        "Campcode":        "",
        "CollegeCode":     "08",   # Engineering
        "Deptcode":        "",     # All departments
        "Status":          "",
        "Level":           "",
        "Subjcode":        "",
        "CRN":             "",
        "CourseNumber":    "",
        "CourseTitle":     "",
        "CreditHours":     "",
        "courseattribute": "",
        "BeginTime":       "",
        "Instructor":      "",
        "sortby":          "course",
        "Button1":         "Search",
    }
    resp = await client.post(RESULT_URL, data=form_data, headers=HEADERS)
    return resp.text, resp.status_code

def parse_courses(html):
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text().lower()

    if "no classes" in page_text or "no section" in page_text:
        return [], []

    tables = soup.find_all("table")
    courses = []
    headers = []
    seen_crns = set()  # deduplicate by CRN

    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        header_cells = rows[0].find_all(["th", "td"])
        row_headers = [c.get_text(strip=True) for c in header_cells]
        header_text = " ".join(row_headers).lower()
        if not any(k in header_text for k in [
            "crn", "subj", "numb", "title", "credit", "cap", "instructor", "days", "sec"
        ]):
            continue

        # Find CRN column index for deduplication
        crn_idx = next((i for i, h in enumerate(row_headers)
                        if "crn" in h.lower()), None)

        if not headers:
            headers = row_headers

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            values = [c.get_text(separator=" ", strip=True) for c in cells]
            if not any(v.strip() for v in values):
                continue

            # Skip rows where CRN is not a valid number (header/title rows)
            if crn_idx is not None and crn_idx < len(values):
                crn_val = values[crn_idx].strip()
                if crn_val and not crn_val.isdigit():
                    continue

            # Deduplicate by CRN value
            crn = values[crn_idx].strip() if crn_idx is not None and crn_idx < len(values) else None
            if crn and crn in seen_crns:
                continue
            if crn:
                seen_crns.add(crn)

            courses.append(values)

    return headers, courses

def save_term_file(term_code, term_label, headers, courses):
    term_display = term_label.replace("_", " ")
    md_path = os.path.join(OUTPUT_DIR, f"courses_{term_label}.md")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# FGCU Engineering Course Schedule — {term_display}\n\n")
        f.write(f"**Term Code:** {term_code}\n")
        f.write(f"**College:** Engineering\n")
        f.write(f"**Total Courses:** {len(courses)}\n\n")
        f.write("---\n\n")

        if headers:
            f.write("| " + " | ".join(headers) + " |\n")
            f.write("|" + "|".join(["---"] * len(headers)) + "|\n")
            for row in courses:
                while len(row) < len(headers):
                    row.append("")
                row = [c.replace("|", "/") for c in row[:len(headers)]]
                f.write("| " + " | ".join(row) + " |\n")

    return md_path

async def scrape_all():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Scraping {len(TERMS)} semesters — College: Engineering (all depts)")
    print(f"Output: {OUTPUT_DIR}\n")

    total_files   = 0
    total_courses = 0
    empty_terms   = []

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for i, (term_code, term_label) in enumerate(TERMS):
            term_display = term_label.replace("_", " ")
            print(f"[{i+1}/{len(TERMS)}] {term_display} ({term_code})", end=" ... ")

            html, status = await fetch_all_engineering(client, term_code)
            headers, courses = parse_courses(html)

            if courses:
                md_path = save_term_file(term_code, term_label, headers, courses)
                print(f"{len(courses)} courses -> courses_{term_label}.md")
                total_files   += 1
                total_courses += len(courses)
            else:
                print(f"no courses found (HTTP {status})")
                empty_terms.append(term_display)

            await asyncio.sleep(0.5)

    print(f"\n{'='*50}")
    print(f"Done!")
    print(f"  Files saved:   {total_files}")
    print(f"  Total courses: {total_courses}")
    if empty_terms:
        print(f"\nNo data for:")
        for t in empty_terms:
            print(f"  {t}")

asyncio.run(scrape_all())