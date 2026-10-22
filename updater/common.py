"""
Shared pieces for the updater: manifest + state files, a polite HTTP fetcher,
HTML -> Markdown conversion that mirrors the old clean_pages.py output, and the
small safety checks every source applies before it overwrites a data file.
"""
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone

import requests
import yaml
from bs4 import BeautifulSoup
from markdownify import markdownify

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
MANIFEST_PATH = os.path.join(HERE, "sources.yaml")
STATE_PATH = os.path.join(HERE, "state.json")


# ── manifest / state ───────────────────────────────────────

def load_manifest(path=MANIFEST_PATH):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_state(path=STATE_PATH):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_state(state, path=STATE_PATH):
    state["saved_at"] = now_iso()
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(state, f, indent=1, sort_keys=True, ensure_ascii=False)
        f.write("\n")


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today():
    return datetime.now(timezone.utc).date()


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── files ──────────────────────────────────────────────────

def abs_path(rel):
    return os.path.join(DATA, rel.replace("/", os.sep))


def rel_path(path):
    return os.path.relpath(path, DATA).replace("\\", "/")


def read_text(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8", errors="ignore") as f:
        return f.read()


def write_text(path, text):
    """Write UTF-8, keeping the line ending the file already uses (the data
    files were written on Windows with CRLF) so a content change doesn't show
    up in git as a rewrite of every line. New files get LF."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    nl = "\n"
    if os.path.exists(path):
        with open(path, "rb") as f:
            if b"\r\n" in f.read(4096):
                nl = "\r\n"
    with open(path, "w", encoding="utf-8", newline=nl) as f:
        f.write(text.rstrip() + "\n")


def remove_part_files(path):
    """split_large_files.py once broke big pages into X_part2.md, X_part3.md...
    The updater writes the whole page to X.md (ingest windows long sections
    itself), so stale part files must go or they'd be indexed twice."""
    base, ext = os.path.splitext(path)
    removed = []
    d = os.path.dirname(path)
    for fn in os.listdir(d) if os.path.isdir(d) else []:
        if re.fullmatch(re.escape(os.path.basename(base)) + r"_part\d+" + re.escape(ext), fn):
            os.remove(os.path.join(d, fn))
            removed.append(fn)
    return removed


def shrink_check(old_text, new_text, min_ratio=0.4, min_old=500):
    """Refuse to replace a substantial file with something far smaller. A page
    that lost most of its text almost always means an error page, a login
    wall, or a layout change our extractor doesn't understand - not a real
    edit. Returns (ok, reason)."""
    if not old_text or len(old_text) < min_old:
        return True, ""
    ratio = len(new_text) / len(old_text)
    if ratio < min_ratio:
        return False, f"new content is {ratio:.0%} the size of the old file"
    return True, ""


# ── HTTP ───────────────────────────────────────────────────

class Fetcher:
    """requests.Session with a fixed User-Agent, a delay between requests, and
    conditional-GET support (ETag / Last-Modified) for hosts that send them."""

    def __init__(self, defaults):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = defaults.get("user_agent", "AskTheEagleBot/1.0")
        self.delay = float(defaults.get("delay_seconds", 1.0))
        self.timeout = float(defaults.get("timeout_seconds", 45))
        self._last = 0.0
        self.requests_made = 0

    def _wait(self):
        gap = time.monotonic() - self._last
        if gap < self.delay:
            time.sleep(self.delay - gap)
        self._last = time.monotonic()
        self.requests_made += 1

    def get(self, url, cond=None):
        headers = {}
        if cond:
            if cond.get("etag"):
                headers["If-None-Match"] = cond["etag"]
            if cond.get("last_modified"):
                headers["If-Modified-Since"] = cond["last_modified"]
        self._wait()
        return self.session.get(url, headers=headers, timeout=self.timeout, allow_redirects=True)

    def post(self, url, data):
        self._wait()
        return self.session.post(url, data=data, timeout=self.timeout, allow_redirects=True)


def same_page(a, b):
    """True when two URLs name the same page ignoring scheme, trailing slash
    and a www. prefix - so a harmless canonical redirect isn't flagged."""
    def norm(u):
        u = re.sub(r"^https?://(www\.)?", "", u.strip().lower())
        return u.rstrip("/")
    return norm(a) == norm(b)


# ── HTML -> Markdown ───────────────────────────────────────

# Removed before conversion: site chrome and anything with no text value.
STRIP_SELECTORS = [
    "script", "style", "noscript", "iframe", "svg", "form", "img", "figure",
    "video", "audio", "button", "nav", "#nav-main", "#nav-inner",
    "#nav-breadcrumb", "section.experience-fgcu", ".experience-fgcu",
    ".backbtn", ".sr-only", ".skip-link", ".social", ".share", "footer",
    # hidden data table that feeds the site's JS events calendar: raw
    # "| 06 | 10 | 2026 |" day/month/year cells that read as June 10 to a
    # model. events.py turns the same table into readable dated entries.
    "table.tiva-events-calendar-data", "[class*='calendar-data']",
    # live news / events feeds embedded on many pages: different every day,
    # so they'd make those pages "change" on every run
    "section.newsfeed", "section.eventslist", ".eventlistitem",
]

# Lines that are navigation/footer boilerplate (ported from clean_pages.py).
_SKIP_LINE_PATTERNS = [re.compile(p, re.IGNORECASE) for p in (
    r"^\s*\*\s+\S+\s*$",
    r"Skip to (main content|the content)",
    r"FGCU Privacy Policy",
    r"This website stores cookies",
    r"^\s*Accept\s*$",
    r"^\s*Close\s*$",
    r"Menu Toggle",
    r"fgcu-lettermark",
    r"fgcu-ribbon",
    r"^\s*(Facebook|Instagram|Twitter|LinkedIn|YouTube|fgcu360)\s*$",
    r"Privacy Statement",
    r"Statement of Free Expression",
    r"Webmaster",
    r"EO/VET/Title IX",
    r"All Rights Reserved",
    r"Florida Gulf Coast University\.\s*$",
    r"^\s*Learn [Mm]ore\s*$",
    r"^\s*Read [Mm]ore\s*$",
    r"^\s*Click here\s*$",
    r"^\s*View [Mm]ore\s*$",
    r"^\s*See [Mm]ore\s*$",
    r"^\s*Back to (List|Top)\s*$",
    r"^\s*Toggle .*$",
    r"^\s*\[\s*\]\s*$",
    r"^\s*\|[\s|]*$",
    r"^\s*Source:\s*$",
    r"^#{1,6}\s*$",
    r"Experience FGCU",
    r"10501 FGCU Blvd",
    r"239-590-1000",
    r"Fort Myers, FL",
    r"Toll Free",
    r"^\s*Apply\s*$",
    r"^\s*Visit Us\s*$",
    r"^\s*Contact Us\s*$",
    r"^\s*In This Section\s*$",
    r"^\s*Menu\s*$",
)]

_BLOCK_START = re.compile(r"^\s*(#{1,6}\s|[*\-+]\s|\d+[.)]\s|\||>|<!--)")


def unwrap_paragraphs(text: str) -> str:
    """FGCU's HTML hard-wraps prose at ~90 columns and markdownify keeps those
    newlines. Join the lines of a paragraph (and the indented continuation
    lines of a list item) so each paragraph is one line, as the old scraper
    output was. Headings, list items, tables and blank lines stay put."""
    out = []
    for line in text.split("\n"):
        prev = out[-1] if out else ""
        joinable_prev = prev.strip() and not prev.lstrip().startswith("#") and not prev.lstrip().startswith("|")
        continuation = line.strip() and not _BLOCK_START.match(line)
        if joinable_prev and continuation and (line.startswith(" ") or not _BLOCK_START.match(prev)):
            out[-1] = prev.rstrip() + " " + line.strip()
        else:
            out.append(line)
    return "\n".join(out)


def extract_main(soup: BeautifulSoup):
    """The content region of an FGCU page (main > article), with chrome removed.
    Falls back to <body> for pages built differently."""
    main = soup.select_one("main") or soup.select_one("article") or soup.body or soup
    for sel in STRIP_SELECTORS:
        for el in main.select(sel):
            el.decompose()
    for el in main.find_all(True):
        # hidden accordions (aria-hidden) KEEP their text: that is the expanded
        # content the old crawl4ai scripts clicked open before saving.
        if el.name in ("a",) and el.get_text(strip=True).lower().startswith("toggle "):
            el.decompose()
    return main


def clean_markdown(text: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)                 # images
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)              # links -> text
    text = re.sub(r"https?://\S+", "", text)                          # bare URLs
    text = re.sub(r"^\|[-| :]+\|\s*$", "", text, flags=re.MULTILINE)  # table separators
    text = text.replace("\xa0", " ")
    text = re.sub(r"^(#{1,6}\s+)\*\*(.+?)\*\*\s*$", r"\1\2", text, flags=re.MULTILINE)  # bold inside headings
    text = unwrap_paragraphs(text)

    cleaned, prev_blank = [], False
    for line in text.split("\n"):
        if any(p.search(line) for p in _SKIP_LINE_PATTERNS):
            continue
        if re.match(r"^[\s*\-_#|=+]+$", line):
            continue
        stripped = line.strip()
        if 0 < len(stripped) < 4 and not stripped.isdigit():
            continue
        if stripped == "":
            if not prev_blank:
                cleaned.append("")
            prev_blank = True
        else:
            cleaned.append(line.rstrip())
            prev_blank = False
    text = "\n".join(cleaned)

    # drop consecutive duplicate lines, then duplicate paragraphs
    lines, deduped = text.split("\n"), []
    for i, line in enumerate(lines):
        if i == 0 or line.strip() == "" or line.strip() != lines[i - 1].strip():
            deduped.append(line)
    paragraphs, seen, unique = re.split(r"\n{2,}", "\n".join(deduped)), set(), []
    for para in paragraphs:
        key = re.sub(r"\s+", " ", para.strip().lower())
        if len(key) >= 20:
            if key in seen:
                continue
            seen.add(key)
        unique.append(para)
    text = "\n\n".join(unique)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def page_to_markdown(html: str, url: str) -> str:
    """Full pipeline for an ordinary content page. The first line records the
    source URL as an HTML comment, so ingest never turns it into a heading
    chunk and the model never sees a link."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.find("h1")
    title_text = title.get_text(" ", strip=True) if title else ""
    main = extract_main(soup)
    md = markdownify(str(main), heading_style="ATX", strip=["a", "img"], bullets="*")
    md = clean_markdown(md)
    if title_text and not re.match(r"^#\s", md):
        md = f"# {title_text}\n\n{md}"
    return f"<!-- source: {url} -->\n\n{md}"
