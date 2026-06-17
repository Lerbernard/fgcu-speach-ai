import os
import re

PROGRAMS_DIR = "..\\data\\pages\\03_engineering_programs"

# Map year numbers to class standing
YEAR_LABELS = {
    "1": "Freshman",
    "2": "Sophomore",
    "3": "Junior",
    "4": "Senior",
    "5": "Fifth Year (Graduate)",
}

def fix_degree_map(text, filename):
    lines = text.split('\n')
    out = []

    for line in lines:
        # Add class standing to year headings
        # Matches: "Fall Year 1:", "Spring Year 2:", "Summer Year 3:", etc.
        year_match = re.match(
            r'^(Fall|Spring|Summer|Year)\s+(Year\s+)?(\d)(.*)$',
            line.strip()
        )
        if year_match:
            season  = year_match.group(1)
            year_num= year_match.group(3)
            rest    = year_match.group(4)
            label   = YEAR_LABELS.get(year_num, "")

            if label and label.lower() not in line.lower():
                if season == "Year":
                    new_line = f"Year {year_num} ({label}){rest}"
                else:
                    new_line = f"{season} Year {year_num} — {label}{rest}"
                out.append(new_line)
                continue

        out.append(line)

    return '\n'.join(out)

def process_all():
    total = 0
    updated = 0

    for root, dirs, files in os.walk(PROGRAMS_DIR):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for filename in files:
            if not filename.startswith('programs_') or not filename.endswith('.md'):
                continue

            filepath = os.path.join(root, filename)
            rel = os.path.relpath(filepath, PROGRAMS_DIR)

            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    original = f.read()

                fixed = fix_degree_map(original, filename)

                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(fixed)

                print(f"  Updated: {rel}")
                updated += 1
                total += 1

            except Exception as e:
                print(f"  Error: {rel} — {e}")

    print(f"\n{'='*60}")
    print(f"Done! Updated {updated} program files.")
    print("Re-run ingest.py to update Pinecone.")

process_all()