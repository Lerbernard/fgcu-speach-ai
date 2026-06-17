import asyncio
import os
import re
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from bs4 import BeautifulSoup

FACULTY_PAGE  = "https://www.fgcu.edu/eng/facultystaff/"
DIRECTORY_BASE = "https://www.fgcu.edu/directory/"
OUTPUT_DIR    = "..\\data\\pages\\04_engineering_faculty"

JS_EXPAND_ALL = """
(async () => {
    // Click all collapsed accordion sections
    const selectors = [
        'button[aria-expanded="false"]',
        '.accordion-toggle',
        '[data-toggle="collapse"]',
        'dt button',
        'summary',
    ];
    for (const selector of selectors) {
        for (const btn of document.querySelectorAll(selector)) {
            try { btn.click(); } catch(e) {}
        }
    }
    // Click any + buttons
    for (const btn of document.querySelectorAll('button, div[role="button"]')) {
        if (btn.textContent.trim() === '+') {
            try { btn.click(); } catch(e) {}
        }
    }
    await new Promise(r => setTimeout(r, 2000));
})();
"""

async def get_faculty_links(crawler):
    """Scrape the faculty staff page and extract all directory profile links."""
    config = CrawlerRunConfig(page_timeout=25000)
    result = await crawler.arun(url=FACULTY_PAGE, config=config)

    if not result.success:
        print(f"Failed to load faculty page: {result.error_message}")
        return []

    soup = BeautifulSoup(result.html, "html.parser")
    links = soup.find_all("a", href=True)

    faculty = []
    seen = set()
    for link in links:
        href = link["href"]
        name = link.get_text(strip=True)
        # Match directory profile links
        if "/directory/" in href and "?" in href and name:
            # Normalize URL
            if href.startswith("/"):
                href = "https://www.fgcu.edu" + href
            # Remove anchor fragments for the base URL
            base_url = href.split("#")[0]
            if base_url not in seen and len(name) > 3:
                seen.add(base_url)
                faculty.append({"name": name, "url": base_url})

    return faculty

async def scrape_profile(crawler, faculty_member):
    """Scrape a single faculty profile with all sections expanded."""
    name = faculty_member["name"]
    url  = faculty_member["url"]

    config = CrawlerRunConfig(
        js_code=JS_EXPAND_ALL,
        wait_for="body",
        delay_before_return_html=2.5,
        markdown_generator=DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(threshold=0.3)
        ),
        word_count_threshold=10,
        page_timeout=25000,
    )

    result = await crawler.arun(url=url, config=config)

    if not result.success:
        return None, []

    # Extract external links (Google Scholar, RateMyProfessors, ResearchGate etc.)
    soup = BeautifulSoup(result.html, "html.parser")
    external_links = []
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if any(site in href for site in [
            "scholar.google", "ratemyprofessors", "researchgate",
            "linkedin.com", "orcid.org", "academia.edu", "pubmed"
        ]):
            external_links.append(href)

    return result.markdown.fit_markdown, external_links

def name_to_filename(name):
    clean = re.sub(r"[^\w\s]", "", name).strip()
    clean = re.sub(r"\s+", "_", clean).lower()
    return clean[:60] + ".md"

async def scrape_all_faculty():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    browser_config = BrowserConfig(headless=True, verbose=False)

    async with AsyncWebCrawler(config=browser_config) as crawler:
        print("Step 1 — Finding all faculty members...")
        faculty_list = await get_faculty_links(crawler)

        if not faculty_list:
            print("No faculty found. Check that the faculty page is accessible.")
            return

        print(f"Found {len(faculty_list)} faculty members\n")

        saved = 0
        failed = []

        for i, person in enumerate(faculty_list):
            name = person["name"]
            url  = person["url"]
            print(f"[{i+1}/{len(faculty_list)}] {name}")
            print(f"  URL: {url}")

            content, ext_links = await scrape_profile(crawler, person)

            if content and content.strip():
                filename = name_to_filename(name)
                filepath = os.path.join(OUTPUT_DIR, filename)

                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(f"# {name}\n")
                    f.write(f"Profile: {url}\n")
                    if ext_links:
                        f.write("\n## External Links\n")
                        for link in ext_links:
                            f.write(f"- {link}\n")
                    f.write("\n---\n\n")
                    f.write(content)

                print(f"  Saved: {filename}")
                if ext_links:
                    print(f"  Found {len(ext_links)} external links: {', '.join(ext_links)}")
                saved += 1
            else:
                print(f"  Skipped (empty)")
                failed.append(person)

            await asyncio.sleep(0.8)

        print(f"\n{'='*50}")
        print(f"Done!")
        print(f"  Saved:  {saved} faculty profiles")
        print(f"  Failed: {len(failed)}")

        if failed:
            print("\nFailed profiles:")
            for p in failed:
                print(f"  {p['name']} — {p['url']}")

asyncio.run(scrape_all_faculty())