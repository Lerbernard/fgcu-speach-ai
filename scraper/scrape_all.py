import asyncio
import os
import re
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

BASE_DIR = "..\\data\\pages"

JS_EXPAND_ALL = """
(async () => {
    const selectors = [
        'button[aria-expanded="false"]',
        '.accordion-toggle',
        '.collapse-toggle',
        '[data-toggle="collapse"]',
        'button.toggle',
        '.expand-btn',
        'a[data-toggle]',
        '.panel-heading a',
        'dt button',
        'summary',
    ];
    for (const selector of selectors) {
        const buttons = document.querySelectorAll(selector);
        for (const btn of buttons) {
            try { btn.click(); } catch(e) {}
        }
    }
    const allButtons = document.querySelectorAll('button, a, div[role="button"]');
    for (const btn of allButtons) {
        const text = btn.textContent.trim();
        const label = btn.getAttribute('aria-label') || '';
        if (text === '+' || label.toLowerCase().includes('expand') ||
            label.toLowerCase().includes('show')) {
            try { btn.click(); } catch(e) {}
        }
    }
    await new Promise(r => setTimeout(r, 1500));
})();
"""

URLS = [
    # --- ENGINEERING COLLEGE ---
    ("01_engineering_main",         "https://www.fgcu.edu/eng/"),
    ("01_engineering_main",         "https://www.fgcu.edu/eng/about/"),
    ("01_engineering_main",         "https://www.fgcu.edu/eng/accreditation"),
    ("01_engineering_main",         "https://www.fgcu.edu/eng/advising/"),
    ("01_engineering_main",         "https://www.fgcu.edu/eng/technology_recommendations"),
    ("01_engineering_main",         "https://www.fgcu.edu/eng/wceawards"),
    ("01_engineering_main",         "https://www.fgcu.edu/eng/wce-news"),
    ("01_engineering_main",         "https://www.fgcu.edu/eng/wce-news/alexis-figueroa-baltazar-spotlight"),
    ("01_engineering_main",         "https://www.fgcu.edu/eng/wce-news/first-place-wins"),
    ("01_engineering_main",         "https://www.fgcu.edu/eng/wce-news/juan-cortes-spotlight"),

    # — ENGINEERING DEPARTMENTS ---
    ("02_engineering_departments",  "https://www.fgcu.edu/eng/bioengineering-civilengineering-environmentalengineering/"),
    ("02_engineering_departments",  "https://www.fgcu.edu/eng/computing-software-engineering/"),
    ("02_engineering_departments",  "https://www.fgcu.edu/eng/constructionmanagement/"),
    ("02_engineering_departments",  "https://www.fgcu.edu/eng/dendritic-institute/"),

    # --- ENGINEERING PROGRAMS ---
    # Note: /programs/, /undergraduate/, /graduate/ return 404 — using working alternatives
    ("03_engineering_programs",     "https://www.fgcu.edu/eng/bioengineering-civilengineering-environmentalengineering/"),
    ("03_engineering_programs",     "https://www.fgcu.edu/eng/computing-software-engineering/"),
    ("03_engineering_programs",     "https://www.fgcu.edu/eng/constructionmanagement/"),
    ("03_engineering_programs",     "https://www.fgcu.edu/admissionsandaid/graduateadmissions/degreesandprograms"),

    # — ENGINEERING FACULTY & STAFF ---
    ("04_engineering_faculty",      "https://www.fgcu.edu/eng/facultystaff/"),

    # --- ENGINEERING RESEARCH ---
    ("05_engineering_research",     "https://www.fgcu.edu/eng/research/"),

    # --- ENGINEERING STUDENT LIFE —
    ("06_engineering_student_life", "https://www.fgcu.edu/eng/student-involvement/"),
    ("06_engineering_student_life", "https://www.fgcu.edu/eng/internships/community-employer-involvement"),

    # — COURSES & CATALOG ---
    ("07_courses_catalog",          "https://catalog.fgcu.edu/"),
    ("07_courses_catalog",          "https://fgcu-web02.fgcu.edu/CourseDescriptions/"),
    ("07_courses_catalog",          "https://www.fgcu.edu/academics/academiccalendar/"),
    ("07_courses_catalog",          "https://www.fgcu.edu/academics/programguide/"),
    ("07_courses_catalog",          "https://www.fgcu.edu/degree/"),
    ("07_courses_catalog",          "https://www.fgcu.edu/recordsandregistration/"),

    # --- ACADEMICS ---
    ("08_academics",                "https://www.fgcu.edu/academics/"),
    ("08_academics",                "https://www.fgcu.edu/academics/advising/"),
    ("08_academics",                "https://www.fgcu.edu/academics/caa/"),
    ("08_academics",                "https://www.fgcu.edu/academics/colleges/"),
    ("08_academics",                "https://www.fgcu.edu/academics/global-engagement-office/"),
    ("08_academics",                "https://www.fgcu.edu/academics/innovate/"),
    ("08_academics",                "https://www.fgcu.edu/academics/internships/"),
    ("08_academics",                "https://www.fgcu.edu/academics/research/"),
    ("08_academics",                "https://www.fgcu.edu/graduatestudies/"),
    ("08_academics",                "https://www.fgcu.edu/sisr/"),

    # --- ADMISSIONS ---
    ("09_admissions",               "https://www.fgcu.edu/admissionsandaid/"),
    ("09_admissions",               "https://www.fgcu.edu/admissionsandaid/undergraduateadmissions/"),
    ("09_admissions",               "https://www.fgcu.edu/admissionsandaid/undergraduateadmissions/freshmanadmissions"),
    ("09_admissions",               "https://www.fgcu.edu/admissionsandaid/undergraduateadmissions/transferadmissions"),
    ("09_admissions",               "https://www.fgcu.edu/admissionsandaid/undergraduateadmissions/admittedstudents"),
    ("09_admissions",               "https://www.fgcu.edu/admissionsandaid/undergraduateadmissions/internationalstudents/"),
    ("09_admissions",               "https://www.fgcu.edu/admissionsandaid/undergraduateadmissions/nondegreeadmissions"),
    ("09_admissions",               "https://www.fgcu.edu/admissionsandaid/undergraduateadmissions/highschoolcounselors"),
    ("09_admissions",               "https://www.fgcu.edu/admissionsandaid/graduateadmissions/"),
    ("09_admissions",               "https://www.fgcu.edu/admissionsandaid/graduateadmissions/degreesandprograms"),
    ("09_admissions",               "https://www.fgcu.edu/enrollmentservices/"),

    # --- FINANCIAL AID ---
    ("10_financial_aid",            "https://www.fgcu.edu/admissionsandaid/financialaid/"),
    ("10_financial_aid",            "https://www.fgcu.edu/admissionsandaid/financialaid/undergraduate/formsandresources/consumerinformation"),

    # --- STUDENT LIFE ---
    ("11_student_life",             "https://www.fgcu.edu/studentlife/"),
    ("11_student_life",             "https://www.fgcu.edu/studentlife/care/"),
    ("11_student_life",             "https://www.fgcu.edu/studentlife/dean_of_students/"),
    ("11_student_life",             "https://www.fgcu.edu/studentlife/dean_of_students/bni"),
    ("11_student_life",             "https://www.fgcu.edu/studentlife/housing/"),
    ("11_student_life",             "https://www.fgcu.edu/studentlife/studenthealth/"),
    ("11_student_life",             "https://www.fgcu.edu/studentlife/studentorgs/"),
    ("11_student_life",             "https://www.fgcu.edu/firstyearexperience/"),
    ("11_student_life",             "https://www.fgcu.edu/counseling-and-psychological-services/"),
    ("11_student_life",             "https://www.fgcu.edu/adaptive/"),
    ("11_student_life",             "https://www.fgcu.edu/trio/"),
    ("11_student_life",             "https://www.fgcu.edu/retention"),
    ("11_student_life",             "https://www.fgcu.edu/university-recreation-and-wellness/"),
    ("11_student_life",             "https://www.fgcu.edu/sg/"),

    # --- COLLEGES & SCHOOLS ---
    ("12_colleges_schools",         "https://www.fgcu.edu/cas/"),
    ("12_colleges_schools",         "https://www.fgcu.edu/cas/bsma/"),
    ("12_colleges_schools",         "https://www.fgcu.edu/cas/centers/whitaker/"),
    ("12_colleges_schools",         "https://www.fgcu.edu/cob/"),
    ("12_colleges_schools",         "https://www.fgcu.edu/cob/srhm/"),
    ("12_colleges_schools",         "https://www.fgcu.edu/coe/"),
    ("12_colleges_schools",         "https://www.fgcu.edu/mariebcollege/"),
    ("12_colleges_schools",         "https://www.fgcu.edu/mariebcollege/nursing/"),
    ("12_colleges_schools",         "https://www.fgcu.edu/school-of-entrepreneurship/"),
    ("12_colleges_schools",         "https://www.fgcu.edu/thewaterschool/"),

    # --- ABOUT FGCU ---
    ("13_about_fgcu",               "https://www.fgcu.edu/"),
    ("13_about_fgcu",               "https://www.fgcu.edu/about/"),
    ("13_about_fgcu",               "https://www.fgcu.edu/about/contactus"),
    ("13_about_fgcu",               "https://www.fgcu.edu/community/"),
    ("13_about_fgcu",               "https://www.fgcu.edu/communityengagement/"),
    ("13_about_fgcu",               "https://www.fgcu.edu/advancement/"),
    ("13_about_fgcu",               "https://www.fgcu.edu/worldaffairslectures/"),

    # --- RESOURCES & SERVICES ---
    ("14_resources_services",       "https://www.fgcu.edu/jobs/"),
    ("14_resources_services",       "https://www.fgcu.edu/its/"),
    ("14_resources_services",       "https://www.fgcu.edu/militaryandveteransuccess/"),
    ("14_resources_services",       "https://www.fgcu.edu/upd/"),
    ("14_resources_services",       "https://www.fgcu.edu/ehs/sustainability/"),
    ("14_resources_services",       "https://www.fgcu.edu/testing/"),

    # --- POLICIES & LEGAL ---
    ("15_policies_legal",           "https://www.fgcu.edu/generalcounsel/resources"),
    ("15_policies_legal",           "https://www.fgcu.edu/admissionsandaid/statement-of-free-expression"),
    ("15_policies_legal",           "https://www.fgcu.edu/stateauthorization/"),
    ("15_policies_legal",           "https://www.fgcu.edu/institutional-ethics-and-compliance/ethics/"),
    ("15_policies_legal",           "https://www.fgcu.edu/governmentrelations/"),
]

def url_to_filename(url):
    name = re.sub(r"https?://", "", url)
    name = re.sub(r"[^\w\-]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name[:80] + ".md"

async def scrape_all():
    categories = set(folder for folder, _ in URLS)
    for cat in categories:
        os.makedirs(os.path.join(BASE_DIR, cat), exist_ok=True)
    print(f"Created {len(categories)} category folders\n")

    config = CrawlerRunConfig(
        js_code=JS_EXPAND_ALL,
        wait_for="body",
        delay_before_return_html=2.0,
        markdown_generator=DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(threshold=0.45)
        ),
        exclude_external_links=True,
        word_count_threshold=30,
        page_timeout=25000,
    )

    saved = 0
    failed = []
    skipped = 0

    async with AsyncWebCrawler() as crawler:
        for i, (folder, url) in enumerate(URLS):
            print(f"[{i+1}/{len(URLS)}] [{folder}] {url}")
            try:
                result = await crawler.arun(url=url, config=config)
                if result.success and result.markdown.fit_markdown.strip():
                    filename = url_to_filename(url)
                    filepath = os.path.join(BASE_DIR, folder, filename)
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(f"# Source: {url}\n\n")
                        f.write(result.markdown.fit_markdown)
                    print(f"  Saved: {folder}\\{filename}")
                    saved += 1
                else:
                    print(f"  Skipped (empty): {url}")
                    skipped += 1
            except Exception as e:
                print(f"  Error: {e}")
                failed.append((folder, url))

            await asyncio.sleep(0.5)

    print(f"\n{'='*50}")
    print(f"Done!")
    print(f"  Saved:   {saved}")
    print(f"  Skipped: {skipped}")
    print(f"  Failed:  {len(failed)}")

    if failed:
        print("\nFailed URLs:")
        for folder, u in failed:
            print(f"  [{folder}] {u}")
        with open("..\\data\\failed_urls.txt", "w") as f:
            for folder, u in failed:
                f.write(f"{folder} | {u}\n")
        print("Saved to data\\failed_urls.txt")

asyncio.run(scrape_all())