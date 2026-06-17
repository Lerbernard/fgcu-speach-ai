import os
import re

COURSES_DIR = "..\\data\\courses"
OUTPUT_DIR  = "..\\data\\courses"

def split_course_file(text, filename):
    """Split a course schedule file into one file per subject prefix."""

    # Extract term from filename e.g. courses_Fall_2025.md -> Fall 2025
    term = filename.replace('courses_', '').replace('.md', '').replace('_', ' ')

    # Extract header (everything before the first ## section)
    header_match = re.match(r'^(.*?)(?=^## )', text, re.DOTALL | re.MULTILINE)
    header = header_match.group(1).strip() if header_match else f"# FGCU Engineering — {term}\n"

    # Split by subject sections: ## BCN Courses — Fall 2025
    sections = re.split(r'(?=^## [A-Z]{2,4} Courses)', text, flags=re.MULTILINE)

    files_created = {}

    for section in sections:
        section = section.strip()
        if not section:
            continue

        # Match section header
        match = re.match(r'^## ([A-Z]{2,4}) Courses', section)
        if not match:
            continue

        prefix = match.group(1)

        # Count course entries in this section
        course_count = section.count('CRN:')
        if course_count == 0:
            continue

        # Build the output file content
        content  = f"# FGCU Engineering Course Schedule — {term} — {prefix}\n\n"
        content += f"Term: {term}\n"
        content += f"Subject: {prefix}\n"
        content += f"Courses: {course_count}\n\n"
        content += "---\n\n"
        content += section

        files_created[prefix] = (content, course_count)

    return term, files_created

def process_all():
    if not os.path.exists(COURSES_DIR):
        print(f"ERROR: Folder not found: {COURSES_DIR}")
        return

    files = sorted([
        f for f in os.listdir(COURSES_DIR)
        if f.endswith('.md') and f.startswith('courses_')
    ])
    print(f"Found {len(files)} course schedule files to split\n")

    total_created = 0
    total_deleted = 0

    for filename in files:
        filepath = os.path.join(COURSES_DIR, filename)
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()

            term, sections = split_course_file(text, filename)

            if not sections:
                print(f"  Skipped (no sections found): {filename}")
                continue

            # Create subfolder for this term
            term_folder = filename.replace('.md', '')
            term_dir = os.path.join(COURSES_DIR, term_folder)
            os.makedirs(term_dir, exist_ok=True)

            # Write one file per subject prefix
            for prefix, (content, count) in sorted(sections.items()):
                out_filename = f"courses_{term.replace(' ', '_')}_{prefix}.md"
                out_path = os.path.join(term_dir, out_filename)
                with open(out_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                total_created += 1

            print(f"  {filename} -> {len(sections)} subject files in {term_folder}\\")

            # Delete the original large file
            os.remove(filepath)
            total_deleted += 1

        except Exception as e:
            print(f"  Error: {filename} — {e}")

    print(f"\n{'='*60}")
    print(f"Done!")
    print(f"  Original files removed : {total_deleted}")
    print(f"  Subject files created  : {total_created}")
    print(f"\nFolder structure:")
    print(f"  data\\courses\\")
    for d in sorted(os.listdir(COURSES_DIR)):
        full = os.path.join(COURSES_DIR, d)
        if os.path.isdir(full):
            count = len([f for f in os.listdir(full) if f.endswith('.md')])
            print(f"    {d}\\ ({count} subject files)")

process_all()