import os
import re

CS_DIR = "..\\data\\pages\\03_engineering_programs\\computer_science_bs"

# Files to compare for uniqueness
CONC_FILES = [
    "programs_computer-science-bs_computer_science_no_concentration.md",
    "programs_computer-science-bs_ai_and_data_science_concentration.md",
    "programs_computer-science-bs_cybersecurity_concentration.md",
    "programs_computer-science-bs_software_engineering_concentration.md",
]

COURSE_RE = re.compile(r'\b([A-Z]{2,4}\s?\d{3,4}[A-Z]?)\b')

def extract_courses(text):
    return set(COURSE_RE.findall(text.replace('-', ' ')))

def conc_name_from_file(filename):
    # programs_computer-science-bs_ai_and_data_science_concentration.md -> AI and Data Science
    name = filename.replace("programs_computer-science-bs_", "").replace(".md", "")
    name = name.replace("_concentration", "").replace("_", " ")
    return name.title()

def process():
    # Read all concentration files and their course sets
    file_courses = {}
    file_text = {}
    for fn in CONC_FILES:
        path = os.path.join(CS_DIR, fn)
        if not os.path.exists(path):
            print(f"  Missing: {fn}")
            continue
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
        file_text[fn] = text
        file_courses[fn] = extract_courses(text)

    if len(file_courses) < 2:
        print("Not enough concentration files to compare.")
        return

    # Find courses common to ALL concentrations
    all_sets = list(file_courses.values())
    common = set.intersection(*all_sets)

    for fn, courses in file_courses.items():
        # Unique = courses in this file but not in the common core
        unique = sorted(courses - common)
        conc = conc_name_from_file(fn)

        # Skip if already enhanced
        text = file_text[fn]
        if "## What makes this concentration unique" in text:
            print(f"  Already enhanced: {fn}")
            continue

        # Build front-matter highlighting unique courses
        alt_phrases = f"(also called the {conc} track, {conc} option, {conc} emphasis)"
        front = f"## What makes this concentration unique {alt_phrases}\n"
        if unique:
            front += f"The courses that set the {conc} concentration apart from other Computer Science concentrations are: "
            front += ", ".join(unique) + ".\n\n"
        else:
            front += f"The {conc} concentration shares a common core with other CS concentrations.\n\n"

        # Insert front-matter right after the first heading line
        lines = text.split('\n')
        # Find first non-empty heading
        insert_at = 0
        for idx, line in enumerate(lines):
            if line.startswith('# '):
                insert_at = idx + 1
                break
        new_text = '\n'.join(lines[:insert_at]) + '\n\n' + front + '\n'.join(lines[insert_at:])

        with open(os.path.join(CS_DIR, fn), 'w', encoding='utf-8') as f:
            f.write(new_text)

        print(f"  Enhanced: {fn}")
        print(f"    Unique courses: {', '.join(unique) if unique else 'none (shared core)'}")

    print("\nDone. Re-run ingest.py to update Pinecone.")

process()