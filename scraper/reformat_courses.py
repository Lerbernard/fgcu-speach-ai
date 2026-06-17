import os
import re

COURSES_DIR = "..\\data\\courses"

def reformat_entries(text, term):
    """
    Reformat each course entry so instructor is on the first line.

    FROM:
      **COP 1500 — Intro to Computer Science** (3 credits) | Fall 2025
      CRN: 83989 | Instructor: Ciris, Pelin | 5 of 30 seats available
      Schedule: M W -- 01:30pm - 02:45pm -- Holmes Engineering 402
      Session: Full Term

    TO:
      COP 1500 Fall 2025 — Instructor: Ciris, Pelin
      Course: Intro to Computer Science (3 credits)
      CRN: 83989 | Schedule: M W 01:30pm-02:45pm Holmes Engineering 402
      Session: Full Term
    """
    lines = text.split('\n')
    out = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Detect course title line: **COP 1500 — Title** (N credits) | Term
        title_match = re.match(
            r'^\*\*([A-Z]{2,4}\s*\d{3,4}[A-Z]?)\s*—\s*(.+?)\*\*\s*\((\d+)\s*credits?\)\s*(?:\|\s*(.+))?$',
            line.strip()
        )

        if title_match:
            code    = title_match.group(1).strip()
            title   = title_match.group(2).strip()
            credits = title_match.group(3).strip()
            term_in_line = title_match.group(4).strip() if title_match.group(4) else term

            # Read ahead for CRN/Instructor line
            crn_line = lines[i+1].strip() if i+1 < len(lines) else ''
            schedule_line = lines[i+2].strip() if i+2 < len(lines) else ''
            session_line  = lines[i+3].strip() if i+3 < len(lines) else ''
            note_line     = lines[i+4].strip() if i+4 < len(lines) else ''

            # Extract instructor from CRN line
            instructor = ''
            crn = ''
            seats = ''
            crn_match = re.search(r'CRN:\s*(\d+)', crn_line)
            instr_match = re.search(r'Instructor:\s*([^|]+)', crn_line)
            seats_match = re.search(r'(\d+\s*of\s*\d+\s*seats[^|]*|CLOSED[^|]*)', crn_line)

            if crn_match:
                crn = crn_match.group(1).strip()
            if instr_match:
                instructor = instr_match.group(1).strip()
            if seats_match:
                seats = seats_match.group(1).strip()

            # Clean schedule
            sched_clean = re.sub(r'^Schedule:\s*', '', schedule_line)
            sched_clean = re.sub(r'\s+', ' ', sched_clean).strip()

            # Build new format — instructor first
            if instructor:
                out.append(f"{code} {term_in_line} — Instructor: {instructor}")
            else:
                out.append(f"{code} {term_in_line}")

            out.append(f"Course: {title} ({credits} credits) | CRN: {crn}")

            if sched_clean:
                out.append(f"Schedule: {sched_clean}")

            if session_line.startswith('Session:'):
                out.append(session_line)

            if note_line.startswith('Note:') and len(note_line) > 6:
                out.append(note_line)

            out.append('')  # blank line between entries

            # Skip the lines we already consumed
            skip = 3
            if session_line.startswith('Session:'):
                skip += 1
            if note_line.startswith('Note:') and len(note_line) > 6:
                skip += 1
            i += skip + 1
            continue

        out.append(line)
        i += 1

    return '\n'.join(out)

def process_all():
    total = 0
    updated = 0

    for root, dirs, files in os.walk(COURSES_DIR):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for filename in files:
            if not filename.endswith('.md'):
                continue

            filepath = os.path.join(root, filename)
            rel = os.path.relpath(filepath, COURSES_DIR)

            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    original = f.read()

                # Extract term from filename
                term_match = re.search(
                    r'(Fall|Spring|Summer)_(\d{4})',
                    filename, re.IGNORECASE
                )
                term = term_match.group(0).replace('_', ' ') if term_match else ''

                # Only process files with course entries
                if 'CRN:' not in original or 'Instructor:' not in original:
                    continue

                reformatted = reformat_entries(original, term)

                if reformatted != original:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(reformatted)
                    print(f"  Reformatted: {rel}")
                    updated += 1

                total += 1

            except Exception as e:
                print(f"  Error: {rel} — {e}")

    print(f"\n{'='*60}")
    print(f"Done! Reformatted {updated} of {total} course files.")
    print("Clear Pinecone and re-run ingest.py to update.")

process_all()