import os
import re

DATA_DIR = "..\\data"

def clean_content(text):
    # Remove image markdown ![alt](url)
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)

    # Remove markdown links but keep the text [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

    # Remove bare URLs
    text = re.sub(r'https?://\S+', '', text)

    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Remove markdown table separators |---|---|
    text = re.sub(r'^\|[-| :]+\|$', '', text, flags=re.MULTILINE)

    # Remove lines that are just nav/footer boilerplate
    skip_patterns = [
        r'^\s*\*\s+\S+\s*$',                          # lone bullet items
        r'Skip to (main content|the content)',
        r'FGCU Privacy Policy',
        r'This website stores cookies',
        r'Accept\s*$',
        r'Close\s*$',
        r'Menu Toggle',
        r'fgcu-lettermark',
        r'fgcu-ribbon',
        r'Facebook|Instagram|Twitter|LinkedIn|YouTube|fgcu360',
        r'Privacy Statement',
        r'Statement of Free Expression',
        r'Webmaster',
        r'EO/VET/Title IX',
        r'All Rights Reserved',
        r'Florida Gulf Coast University\.\s*$',
        r'^\s*Learn [Mm]ore\s*$',
        r'^\s*Read [Mm]ore\s*$',
        r'^\s*Click here\s*$',
        r'^\s*View [Mm]ore\s*$',
        r'^\s*See [Mm]ore\s*$',
        r'^\s*Back to (List|Top)\s*$',
        r'^\s*\[\s*\]\s*$',               # empty links
        r'^\s*\|\s*\|\s*$',              # empty table rows
        r'^\s*Source:\s*$',              # empty source lines
        r'^\#{1,6}\s*$',                 # empty headings
        r'Experience FGCU',
        r'10501 FGCU Blvd',
        r'239-590-1000',
        r'Fort Myers, FL',
        r'Toll Free',
        r'^\s*Apply\s*$',
        r'^\s*Visit Us\s*$',
        r'^\s*Contact Us\s*$',
    ]

    lines = text.split('\n')
    cleaned = []
    prev_blank = False

    for line in lines:
        # Check skip patterns
        if any(re.search(p, line, re.IGNORECASE) for p in skip_patterns):
            continue

        # Skip lines that are only punctuation/symbols
        if re.match(r'^[\s\*\-\_\#\|\=\+]+$', line):
            continue

        # Skip very short lines that are likely nav remnants
        stripped = line.strip()
        if len(stripped) > 0 and len(stripped) < 4 and not stripped.isdigit():
            continue

        # Collapse multiple blank lines into one
        if stripped == '':
            if not prev_blank:
                cleaned.append('')
            prev_blank = True
        else:
            cleaned.append(line)
            prev_blank = False

    text = '\n'.join(cleaned)

    # Remove duplicate consecutive lines
    lines = text.split('\n')
    deduped = []
    for i, line in enumerate(lines):
        if i == 0 or line.strip() == '' or line.strip() != lines[i-1].strip():
            deduped.append(line)
    text = '\n'.join(deduped)

    # Remove duplicate paragraphs (blocks of text that repeat)
    paragraphs = re.split(r'\n{2,}', text)
    seen = set()
    unique_paragraphs = []
    for para in paragraphs:
        key = re.sub(r'\s+', ' ', para.strip().lower())
        if len(key) < 20:
            unique_paragraphs.append(para)
            continue
        if key not in seen:
            seen.add(key)
            unique_paragraphs.append(para)

    text = '\n\n'.join(unique_paragraphs)

    # Final cleanup — no more than 2 newlines in a row
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()

def clean_all():
    total = 0
    cleaned = 0
    skipped = 0

    all_files = []
    for root, dirs, files in os.walk(DATA_DIR):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for filename in files:
            if filename.endswith('.md'):
                all_files.append(os.path.join(root, filename))

    print(f"Found {len(all_files)} markdown files\n")

    for filepath in all_files:
        rel = os.path.relpath(filepath, DATA_DIR)
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                original = f.read()

            cleaned_text = clean_content(original)

            if len(cleaned_text) < 30:
                skipped += 1
                continue

            reduction = round((1 - len(cleaned_text) / max(len(original), 1)) * 100)

            if reduction > 2:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(cleaned_text)
                print(f"  Cleaned ({reduction}% smaller): {rel}")
                cleaned += 1
            else:
                skipped += 1

            total += 1

        except Exception as e:
            print(f"  Error: {rel} — {e}")

    print(f"\n{'='*60}")
    print(f"Done!")
    print(f"  Total files : {total}")
    print(f"  Cleaned     : {cleaned}")
    print(f"  Unchanged   : {skipped}")

clean_all()