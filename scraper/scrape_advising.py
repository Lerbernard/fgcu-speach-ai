import asyncio
import os
import re
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

OUTPUT_DIR = "..\\data\\pages\\03_engineering_programs\\advising"

URLS = [
    "https://www.fgcu.edu/eng/advising/",
    "https://www.fgcu.edu/eng/advising/transientstudentinstructions",
    "https://www.fgcu.edu/eng/advising/advisingsyllabus",
    "https://www.fgcu.edu/academics/advising/holdskey",
    "https://www.fgcu.edu/studentcomplaints/",
    "https://www.fgcu.edu/academics/advising/faq",
]

JS_EXPAND_ALL = """
(async () => {
    const selectors = [
        'button[aria-expanded="false"]',
        '.accordion-button.collapsed',
        '.accordion-toggle',
        '[data-toggle="collapse"]',
        '[data-bs-toggle="collapse"]',
        'dt button',
        '.panel-heading a',
        '.collapsible',
    ];
    for (const selector of selectors) {
        for (const el of document.querySelectorAll(selector)) {
            try { el.click(); } catch(e) {}
        }
    }
    for (const d of document.querySelectorAll('details')) {
        d.setAttribute('open', '');
    }
    for (const btn of document.querySelectorAll('button, [role="button"]')) {
        const text = btn.textContent.trim();
        if (text === '+' || text === 'Show More' || text === 'Expand All') {
            try { btn.click(); } catch(e) {}
        }
    }
    window.scrollTo(0, document.body.scrollHeight);
    await new Promise(r => setTimeout(r, 2000));
})();
"""

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
    name = re.sub(r"https?://[^/]+/", "", url)
    name = re.sub(r"[^\w\-]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return (name[:70] or "index") + ".md"

async def scrape_all():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Scraping {len(URLS)} advising pages\n")

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
        for i, url in enumerate(URLS):
            print(f"[{i+1}/{len(URLS)}] {url}")
            try:
                result = await crawler.arun(url=url, config=config)
                if result.success:
                    cleaned = clean_content(result.markdown.fit_markdown)
                    if len(cleaned) < 300:
                        cleaned = result.markdown.raw_markdown

                    filename = url_to_filename(url)
                    filepath = os.path.join(OUTPUT_DIR, filename)
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(f"# Source: {url}\n\n")
                        f.write(cleaned)

                    print(f"  Saved: {filename} ({len(cleaned):,} chars)")
                    saved += 1
                else:
                    print(f"  Failed: {result.error_message}")
                    failed.append(url)
            except Exception as e:
                print(f"  Error: {e}")
                failed.append(url)

            await asyncio.sleep(1.5)

    print(f"\n{'='*50}")
    print(f"Done! Saved {saved}/{len(URLS)} pages to {OUTPUT_DIR}")
    if failed:
        print("\nFailed:")
        for u in failed:
            print(f"  {u}")

asyncio.run(scrape_all())