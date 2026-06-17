import os
import re

# Folder with the raw faculty .md files (adjust if needed)
IN_DIR  = "..\\data\\pages\\engineering_faculty"
OUT_DIR = "..\\data\\pages\\engineering_faculty_cleaned"

def clean_faculty_file(text):
    lines = text.split('\n')
    out = []

    # Drop the first "# Lastname, Firstname" line — it duplicates the ## line
    # Find the "## Name" heading and start there
    start = 0
    for i, line in enumerate(lines):
        if line.strip().startswith('## '):
            start = i
            break
    lines = lines[start:]

    for line in lines:
        stripped = line.strip()

        # Convert "Toggle X" markers into bold section headers (keep the section meaning)
        if stripped == "Toggle Education":
            out.append("\n**Education**")
            continue
        if stripped == "Toggle Specialties":
            out.append("\n**Specialties**")
            continue
        if stripped == "Toggle Publications":
            out.append("\n**Publications**")
            continue
        if stripped == "Toggle Research and Teaching Interests":
            out.append("\n**Research and Teaching Interests**")
            continue

        # Bare repeated section labels -> bold
        if stripped == "Research and Teaching Interests":
            out.append("**Research and Teaching Interests**")
            continue
        if stripped == "Memberships":
            out.append("**Memberships**")
            continue

        # Skip pure navigation / link-only lines
        if re.match(r'^(View .*portfolio|View my publications\.?|Google Scholar|Linked-?In Profile:?)$',
                    stripped, re.IGNORECASE):
            continue
        if stripped.startswith("* Linked-In Profile") or stripped.startswith("* Research and Teaching Interests"):
            continue

        out.append(line)

    text = '\n'.join(out)
    # Collapse 3+ blank lines into 1
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    # Convert the "## Name" heading into a clean "# Name"
    text = re.sub(r'^##\s+', '# ', text, count=1)
    return text.strip() + '\n'

def process():
    if not os.path.isdir(IN_DIR):
        print(f"ERROR: {IN_DIR} not found. Adjust IN_DIR.")
        return
    os.makedirs(OUT_DIR, exist_ok=True)

    count = 0
    for root, dirs, files in os.walk(IN_DIR):
        # don't recurse into ratemyprofessors — those are reviews, not bios
        dirs[:] = [d for d in dirs if "ratemyprofessor" not in d.lower()]
        for fn in files:
            if not fn.endswith(".md"):
                continue
            in_path = os.path.join(root, fn)
            with open(in_path, "r", encoding="utf-8", errors="ignore") as f:
                raw = f.read()

            cleaned = clean_faculty_file(raw)

            # Preserve subfolder structure under OUT_DIR
            rel = os.path.relpath(in_path, IN_DIR)
            out_path = os.path.join(OUT_DIR, rel)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(cleaned)
            count += 1
            print(f"  Cleaned: {rel}")

    print(f"\n{'='*60}")
    print(f"Done! Cleaned {count} faculty files.")
    print(f"Output: {OUT_DIR}")
    print(f"Review them, then replace the originals if they look good.")

process()