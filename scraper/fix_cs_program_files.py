import os
import re

CS_DIR = "..\\data\\pages\\03_engineering_programs\\computer_science_bs"

YEAR_LABELS = {
    "1": ("Freshman",  "Year 1"),
    "2": ("Sophomore", "Year 2"),
    "3": ("Junior",    "Year 3"),
    "4": ("Senior",    "Year 4"),
    "5": ("Fifth Year","Year 5"),
}

def get_concentration_name(filepath):
    """Extract concentration name from filename or file header."""
    filename = os.path.basename(filepath)
    # From filename e.g. programs_computer-science-bs_cybersecurity.md
    match = re.search(r'_bs_(.+)\.md$', filename)
    if match:
        name = match.group(1).replace('_', ' ').replace('-', ' ').title()
        return name
    # From file header
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        first_lines = f.read(500)
    h_match = re.search(r'#+ .*?—\s*(.+)', first_lines)
    if h_match:
        return h_match.group(1).strip()
    return "Computer Science"

def season_label(season, year_num):
    """Convert Fall/Spring/Summer + year number to labeled heading."""
    class_standing, year_label = YEAR_LABELS.get(str(year_num), ("Year " + str(year_num), "Year " + str(year_num)))
    return f"### {season} {year_label} ({class_standing})"

def convert_table_to_text(table_lines, concentration):
    """Convert markdown course table rows to clean text."""
    out = []
    current_section = None

    for line in table_lines:
        # Skip separator rows |---|---|
        if re.match(r'^\|\s*[-:| ]+\s*\|', line):
            continue

        cells = [c.strip() for c in line.split('|')[1:-1]]
        if not cells:
            continue

        # Clean cells
        cells = [re.sub(r'\*+', '', c).strip() for c in cells]
        course_cell = cells[0] if len(cells) > 0 else ''
        note_cell   = cells[1] if len(cells) > 1 else ''
        offer_cell  = cells[2] if len(cells) > 2 else ''

        # Skip empty rows
        if not any(c.strip() for c in cells):
            continue

        # Detect year/semester heading rows like **Fall Year 1** or **Fall Year 1 — Junior**
        year_match = re.match(
            r'^\*?\*?(Fall|Spring|Summer)\s+(?:YEAR|Year)\s+(\d)\*?\*?',
            course_cell, re.IGNORECASE
        )
        if year_match or re.match(r'^\*?\*?(Freshman|Sophomore|Junior|Senior)', course_cell, re.IGNORECASE):
            season_m = re.match(r'(Fall|Spring|Summer)\s+(?:YEAR|Year)\s+(\d)', course_cell, re.IGNORECASE)
            if season_m:
                season   = season_m.group(1).capitalize()
                year_num = season_m.group(2)
                label = season_label(season, year_num)
                current_section = f"{season} Year {year_num}"
                out.append(f"\n{label} — {concentration}")
            else:
                out.append(f"\n### {course_cell} — {concentration}")
            continue

        # Skip total credits row
        if 'total credits' in course_cell.lower():
            out.append(f"\n**Total Credits Required: 120**")
            continue

        # Build course entry
        if course_cell:
            entry = f"- {course_cell}"
            if note_cell and len(note_cell) > 3 and 'substitute' not in note_cell.lower()[:20]:
                entry += f" — {note_cell}"
            out.append(entry)
        elif note_cell:
            # Empty course cell with note = elective description
            out.append(f"- {note_cell}")

    return '\n'.join(out)

def fix_file(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        text = f.read()

    # Skip if no tables
    if '|' not in text or '---' not in text:
        return False

    concentration = get_concentration_name(filepath)
    lines = text.split('\n')
    out_lines = []
    in_table = False
    table_buffer = []

    for line in lines:
        if line.strip().startswith('|'):
            in_table = True
            table_buffer.append(line)
        else:
            if in_table and table_buffer:
                converted = convert_table_to_text(table_buffer, concentration)
                out_lines.append(converted)
                table_buffer = []
                in_table = False
            out_lines.append(line)

    if table_buffer:
        out_lines.append(convert_table_to_text(table_buffer, concentration))

    result = '\n'.join(out_lines)
    result = re.sub(r'\n{3,}', '\n\n', result)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(result.strip())

    return True

def process_all():
    if not os.path.exists(CS_DIR):
        print(f"ERROR: Folder not found: {CS_DIR}")
        return

    files = [f for f in os.listdir(CS_DIR) if f.endswith('.md')]
    print(f"Found {len(files)} files in computer_science_bs\\\n")

    fixed = 0
    skipped = 0

    for filename in sorted(files):
        filepath = os.path.join(CS_DIR, filename)
        lines_before = len(open(filepath, encoding='utf-8', errors='ignore').read().split('\n'))

        changed = fix_file(filepath)

        lines_after = len(open(filepath, encoding='utf-8', errors='ignore').read().split('\n'))

        if changed:
            print(f"  Fixed: {filename} ({lines_before} -> {lines_after} lines)")
            fixed += 1
        else:
            print(f"  Skipped (no tables): {filename}")
            skipped += 1

    print(f"\n{'='*60}")
    print(f"Done! Fixed: {fixed} | Skipped: {skipped}")
    print("Re-run ingest.py to update Pinecone.")

process_all()
