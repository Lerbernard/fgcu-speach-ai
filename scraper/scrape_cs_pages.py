import asyncio
import os
import re
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

OUTPUT_DIR = "..\\data\\pages\\02_engineering_departments\\computing_software_engineering"

URLS = [
    "https://www.fgcu.edu/eng/computing-software-engineering/",
    "https://www.fgcu.edu/eng/computing-software-engineering/softwareengineering-bs",
    "https://www.fgcu.edu/eng/computing-software-engineering/computerscience-bs",
    "https://www.fgcu.edu/eng/computing-software-engineering/computerscience-minor",
    "https://www.fgcu.edu/eng/graduateprograms/computer-science-ms/",
    "https://www.fgcu.edu/eng/computing-software-engineering/eaglecybernest/",
    "https://www.fgcu.edu/eng/dendritic-institute/",
]

JS_EXPAND_ALL = """
(async () => {
    // Click all collapsed sections
    const selectors = [
        'button[aria-expanded="false"]',
        '.accordion-toggle',
        '.accordion-button.collapsed',
        '[data-toggle="collapse"]',
        '[data-bs-toggle="collapse"]',
        'details:not([open]) > summary',
        'dt button',
        '.panel-heading a',
        '.collapsible',
        '.toggle-btn',
    ];
    for (const selector of selectors) {
        const els = document.querySelectorAll(selector);
        for (const el of els) {
            try { el.click(); } catch(e) {}
        }
    }
    // Click any + or expand buttons
    for (const btn of document.querySelectorAll('button, [role="button"], a')) {
        const text = btn.textContent.trim();
        const label = (btn.getAttribute('aria-label') || '').toLowerCase();
        if (text === '+' || text === 'Expand' ||
            label.includes('expand') || label.includes('show more')) {
            try { btn.click(); } catch(e) {}
        }
    }
    // Open all <details> elements
    for (const d of document.querySelectorAll('details')) {
        d.setAttribute('open', '');
    }
    await new Promise(r => setTimeout(r, 2000));
})();
"""

def url_to_filename(url):
    name = re.sub(r"https?://www\.fgcu\.edu/", "", url)
    name = re.sub(r"[^\w\-]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name[:80] + ".md"

def clean_content(text):
    """Remove repeated nav/header/footer boilerplate."""
    lines = text.split("\n")
    cleaned = []
    content_started = False

    skip_patterns = [
        "Skip to main content",
        "Skip to the content",
        "FGCU Privacy Policy",
        "This website stores cookies",
        "Accept\nClose",
        "fgcu-lettermark",
        "fgcu-ribbon",
        "Menu Toggle",
        "florida gulf coast university. all rights reserved",
        "privacy statement",
        "statement of free expression",
        "webmaster",
        "accessibility",
        "eo/vet/title ix",
    ]

    footer_markers = [
        "Experience FGCU",
        "10501 FGCU Blvd",
        "© Florida Gulf Coast University",
        "Florida Gulf Coast University. All Rights Reserved",
        "Contact Us](https://www.fgcu.edu/about/contactus",
    ]

    for line in lines:
        line_lower = line.lower().strip()

        # Detect content start — first real heading after nav
        if not content_started:
            if re.match(r"^#{1,3} ", line) and "fgcu" not in line_lower[:20]:
                content_started = True
            else:
                continue

        # Stop at footer
        if any(marker.lower() in line_lower for marker in footer_markers):
            break

        # Skip nav/boilerplate lines
        if any(p.lower() in line_lower for p in skip_patterns):
            continue

        # Skip pure bullet nav links
        if re.match(r"^\s{2,}\*\s+\[.+\]\(https?://.+\)\s*$", line):
            continue

        # Skip social media icon lines
        if any(x in line for x in ["facebook.svg", "instagram.svg", "youtube.svg",
                                     "linkedin.svg", "fgcu360", "x.svg"]):
            continue

        cleaned.append(line)

    content = "\n".join(cleaned)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()

async def scrape_all():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    browser_config = BrowserConfig(headless=True, verbose=False)
    config = CrawlerRunConfig(
        js_code=JS_EXPAND_ALL,
        wait_for="body",
        delay_before_return_html=2.5,
        markdown_generator=DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(threshold=0.3)
        ),
        word_count_threshold=20,
        page_timeout=30000,
    )

    saved = 0
    failed = []

    async with AsyncWebCrawler(config=browser_config) as crawler:
        for i, url in enumerate(URLS):
            print(f"\n[{i+1}/{len(URLS)}] {url}")
            try:
                result = await crawler.arun(url=url, config=config)
                if result.success:
                    raw = result.markdown.fit_markdown
                    cleaned = clean_content(raw)

                    if len(cleaned) < 200:
                        print(f"  Warning: very little content ({len(cleaned)} chars)")
                        print(f"  Using raw markdown instead")
                        cleaned = raw

                    filename = url_to_filename(url)
                    filepath = os.path.join(OUTPUT_DIR, filename)
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(f"# Source: {url}\n\n")
                        f.write(cleaned)

                    print(f"  Saved: {filename}")
                    print(f"  Content: {len(cleaned)} chars")
                    saved += 1
                else:
                    print(f"  Failed: {result.error_message}")
                    failed.append(url)
            except Exception as e:
                print(f"  Error: {e}")
                failed.append(url)

            await asyncio.sleep(1)

    print(f"\n{'='*50}")
    print(f"Done! Saved {saved}/{len(URLS)} pages")
    if failed:
        print("\nFailed:")
        for u in failed:
            print(f"  {u}")

asyncio.run(scrape_all())