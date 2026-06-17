import os
import re

COURSES_DIR = "..\\data\\courses"

def process_cleaned_file(text, filename):
    """Add term name to already-cleaned course entries and remove leftover boilerplate."""

    # Extract term from filename
    term = filename.replace('courses_', '').replace('.md', '').replace('_', ' ')

    lines = text.split('\n')
    out = []

    for line in lines:
        # Add term to course title lines: **COP 1500 — Title** (3 credits)
        if re.match(r'^\*\*[A-Z]{2,4}\s*\d{3,4}', line) and '(3 credits)' in line or '(4 credits)' in line or '(1 credits)' in line or '(2 credits)' in line:
            # Only add if term not already there
            if f'| {term}' not in line:
                line = line.rstrip() + f' | {term}'

        # Add term to section headers
        if re.match(r'^## [A-Z]{2,4} Courses', line) and term not in line:
            line = line.rstrip() + f' — {term}'

        # Clean leftover boilerplate from Note lines
        if line.startswith('Note:'):
            line = re.sub(r'Instructions?:?\s*click.*?method[:\.]?', '', line, flags=re.IGNORECASE)
            line = re.sub(r'Please click.*?method[:\.]?', '', line, flags=re.IGNORECASE)
            line = re.sub(r'click on the following link.*?method[:\.]?', '', line, flags=re.IGNORECASE)
            line = re.sub(r'Instructions?:\s*\.?\s*:?\s*$', '', line, flags=re.IGNORECASE)
            line = re.sub(r'^\s*[:\.\s]+$', '', line)
            line = re.sub(r'\s+', ' ', line).strip()
            # Skip empty note lines
            if line in ('Note:', 'Note: .', 'Note: :', 'Note:  :', ''):
                continue

        out.append(line)

    return '\n'.join(out)

def process_all():
    if not os.path.exists(COURSES_DIR):
        print(f"ERROR: Folder not found: {COURSES_DIR}")
        return

    files = [f for f in os.listdir(COURSES_DIR)
             if f.endswith('.md') and f.startswith('courses_')]
    print(f"Found {len(files)} course schedule files\n")

    saved = 0

    for filename in sorted(files):
        filepath = os.path.join(COURSES_DIR, filename)
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                original = f.read()

            term = filename.replace('courses_', '').replace('.md', '').replace('_', ' ')

            # Check if this is already cleaned format (has **COURSE — Title** lines)
            if '**' not in original:
                print(f"  Skipped (raw format, run original scraper first): {filename}")
                continue

            cleaned = process_cleaned_file(original, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(cleaned)

            course_count = cleaned.count('CRN:')
            print(f"  Updated: {filename} | {course_count} courses | Term '{term}' embedded")
            saved += 1

        except Exception as e:
            print(f"  Error: {filename} — {e}")

    print(f"\n{'='*60}")
    print(f"Done! Updated {saved} files.")
    print("Re-run ingest.py to update Pinecone.")

process_all()