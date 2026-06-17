import os
import re

COURSES_DIR = "..\\data\\courses"

def split_file_by_course(filepath, filename):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # Extract term and subject from filename e.g. courses_Fall_2020_BCN.md
    match = re.match(r'courses_(.+?)_([A-Z]{2,4})\.md$', filename)
    if not match:
        return 0

    term  = match.group(1).replace('_', ' ')   # Fall 2020
    subj  = match.group(2)                      # BCN
    folder = os.path.dirname(filepath)

    # Create subfolder for individual course files
    out_dir = os.path.join(folder, f"{subj}_{term.replace(' ', '_')}_courses")
    os.makedirs(out_dir, exist_ok=True)

    # Split on course entry start: "BCN 1251C Fall 2020 — Instructor:"
    pattern = re.compile(
        r'(?=^[A-Z]{2,4}\s+\d{3,4}[A-Z]?\s+.+?—\s+Instructor:)',
        re.MULTILINE
    )
    parts = pattern.split(content)

    # First part is the file header — skip it
    created = 0
    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Extract course code from first line e.g. "BCN 1251C Fall 2020 — Instructor: ..."
        first_line = part.split('\n')[0]
        code_match = re.match(r'([A-Z]{2,4}\s+\d{3,4}[A-Z]?)', first_line)
        if not code_match:
            continue

        code = code_match.group(1).replace(' ', '_')  # BCN_1251C
        out_filename = f"{code}_{term.replace(' ', '_')}.md"
        out_path = os.path.join(out_dir, out_filename)

        file_content  = f"# {code_match.group(1)} — {term}\n\n"
        file_content += f"Subject: {subj} | Term: {term}\n\n"
        file_content += part

        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(file_content)

        created += 1

    return created

def process_all():
    total_files  = 0
    total_created = 0

    for root, dirs, files in os.walk(COURSES_DIR):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for filename in files:
            if not filename.endswith('.md'):
                continue
            # Only process subject-level files e.g. courses_Fall_2020_BCN.md
            if not re.match(r'courses_.+?_[A-Z]{2,4}\.md$', filename):
                continue

            filepath = os.path.join(root, filename)
            rel      = os.path.relpath(filepath, COURSES_DIR)

            created = split_file_by_course(filepath, filename)
            if created:
                print(f"  {rel} -> {created} course files")
                total_files  += 1
                total_created += created

    print(f"\n{'='*60}")
    print(f"Done!")
    print(f"  Subject files processed : {total_files}")
    print(f"  Individual course files : {total_created}")

process_all()