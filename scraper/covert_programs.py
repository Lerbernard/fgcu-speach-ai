import os
import re

DATA_DIR = "..\\data\\pages\\03_engineering_programs"

def convert_course_table(text):
    """Convert markdown course requirement tables into readable natural language."""
    lines = text.split('\n')
    result = []
    in_table = False
    table_rows = []
    headers = []

    for line in lines:
        # Detect table rows
        if line.strip().startswith('|') and '|' in line[1:]:
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if all(re.match(r'^[-: ]+$', c) for c in cells if c):
                continue  # skip separator rows
            if not headers:
                headers = cells
            else:
                table_rows.append(cells)
            in_table = True
        else:
            if in_table and table_rows:
                # Convert accumulated table to readable text
                converted = convert_table_to_text(headers, table_rows)
                result.append(converted)
                table_rows = []
                headers = []
                in_table = False
            result.append(line)

    if in_table and table_rows:
        result.append(convert_table_to_text(headers, table_rows))

    return '\n'.join(result)

def convert_table_to_text(headers, rows):
    """Turn a course table into plain text the AI can read naturally."""
    out = []
    h = [h.lower() for h in headers]

    # Find column indices
    code_idx   = next((i for i, h_ in enumerate(h) if 'code' in h_ or h_ == ''), None)
    title_idx  = next((i for i, h_ in enumerate(h) if 'title' in h_ or 'course' in h_), None)
    credit_idx = next((i for i, h_ in enumerate(h) if 'credit' in h_ or 'hrs' in h_), None)
    note_idx   = next((i for i, h_ in enumerate(h) if 'note' in h_ or 'comment' in h_ or 'additional' in h_), None)
    offered_idx= next((i for i, h_ in enumerate(h) if 'offer' in h_ or 'avail' in h_), None)

    current_section = None

    for row in rows:
        if not any(c.strip() for c in row):
            continue

        # Detect section headers (rows with bold text or single cell content)
        if len([c for c in row if c.strip()]) <= 2:
            first = row[0].strip() if row else ''
            if first.startswith('**') or first.startswith('#') or (len(first) > 5 and not re.match(r'^[A-Z]{2,4}\s*\d', first)):
                section = first.replace('**', '').replace('#', '').strip()
                if section and len(section) > 3:
                    current_section = section
                    out.append(f"\n{section}:")
                continue

        # Build course entry
        parts = []

        code = row[code_idx].strip() if code_idx is not None and code_idx < len(row) else ''
        title = row[title_idx].strip() if title_idx is not None and title_idx < len(row) else ''
        credits = row[credit_idx].strip() if credit_idx is not None and credit_idx < len(row) else ''
        note = row[note_idx].strip() if note_idx is not None and note_idx < len(row) else ''
        offered = row[offered_idx].strip() if offered_idx is not None and offered_idx < len(row) else ''

        # Clean up
        code = re.sub(r'\*+|\d+$', '', code).strip()
        title = re.sub(r'\*+', '', title).strip()
        credits = re.sub(r'[^0-9\-]', '', credits).strip()
        note = re.sub(r'\*+|\d+$', '', note).strip()

        if code and title:
            entry = f"  {code} — {title}"
            if credits:
                entry += f" ({credits} credits)"
            if note and len(note) > 5 and 'XXX' not in note:
                entry += f". {note}"
            if offered:
                entry += f" [Offered: {offered}]"
            parts.append(entry)
        elif title and not code:
            if 'XXX' not in title:
                entry = f"  {title}"
                if credits:
                    entry += f" ({credits} credits)"
                parts.append(entry)

        if parts:
            out.extend(parts)

    return '\n'.join(out)

def clean_program_file(text):
    """Clean up program/catalog pages for better AI understanding."""

    # Remove print/download artifacts
    text = re.sub(r'## Print Options.*$', '', text, flags=re.DOTALL)
    text = re.sub(r'Close this window.*$', '', text, flags=re.DOTALL)
    text = re.sub(r'Download Page \(PDF\).*?catalog\.', '', text, flags=re.DOTALL)

    # Remove footnote numbers at end of words (COP 1500 *, 1 -> COP 1500)
    text = re.sub(r'\s*\*,?\s*\d+', '', text)

    # Convert tables to readable text
    text = convert_course_table(text)

    # Remove empty source lines
    text = re.sub(r'^# Source:\s*$', '', text, flags=re.MULTILINE)

    # Remove XXX XXXX placeholders but keep the description
    text = re.sub(r'XXX XXXX\s*', '', text)

    # Clean up excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()

def process_all():
    total = 0
    processed = 0

    for root, dirs, files in os.walk(DATA_DIR):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for filename in files:
            if not filename.endswith('.md'):
                continue
            # Only process catalog program files (programs_*.md)
            if not filename.startswith('programs_'):
                continue
            filepath = os.path.join(root, filename)
            rel = os.path.relpath(filepath, DATA_DIR)

            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    original = f.read()

                cleaned = clean_program_file(original)

                if len(cleaned) < 50:
                    continue

                reduction = round((1 - len(cleaned) / max(len(original), 1)) * 100)

                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(cleaned)

                print(f"  Processed ({reduction}% change): {rel}")
                processed += 1
                total += 1

            except Exception as e:
                print(f"  Error: {rel} — {e}")

    print(f"\n{'='*60}")
    print(f"Done! Processed {processed} program files.")
    print("Re-run ingest.py to update Pinecone with improved data.")

process_all()