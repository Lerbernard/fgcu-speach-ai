import os
import re
from urllib.parse import quote

FACULTY_DIR = "..\\data\\pages\\04_engineering_faculty"
OUTPUT_FILE = "..\\data\\ratemyprofessors_links.txt"
FGCU_SCHOOL_ID = "3988"

def extract_name(filepath):
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            # Name is on the first # or ## heading line
            if line.startswith("# ") or line.startswith("## "):
                name = line.lstrip("#").strip()
                # Skip generic headings
                if any(skip in name.lower() for skip in [
                    "source", "external", "fgcu", "experience",
                    "education", "research", "grants", "publications"
                ]):
                    continue
                # Must look like a real name (contains a comma or space)
                if "," in name or " " in name:
                    return name
    return None

def name_to_search_query(name):
    # Convert "Last, First" to "First Last" for better search results
    if "," in name:
        parts = name.split(",", 1)
        last = parts[0].strip()
        first = parts[1].strip() if len(parts) > 1 else ""
        full_name = f"{first} {last}".strip()
    else:
        full_name = name.strip()
    return full_name

def generate_links():
    if not os.path.exists(FACULTY_DIR):
        print(f"ERROR: Faculty folder not found: {FACULTY_DIR}")
        print("Run scrape_faculty.py first.")
        return

    files = [f for f in os.listdir(FACULTY_DIR) if f.endswith(".md")]
    print(f"Found {len(files)} faculty files\n")

    faculty_links = []

    for filename in sorted(files):
        filepath = os.path.join(FACULTY_DIR, filename)
        name = extract_name(filepath)
        if not name:
            print(f"  Could not extract name from: {filename}")
            continue

        search_name = name_to_search_query(name)
        encoded = quote(search_name)
        rmp_url = f"https://www.ratemyprofessors.com/search/professors/{FGCU_SCHOOL_ID}?q={encoded}"

        faculty_links.append((name, search_name, rmp_url))
        print(f"  {name} -> {rmp_url}")

    # Save to file
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("# FGCU Engineering Faculty — RateMyProfessors Links\n")
        f.write(f"# Total: {len(faculty_links)} professors\n")
        f.write(f"# School page: https://www.ratemyprofessors.com/school/{FGCU_SCHOOL_ID}\n\n")

        for name, search_name, url in faculty_links:
            f.write(f"{name}\n")
            f.write(f"{url}\n\n")

    print(f"\nSaved {len(faculty_links)} links to: {OUTPUT_FILE}")

generate_links()