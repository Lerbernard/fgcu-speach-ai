import asyncio
import os
import re
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

BASE_DIR = "..\\data\\pages\\03_engineering_programs"

PROGRAMS = {
    "graduate": [
        ("civil_engineering_ms",    "https://catalog.fgcu.edu/programs/ms-civengr/"),
        ("computer_science_ms",     "https://catalog.fgcu.edu/programs/computer-science-ms/"),
    ],
    "minors": [
        ("bioengineering_minor",           "https://www.fgcu.edu/eng/bioengineering-civilengineering-environmentalengineering/bioengineering-minor"),
        ("computer_science_minor",         "https://www.fgcu.edu/eng/computing-software-engineering/computerscience-minor"),
        ("environmental_engineering_minor","https://www.fgcu.edu/eng/bioengineering-civilengineering-environmentalengineering/enve-minor"),
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
    window.scrollTo(0, document.body.scrollHeight);
    await new Promise(r => setTimeout(r, 2500));
})();
"""

YEAR_MAP = {"1": "Freshman", "2": "Sophomore", "3": "Junior", "4": "Senior", "5": "Fifth Year"}

FOOTER_MARKERS = [
    "Experience FGCU", "10501 FGCU Blvd",
    "Florida Gulf Coast University. All Rights Reserved",
    "© Florida Gulf Coast University", "[Privacy Statement]",
    "[Contact Us](https://www.fgcu.edu/about/contactus",
    "Colleges\n  * [College",
]

NAV_SKIP = [
    "fgcu-lettermark", "fgcu-ribbon", "Menu Toggle",
    "facebook.svg", "instagram.svg", "youtube.svg",
    "linkedin.svg", "fgcu360", "x.svg",
    "Skip to main content", "Skip to the content",
    "FGCU Privacy Policy", "This website stores cookies",
    "Download Page (PDF)", "Close this window", "Print Options",
]

def clean_content(text, prog_name):
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

        # Add Freshman/Sophomore etc. labels to year headings
        year_match = re.match(r'^(Fall|Spring|Summer)\s+Year\s+(\d)(.*)', line.strip())
        if year_match:
            season   = year_match.group(1)
            year_num = year_match.group(2)
            rest     = year_match.group(3)
            label    = YEAR_MAP.get(year_num, "")
            if label and label.lower() not in line.lower():
                line = f"{season} Year {year_num} — {label}{rest}"

        cleaned.append(line)

    content = "\n".join(cleaned)

    # Remove markdown links but keep text
    content = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', content)
    # Remove bare URLs
    content = re.sub(r'https?://\S+', '', content)
    # Remove image tags
    content = re.sub(r'!\[.*?\]\(.*?\)', '', content)
    # Remove print/download artifacts
    content = re.sub(r'## Print Options.*$', '', content, flags=re.DOTALL)
    # Remove footnote numbers
    content = re.sub(r'\s*\*,?\s*\d+', '', content)
    # Remove XXX XXXX placeholders
    content = re.sub(r'XXX XXXX\s*', '', content)
    # Remove table separators
    content = re.sub(r'^\|[-| :]+\|$', '', content, flags=re.MULTILINE)
    # Remove empty table cells (rows of just pipes)
    content = re.sub(r'^\|\s*\|\s*$', '', content, flags=re.MULTILINE)
    # Clean excess blank lines
    content = re.sub(r'\n{3,}', '\n\n', content)

    return content.strip()

async def scrape_all():
    # Create folders
    for folder in ["graduate", "minors"]:
        os.makedirs(os.path.join(BASE_DIR, folder), exist_ok=True)
    print(f"Created folders: graduate, minors\n")

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
        for folder, entries in PROGRAMS.items():
            print(f"\n{'='*50}")
            print(f"Folder: {folder}")
            print('='*50)

            for prog_name, url in entries:
                print(f"\n  [{prog_name}] {url}")
                try:
                    result = await crawler.arun(url=url, config=config)
                    if result.success:
                        cleaned = clean_content(result.markdown.fit_markdown, prog_name)
                        if len(cleaned) < 200:
                            cleaned = clean_content(result.markdown.raw_markdown, prog_name)

                        filename = f"programs_{prog_name}.md"
                        filepath = os.path.join(BASE_DIR, folder, filename)
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.write(f"# Source: {url}\n\n")
                            f.write(cleaned)

                        print(f"  Saved: {folder}\\{filename} ({len(cleaned):,} chars)")
                        saved += 1
                    else:
                        print(f"  Failed: {result.error_message}")
                        failed.append((prog_name, url))
                except Exception as e:
                    print(f"  Error: {e}")
                    failed.append((prog_name, url))

                await asyncio.sleep(1.5)

    print(f"\n{'='*50}")
    print(f"Done! Saved {saved} pages")
    if failed:
        print(f"\nFailed:")
        for name, url in failed:
            print(f"  {name}: {url}")

asyncio.run(scrape_all())