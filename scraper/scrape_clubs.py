import asyncio
import os
import re
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

BASE_DIR = "..\\data\\pages\\06_engineering_student_life\\clubs"

CLUBS = {
    "computer_science_software_engineering_club": [
        "https://getinvolved.fgcu.edu/organization/cssec",
        "https://getinvolved.fgcu.edu/organization/cssec/events?showpastevents=true",
        "https://getinvolved.fgcu.edu/organization/cssec/news",
    ],
    "society_of_women_engineers": [
        "https://getinvolved.fgcu.edu/organization/swe",
    ],
    "women_in_stem": [
        "https://getinvolved.fgcu.edu/organization/womeninstem",
    ],
    "american_society_of_civil_engineers": [
        "https://getinvolved.fgcu.edu/organization/asce",
        "https://getinvolved.fgcu.edu/organization/asce/news",
    ],
    "biomedical_engineering_society": [
        "https://getinvolved.fgcu.edu/organization/bmes",
    ],
    "florida_engineering_society": [
        "https://getinvolved.fgcu.edu/organization/fes",
    ],
    "ieee_student_branch": [
        "https://getinvolved.fgcu.edu/organization/ieee",
    ],
    "national_society_of_black_engineers": [
        "https://getinvolved.fgcu.edu/organization/nsbe",
    ],
}

JS_EXPAND_ALL = """
(async () => {
    const selectors = [
        'button[aria-expanded="false"]',
        '.accordion-button.collapsed',
        '[data-toggle="collapse"]',
        '[data-bs-toggle="collapse"]',
        'details:not([open]) > summary',
        'dt button',
    ];
    for (const selector of selectors) {
        for (const el of document.querySelectorAll(selector)) {
            try { el.click(); } catch(e) {}
        }
    }
    for (const d of document.querySelectorAll('details')) {
        d.setAttribute('open', '');
    }
    // Scroll to load lazy content
    window.scrollTo(0, document.body.scrollHeight);
    await new Promise(r => setTimeout(r, 2500));
})();
"""

FOOTER_MARKERS = [
    "Florida Gulf Coast University. All Rights Reserved",
    "© Florida Gulf Coast University",
    "[Privacy Statement]",
    "10501 FGCU Blvd",
    "Experience FGCU",
]

NAV_SKIP = [
    "fgcu-lettermark", "fgcu-ribbon", "Menu Toggle",
    "facebook.svg", "instagram.svg", "youtube.svg",
    "linkedin.svg", "fgcu360", "x.svg",
    "Skip to main content", "Skip to the content",
    "FGCU Privacy Policy", "This website stores cookies",
]

def clean_content(text):
    lines = text.split("\n")
    cleaned = []
    content_started = False
    for line in lines:
        line_lower = line.lower().strip()
        if not content_started:
            if re.match(r"^#{1,3} ", line):
                content_started = True
            else:
                continue
        if any(m.lower() in line_lower for m in FOOTER_MARKERS):
            break
        if any(p in line for p in NAV_SKIP):
            continue
        if re.match(r"^\s{4,}\*\s+\[.+\]\(https?://.+\)\s*$", line):
            continue
        cleaned.append(line)
    content = "\n".join(cleaned)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()

def url_to_filename(url):
    name = re.sub(r"https?://[^/]+/organization/", "", url)
    name = re.sub(r"[^\w\-]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return (name[:70] or "index") + ".md"

async def scrape_all():
    for club in CLUBS:
        os.makedirs(os.path.join(BASE_DIR, club), exist_ok=True)
    print(f"Created {len(CLUBS)} club folders\n")

    browser_config = BrowserConfig(headless=True, verbose=False)
    config = CrawlerRunConfig(
        js_code=JS_EXPAND_ALL,
        wait_for="body",
        delay_before_return_html=3.0,
        markdown_generator=DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(threshold=0.25)
        ),
        word_count_threshold=15,
        page_timeout=35000,
    )

    saved = 0
    failed = []

    async with AsyncWebCrawler(config=browser_config) as crawler:
        for club_folder, urls in CLUBS.items():
            club_name = club_folder.replace("_", " ").title()
            print(f"\n{'='*50}")
            print(f"Club: {club_name}")

            for url in urls:
                page_type = url.split("/")[-1].split("?")[0] or "main"
                print(f"\n  [{page_type}] {url}")
                try:
                    result = await crawler.arun(url=url, config=config)
                    if result.success:
                        cleaned = clean_content(result.markdown.fit_markdown)
                        if len(cleaned) < 200:
                            cleaned = result.markdown.raw_markdown

                        filename = url_to_filename(url)
                        filepath = os.path.join(BASE_DIR, club_folder, filename)
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write(f"# Source: {url}\n\n")
                            f.write(cleaned)

                        print(f"  Saved: {club_folder}\\{filename} ({len(cleaned):,} chars)")
                        saved += 1
                    else:
                        print(f"  Failed: {result.error_message}")
                        failed.append(url)
                except Exception as e:
                    print(f"  Error: {e}")
                    failed.append(url)

                await asyncio.sleep(1.5)

    print(f"\n{'='*50}")
    print(f"Done! Saved {saved} pages across {len(CLUBS)} clubs")
    if failed:
        print(f"\nFailed ({len(failed)}):")
        for u in failed:
            print(f"  {u}")

asyncio.run(scrape_all())