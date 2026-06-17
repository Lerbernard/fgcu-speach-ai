import asyncio
import os
import re
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig

OUTPUT_DIR = "..\\data\\course_descriptions"
BASE_URL   = "https://fgcu-web02.fgcu.edu/CourseDescriptions/"

# Terms to scrape — 2025 and 2026 only
TERMS = [
    "Spring 2025", "Summer 2025", "Fall 2025",
    "Spring 2026", "Summer 2026", "Fall 2026",
]

# Engineering subject prefixes (used to filter results to engineering only)
ENG_PREFIXES = {
    "BCN", "BME", "CCE", "CDA", "CEG", "CEN", "CES", "CGN", "CIS", "CNT",
    "COP", "COT", "CWR", "CAI", "CAP", "EAS", "EEE", "EEL", "EES", "EGM",
    "EGN", "EGS", "EML", "ENV", "ETP", "IDC", "TTE",
}

# JavaScript: select term + Engineering college, then submit the form
def build_js(term):
    return f"""
    (async () => {{
        // Select the academic term dropdown by visible text
        const termSelect = document.querySelector('select[name*="Term"], select[id*="Term"], select[id*="term"]');
        if (termSelect) {{
            for (const opt of termSelect.options) {{
                if (opt.text.trim() === "{term}") {{ termSelect.value = opt.value; break; }}
            }}
            termSelect.dispatchEvent(new Event('change', {{bubbles:true}}));
        }}

        // Check the Engineering college checkbox/option
        const labels = Array.from(document.querySelectorAll('label, input, option'));
        for (const el of labels) {{
            const txt = (el.textContent || el.value || '').trim();
            if (txt === 'Engineering') {{
                if (el.tagName === 'INPUT') {{ el.checked = true; el.dispatchEvent(new Event('change', {{bubbles:true}})); }}
                else if (el.tagName === 'OPTION') {{ el.selected = true; el.parentElement.dispatchEvent(new Event('change', {{bubbles:true}})); }}
                else {{ const inp = el.querySelector('input'); if (inp) {{ inp.checked = true; inp.dispatchEvent(new Event('change', {{bubbles:true}})); }} }}
            }}
        }}

        await new Promise(r => setTimeout(r, 800));

        // Submit the form (find the search button)
        const btn = document.querySelector('input[type="submit"], button[type="submit"], input[value*="Search"], button');
        if (btn) btn.click();

        await new Promise(r => setTimeout(r, 3500));
    }})();
    """

def clean_descriptions(text):
    """Keep only engineering course description blocks."""
    # Course descriptions usually look like: "COP 1500 Intro to Computer Science 3 credits ..."
    lines = text.split('\n')
    kept = []
    keep_block = False
    for line in lines:
        # Start of a course entry — has an engineering prefix + number
        m = re.match(r'^\s*([A-Z]{2,4})\s*\d{3,4}', line)
        if m:
            keep_block = m.group(1) in ENG_PREFIXES
        if keep_block and line.strip():
            kept.append(line.strip())
    return '\n'.join(kept)

async def scrape():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    browser_config = BrowserConfig(headless=True, verbose=False)

    async with AsyncWebCrawler(config=browser_config) as crawler:
        for term in TERMS:
            print(f"\nScraping course descriptions: {term}")
            config = CrawlerRunConfig(
                js_code=build_js(term),
                wait_for="body",
                delay_before_return_html=4.0,
                page_timeout=60000,
                cache_mode="bypass",
            )
            try:
                result = await crawler.arun(url=BASE_URL, config=config)
                if not result.success:
                    print(f"  Failed: {result.error_message}")
                    continue

                raw = result.markdown.raw_markdown
                eng_only = clean_descriptions(raw)

                if len(eng_only) < 100:
                    print(f"  WARNING: little content captured ({len(eng_only)} chars).")
                    print(f"  The form fields may need adjusting — see notes in the script.")

                out_path = os.path.join(OUTPUT_DIR,
                          f"course_descriptions_{term.replace(' ', '_')}.md")
                with open(out_path, 'w', encoding='utf-8') as f:
                    f.write(f"# FGCU Engineering Course Descriptions — {term}\n\n")
                    f.write(eng_only)
                print(f"  Saved: {os.path.basename(out_path)} ({len(eng_only)} chars)")

            except Exception as e:
                print(f"  Error: {e}")
            await asyncio.sleep(2)

    print(f"\nDone. Files in {OUTPUT_DIR}")

asyncio.run(scrape())