import os
import re

DATA_DIR   = "..\\data"
MAX_LINES  = 100

def split_by_lines(filepath, lines, filename):
    """Split any file into 100-line chunks named part1, part2 etc."""
    base = filename.replace('.md', '')
    folder = os.path.dirname(filepath)
    chunks = [lines[i:i+MAX_LINES] for i in range(0, len(lines), MAX_LINES)]

    # Rewrite original as part 1
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(chunks[0]))

    created = []
    for i, chunk in enumerate(chunks[1:], start=2):
        out_path = os.path.join(folder, f"{base}_part{i}.md")
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(chunk))
        created.append(out_path)

    return created

def split_program_by_semester(filepath, lines, filename):
    """Split program files (programs_*.md) by semester section."""
    base = filename.replace('.md', '')
    folder = os.path.dirname(filepath)
    text = '\n'.join(lines)

    # Split on semester headings in any format:
    # ### Fall Year 1, Fall Year 1:, **Fall Year 1**, Fall Year 1 — Freshman
    semester_pattern = re.compile(
        r'(?=^[\#\*\s]*(Freshman|Sophomore|Junior|Senior|Fall Year|Spring Year|Summer Year|Year \d))',
        re.MULTILINE | re.IGNORECASE
    )

    parts = semester_pattern.split(text)

    # First part is the intro (before any semester heading)
    intro = parts[0].strip()
    semester_parts = []
    current = ""

    for part in parts[1:]:
        if re.match(r'^[\#\*\s]*(Freshman|Sophomore|Junior|Senior|Fall Year|Spring Year|Summer Year|Year \d)',
                    part, re.IGNORECASE):
            if current:
                semester_parts.append(current.strip())
            current = part
        else:
            current += part

    if current:
        semester_parts.append(current.strip())

    if not semester_parts:
        return []

    # Group into pairs (Fall + Spring of same year) to keep files ~50-80 lines
    grouped = []
    i = 0
    while i < len(semester_parts):
        group = semester_parts[i]
        # Try to combine with next part if result is under MAX_LINES
        if i + 1 < len(semester_parts):
            combined = group + '\n\n' + semester_parts[i+1]
            if len(combined.split('\n')) <= MAX_LINES:
                group = combined
                i += 2
            else:
                i += 1
        else:
            i += 1
        grouped.append(group)

    created = []

    # Write intro + first group as the original file
    first_content = intro + '\n\n' + grouped[0] if intro else grouped[0]
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(first_content)

    # Write remaining groups as part2, part3 etc.
    for idx, group in enumerate(grouped[1:], start=2):
        out_path = os.path.join(folder, f"{base}_part{idx}.md")
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(group)
        created.append(out_path)

    return created

def process_all():
    total_checked = 0
    total_split = 0
    total_created = 0
    skipped = []

    for root, dirs, files in os.walk(DATA_DIR):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for filename in files:
            if not filename.endswith('.md'):
                continue
            # Skip already-split part files
            if re.search(r'_part\d+\.md$', filename):
                continue

            filepath = os.path.join(root, filename)
            rel = os.path.relpath(filepath, DATA_DIR)

            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.read().split('\n')

                total_checked += 1
                line_count = len(lines)

                if line_count <= MAX_LINES:
                    continue  # File is fine

                # Program files: split by semester
                if filename.startswith('programs_'):
                    new_files = split_program_by_semester(filepath, lines, filename)
                    split_type = "semester"
                else:
                    new_files = split_by_lines(filepath, lines, filename)
                    split_type = "lines"

                if new_files:
                    print(f"  Split ({split_type}): {rel}")
                    print(f"    {line_count} lines -> {len(new_files)+1} files")
                    for nf in new_files:
                        print(f"    + {os.path.basename(nf)}")
                    total_split += 1
                    total_created += len(new_files)
                else:
                    skipped.append(rel)

            except Exception as e:
                print(f"  Error: {rel} — {e}")

    print(f"\n{'='*60}")
    print(f"Done!")
    print(f"  Files checked  : {total_checked}")
    print(f"  Files split    : {total_split}")
    print(f"  New files made : {total_created}")
    if skipped:
        print(f"\nCould not split:")
        for s in skipped:
            print(f"  {s}")

process_all()