import asyncio
import os
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

SEED_URLS = [
    "https://www.fgcu.edu/eng/",
    "https://www.fgcu.edu/eng/programs/",
    "https://www.fgcu.edu/eng/faculty/",
    "https://www.fgcu.edu/eng/undergraduate/",
    "https://www.fgcu.edu/eng/graduate/",
]

def url_to_filename(url):
    # Converts URL to a clean filename e.g. fgcu_eng_faculty.md
    name = url.replace("https://www.fgcu.edu/", "")
    name = name.strip("/").replace("/", "_")
    return f"fgcu_{name}.md" if name else "fgcu_home.md"

async def scrape():
    output_dir = "..\\data"
    os.makedirs(output_dir, exist_ok=True)

    config = CrawlerRunConfig(
        markdown_generator=DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(threshold=0.45)
        ),
        exclude_external_links=True,
        word_count_threshold=50,
    )

    saved = 0
    async with AsyncWebCrawler() as crawler:
        for url in SEED_URLS:
            result = await crawler.arun(url=url, config=config)
            if result.success:
                filename = url_to_filename(url)
                filepath = os.path.join(output_dir, filename)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(f"# Source: {url}\n\n")
                    f.write(result.markdown.fit_markdown)
                print(f"Saved: {filename}")
                saved += 1
            else:
                print(f"Failed: {url}")

    print(f"\nDone. {saved} files saved to {output_dir}")

asyncio.run(scrape())