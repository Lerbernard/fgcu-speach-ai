import asyncio
import os
import re
import shutil
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

OUTPUT_DIR = "..\\data\\pages\\03_engineering_programs\\computer_science_bs"

URLS = [
    "https://www.fgcu.edu/eng/computing-software-engineering/computerscience-bs",
    "https://catalog.fgcu.edu/programs/computer-science-bs/",
]

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
    await new Promise(r => setTimeout(r, 3000));
})();
"""

FOOTER_MARKERS = [
    "Experience FGCU", "10501 FGCU Blvd",
    "Florida Gulf Coast University. All Rights Reserved",
    "© Florida Gulf Coast University", "[Privacy Statement]",
    "Download Page (PDF)", "Close this window", "Print Options",
]

NAV_SKIP = [
    "fgcu-lettermark", "fgcu-ribbon", "Menu Toggle",
    "facebook.svg", "instagram.svg", "youtube.svg",
    "linkedin.svg", "Skip to main content", "Skip to the content",
    "FGCU Privacy Policy", "This website stores cookies",
]

CONCENTRATIONS = [
    "AI and Data Science",
    "Cybersecurity",
    "Software Engineering",
    "No concentration",
    "General",
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
    content = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', content)
    content = re.sub(r'https?://\S+', '', content)
    content = re.sub(r'!\[.*?\]\(.*?\)', '', content)
    content = re.sub(r'\s*\*,?\s*\d+', '', content)
    content = re.sub(r'XXX XXXX\s*', '', content)
    content = re.sub(r'\n{3,}', '\n\n', content)
    return content.strip()

def split_by_semester_and_concentration(text, base_filename, output_dir):
    """Split the catalog file into focused sections."""
    files_created = []

    # ---- Split concentrations into separate files ----
    concentration_pattern = re.compile(
        r'(?=^#{1,4}[^#\n]*(?:Concentration|AI and Data Science|Cybersecurity|Software Engineering Conc))',
        re.MULTILINE | re.IGNORECASE
    )
    conc_parts = concentration_pattern.split(text)

    if len(conc_parts) > 1:
        # Save intro/requirements as main file
        intro = conc_parts[0].strip()
        main_path = os.path.join(output_dir, f"{base_filename}_requirements.md")
        with open(main_path, 'w', encoding='utf-8') as f:
            f.write(f"# Computer Science B.S. — Requirements\n\n{intro}")
        files_created.append(main_path)
        print(f"    Saved: {os.path.basename(main_path)}")

        # Save each concentration
        for part in conc_parts[1:]:
            part = part.strip()
            if not part:
                continue
            # Get concentration name from first line
            first_line = part.split('\n')[0]
            conc_name = re.sub(r'^#+\s*', '', first_line).strip()
            conc_name = re.sub(r'[^\w\s]', '', conc_name).strip()
            conc_safe = re.sub(r'\s+', '_', conc_name.lower())[:50]
            conc_path = os.path.join(output_dir, f"{base_filename}_{conc_safe}.md")
            with open(conc_path, 'w', encoding='utf-8') as f:
                f.write(f"# Computer Science B.S. — {conc_name}\n\n{part}")
            files_created.append(conc_path)
            print(f"    Saved: {os.path.basename(conc_path)}")
    else:
        # No concentrations found — split by semester instead
        semester_pattern = re.compile(
            r'(?=^[\#\*\s]*(Freshman|Sophomore|Junior|Senior|Fall Year|Spring Year|Summer Year))',
            re.MULTILINE | re.IGNORECASE
        )
        sem_parts = semester_pattern.split(text)

        if len(sem_parts) > 1:
            intro = sem_parts[0].strip()
            # Group into pairs (Fall + Spring)
            groups = []
            i = 1
            while i < len(sem_parts):
                group = sem_parts[i].strip()
                if i + 1 < len(sem_parts):
                    combined = group + '\n\n' + sem_parts[i+1].strip()
                    if len(combined.split('\n')) <= 80:
                        group = combined
                        i += 2
                    else:
                        i += 1
                else:
                    i += 1
                groups.append(group)

            # Write intro + first group
            first_path = os.path.join(output_dir, f"{base_filename}_year1.md")
            with open(first_path, 'w', encoding='utf-8') as f:
                f.write(intro + '\n\n' + groups[0] if groups else intro)
            files_created.append(first_path)
            print(f"    Saved: {os.path.basename(first_path)}")

            year_labels = ['year2', 'year3', 'year4', 'year5']
            for idx, group in enumerate(groups[1:]):
                label = year_labels[idx] if idx < len(year_labels) else f"part{idx+2}"
                out_path = os.path.join(output_dir, f"{base_filename}_{label}.md")
                with open(out_path, 'w', encoding='utf-8') as f:
                    f.write(group)
                files_created.append(out_path)
                print(f"    Saved: {os.path.basename(out_path)}")
        else:
            # Just save as-is
            out_path = os.path.join(output_dir, f"{base_filename}.md")
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(text)
            files_created.append(out_path)
            print(f"    Saved: {os.path.basename(out_path)}")

    return files_created

async def scrape():
    # Delete all existing files in the folder
    if os.path.exists(OUTPUT_DIR):
        count = 0
        for f in os.listdir(OUTPUT_DIR):
            if f.endswith('.md'):
                os.remove(os.path.join(OUTPUT_DIR, f))
                count += 1
        print(f"Deleted {count} existing files from {OUTPUT_DIR}\n")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    browser_config = BrowserConfig(headless=True, verbose=False)
    config = CrawlerRunConfig(
        js_code=JS_EXPAND_ALL,
        wait_for="body",
        delay_before_return_html=3.5,
        markdown_generator=DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(threshold=0.2)
        ),
        word_count_threshold=15,
        page_timeout=40000,
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        for url in URLS:
            print(f"\nScraping: {url}")
            try:
                result = await crawler.arun(url=url, config=config)
                if not result.success:
                    print(f"  Failed: {result.error_message}")
                    continue

                cleaned = clean_content(result.markdown.fit_markdown)
                if len(cleaned) < 300:
                    cleaned = clean_content(result.markdown.raw_markdown)

                is_catalog = "catalog.fgcu.edu" in url
                base = "programs_computer-science-bs" if is_catalog else "eng_computerscience-bs"

                print(f"  Content: {len(cleaned):,} chars | Lines: {len(cleaned.split(chr(10)))}")

                if is_catalog and len(cleaned.split('\n')) > 100:
                    print(f"  Splitting into focused files...")
                    split_by_semester_and_concentration(cleaned, base, OUTPUT_DIR)
                else:
                    out_path = os.path.join(OUTPUT_DIR, f"{base}.md")
                    with open(out_path, 'w', encoding='utf-8') as f:
                        f.write(f"# Source: {url}\n\n{cleaned}")
                    print(f"  Saved: {os.path.basename(out_path)}")

            except Exception as e:
                print(f"  Error: {e}")

            await asyncio.sleep(1.5)

    print(f"\n{'='*50}")
    print(f"Done! Files in {OUTPUT_DIR}:")
    for f in sorted(os.listdir(OUTPUT_DIR)):
        path = os.path.join(OUTPUT_DIR, f)
        lines = len(open(path, encoding='utf-8', errors='ignore').read().split('\n'))
        print(f"  {f} ({lines} lines)")

asyncio.run(scrape())