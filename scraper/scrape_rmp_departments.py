import asyncio
import os
import re
import httpx

OUTPUT_BASE = "..\\data\\pages\\04_engineering_faculty\\ratemyprofessors"

RMP_GRAPHQL_URL    = "https://www.ratemyprofessors.com/graphql"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Authorization": "Basic dGVzdDp0ZXN0",
    "Content-Type": "application/json",
    "Referer": "https://www.ratemyprofessors.com/",
    "Origin": "https://www.ratemyprofessors.com",
}

# Department folders and their professor profile URLs
DEPARTMENTS = {
    "01_bioengineering": [
        "https://www.ratemyprofessors.com/professor/2573092",
        "https://www.ratemyprofessors.com/professor/2404307",
        "https://www.ratemyprofessors.com/professor/2098402",
        "https://www.ratemyprofessors.com/professor/2098387",
        "https://www.ratemyprofessors.com/professor/3044435",
        "https://www.ratemyprofessors.com/professor/1703216",
        "https://www.ratemyprofessors.com/professor/2484441",
    ],
    "02_construction_management": [
        "https://www.ratemyprofessors.com/professor/1807029",
        "https://www.ratemyprofessors.com/professor/1912099",
        "https://www.ratemyprofessors.com/professor/2753210",
        "https://www.ratemyprofessors.com/professor/2944862",
        "https://www.ratemyprofessors.com/professor/3036365",
    ],
    "03_civil_engineering": [
        "https://www.ratemyprofessors.com/professor/2404307",
        "https://www.ratemyprofessors.com/professor/1711812",
        "https://www.ratemyprofessors.com/professor/1321392",
        "https://www.ratemyprofessors.com/professor/3119979",
    ],
    "04_environmental_engineering": [
        "https://www.ratemyprofessors.com/professor/2404307",
        "https://www.ratemyprofessors.com/professor/2929905",
        "https://www.ratemyprofessors.com/professor/2576049",
        "https://www.ratemyprofessors.com/professor/1433770",
        "https://www.ratemyprofessors.com/professor/2576048",
    ],
    "05_software_engineering_cs": [
        "https://www.ratemyprofessors.com/professor/1840301",
        "https://www.ratemyprofessors.com/professor/2940428",
        "https://www.ratemyprofessors.com/professor/2233026",
        "https://www.ratemyprofessors.com/professor/2066935",
        "https://www.ratemyprofessors.com/professor/2882177",
        "https://www.ratemyprofessors.com/professor/2924645",
        "https://www.ratemyprofessors.com/professor/2934078",
        "https://www.ratemyprofessors.com/professor/2940426",
        "https://www.ratemyprofessors.com/professor/1323465",
        "https://www.ratemyprofessors.com/professor/2989528",
    ],
}

PROF_QUERY = """
query TeacherRatingsPageQuery($id: ID!) {
  node(id: $id) {
    ... on Teacher {
      id
      legacyId
      firstName
      lastName
      department
      avgRating
      avgDifficulty
      numRatings
      wouldTakeAgainPercent
      school { name }
    }
  }
}
"""

RATINGS_QUERY = """
query RatingsListQuery($id: ID!, $count: Int!, $cursor: String) {
  node(id: $id) {
    ... on Teacher {
      ratings(first: $count, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        edges {
          node {
            date
            class
            comment
            helpfulRating
            clarityRating
            difficultyRating
            wouldTakeAgain
            grade
            isForOnlineClass
          }
        }
      }
    }
  }
}
"""

def legacy_id_to_gql_id(legacy_id):
    """Convert numeric professor ID to base64 GraphQL ID."""
    return base64_encode(f"Teacher-{legacy_id}")

def base64_encode(s):
    import base64
    return base64.b64encode(s.encode()).decode()

def extract_legacy_id(url):
    match = re.search(r"/professor/(\d+)", url)
    return match.group(1) if match else None

async def get_professor_info(client, gql_id):
    payload = {"query": PROF_QUERY, "variables": {"id": gql_id}}
    resp = await client.post(RMP_GRAPHQL_URL, json=payload, headers=HEADERS)
    data = resp.json()
    return data.get("data", {}).get("node")

async def get_all_ratings(client, gql_id):
    all_ratings = []
    cursor = None
    while True:
        variables = {"id": gql_id, "count": 20}
        if cursor:
            variables["cursor"] = cursor
        payload = {"query": RATINGS_QUERY, "variables": variables}
        resp = await client.post(RMP_GRAPHQL_URL, json=payload, headers=HEADERS)
        data = resp.json()
        node = data.get("data", {}).get("node", {})
        ratings_data = node.get("ratings", {})
        edges = ratings_data.get("edges", [])
        page_info = ratings_data.get("pageInfo", {})
        for edge in edges:
            all_ratings.append(edge["node"])
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        await asyncio.sleep(0.3)
    return all_ratings

def build_markdown(prof, ratings, profile_url):
    name = f"{prof.get('firstName', '')} {prof.get('lastName', '')}".strip()
    would_take = prof.get("wouldTakeAgainPercent", -1)

    md  = f"# {name}\n\n"
    md += f"**RMP Profile:** {profile_url}\n"
    md += f"**Department:** {prof.get('department', 'N/A')}\n"
    md += f"**School:** {prof.get('school', {}).get('name', 'FGCU')}\n"
    md += f"**Overall Rating:** {prof.get('avgRating', 'N/A')} / 5\n"
    md += f"**Difficulty:** {prof.get('avgDifficulty', 'N/A')} / 5\n"
    md += f"**Total Ratings:** {prof.get('numRatings', 0)}\n"
    if would_take and would_take != -1:
        md += f"**Would Take Again:** {round(would_take)}%\n"
    md += "\n---\n\n"

    if ratings:
        md += f"## Student Reviews ({len(ratings)} total)\n\n"
        for j, r in enumerate(ratings, 1):
            md += f"### Review {j}\n"
            if r.get("date"):
                md += f"- **Date:** {r['date'][:10]}\n"
            if r.get("class"):
                md += f"- **Course:** {r['class']}\n"
            if r.get("grade"):
                md += f"- **Grade:** {r['grade']}\n"
            md += f"- **Quality:** {r.get('helpfulRating', 'N/A')} / 5\n"
            md += f"- **Difficulty:** {r.get('difficultyRating', 'N/A')} / 5\n"
            md += f"- **Would Take Again:** {'Yes' if r.get('wouldTakeAgain') == 1 else 'No'}\n"
            if r.get("isForOnlineClass"):
                md += f"- **Online Class:** Yes\n"
            if r.get("comment"):
                md += f"\n> {r['comment']}\n"
            md += "\n---\n\n"
    else:
        md += "_No reviews found._\n"

    return md, name

async def scrape_all():
    # Create all department subfolders
    seen_urls = set()  # avoid scraping same professor twice
    for dept_folder in DEPARTMENTS:
        os.makedirs(os.path.join(OUTPUT_BASE, dept_folder), exist_ok=True)
    print(f"Created {len(DEPARTMENTS)} department folders\n")

    total_saved = 0
    total_failed = []

    async with httpx.AsyncClient(timeout=20) as client:
        for dept_folder, urls in DEPARTMENTS.items():
            dept_name = dept_folder.replace("_", " ").title()
            print(f"\n{'='*50}")
            print(f"Department: {dept_name}")
            print(f"{'='*50}")

            for url in urls:
                # Deduplicate — same prof can appear in multiple departments
                if url in seen_urls:
                    print(f"  Skipped (already scraped): {url}")
                    # Copy file to this dept folder if it exists elsewhere
                    continue
                seen_urls.add(url)

                legacy_id = extract_legacy_id(url)
                if not legacy_id:
                    print(f"  Invalid URL: {url}")
                    continue

                gql_id = legacy_id_to_gql_id(legacy_id)
                print(f"\n  [{legacy_id}] {url}")

                try:
                    # Get professor info
                    prof = await get_professor_info(client, gql_id)
                    if not prof:
                        print(f"  Not found in RMP API")
                        total_failed.append(url)
                        continue

                    name = f"{prof.get('firstName', '')} {prof.get('lastName', '')}".strip()
                    print(f"  Name: {name}")
                    print(f"  Rating: {prof.get('avgRating')} / 5  ({prof.get('numRatings')} reviews)")

                    # Get all reviews (paginates automatically)
                    ratings = await get_all_ratings(client, gql_id)
                    print(f"  Reviews loaded: {len(ratings)}")

                    # Build and save markdown
                    md, name = build_markdown(prof, ratings, url)
                    safe_name = re.sub(r"[^\w\s]", "", name).strip()
                    safe_name = re.sub(r"\s+", "_", safe_name).lower()
                    filename = f"{safe_name[:50]}.md"
                    filepath = os.path.join(OUTPUT_BASE, dept_folder, filename)

                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(md)
                    print(f"  Saved: {dept_folder}\\{filename}")
                    total_saved += 1

                except Exception as e:
                    print(f"  Error: {e}")
                    total_failed.append(url)

                await asyncio.sleep(0.8)

    print(f"\n{'='*50}")
    print(f"All done!")
    print(f"  Saved:  {total_saved} professor files")
    print(f"  Failed: {len(total_failed)}")
    if total_failed:
        print("\nFailed URLs:")
        for u in total_failed:
            print(f"  {u}")

asyncio.run(scrape_all())