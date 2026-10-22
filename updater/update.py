"""
Ask the Eagle data updater.

Re-scrapes the FGCU pages behind data/ and rewrites only the files whose
source actually changed. Hand-edited files are never overwritten; the report
says when their source page changed. State (page hashes, ETags, last-seen
terms) lives in updater/state.json and is committed with the data.

    python updater/update.py                      # everything
    python updater/update.py --only courses       # one source
    python updater/update.py --dry-run --limit 5  # look, don't touch
    python updater/update.py --report out.md      # Markdown report (PR body)

Sources: pages, faculty, courses, descriptions, events, calendar.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import calendar_dates   # noqa: E402
import courses          # noqa: E402
import descriptions     # noqa: E402
import events           # noqa: E402
import faculty          # noqa: E402
import pages            # noqa: E402
from common import Fetcher, load_manifest, load_state, save_state, now_iso  # noqa: E402

SOURCES = {
    "pages": pages, "faculty": faculty, "courses": courses,
    "descriptions": descriptions, "events": events, "calendar": calendar_dates,
}


class Report:
    """Collects what happened per source and renders it as Markdown."""

    def __init__(self):
        self.counts = {}        # source -> {new, updated, removed, unchanged}
        self.files = []         # (source, action, path)
        self.lines = {}         # source -> free-form summary lines
        self.watch = []         # (what, url, detail)
        self.warnings = []
        self.errors = []

    def _c(self, source):
        return self.counts.setdefault(source, {"new": 0, "updated": 0, "removed": 0, "unchanged": 0})

    def written(self, source, rel, action, quiet=False):
        self._c(source)[action] += 1
        if not quiet:
            self.files.append((source, action, rel))

    def removed(self, source, what, quiet=False):
        self._c(source)["removed"] += 1
        if not quiet:
            self.files.append((source, "removed", what))

    def unchanged(self, source):
        self._c(source)["unchanged"] += 1

    def summary_line(self, source, text):
        self.lines.setdefault(source, []).append(text)

    def watch_changed(self, what, url, last_changed, detail=None):
        self.watch.append((what, url, detail or f"page changed (previous change: {last_changed or 'baseline'})"))

    def warn(self, source, text):
        self.warnings.append(f"{source}: {text}")

    def error(self, source, text):
        self.errors.append(f"{source}: {text}")

    @property
    def changed_files(self):
        return sum(c["new"] + c["updated"] + c["removed"] for c in self.counts.values())

    def to_markdown(self, started, elapsed, dry_run):
        L = [f"## Data update {started[:10]}" + (" (dry run)" if dry_run else ""), ""]
        L.append(f"{self.changed_files} file change(s) in {elapsed:.0f}s.")
        L.append("")
        L.append("| source | new | updated | removed | unchanged |")
        L.append("|---|---:|---:|---:|---:|")
        for src, c in self.counts.items():
            L.append(f"| {src} | {c['new']} | {c['updated']} | {c['removed']} | {c['unchanged']} |")
        for src, lines in self.lines.items():
            L += ["", f"**{src}**"] + [f"- {ln}" for ln in lines]
        if self.files:
            L += ["", "### Changed files"]
            L += [f"- `{rel}` — {action} ({src})" for src, action, rel in self.files[:200]]
            if len(self.files) > 200:
                L.append(f"- … and {len(self.files) - 200} more")
        if self.watch:
            L += ["", "### Needs a human: source changed behind a hand-edited file"]
            L += [f"- **{what}** — {detail} — {url}" for what, url, detail in self.watch]
        if self.warnings:
            L += ["", "### Warnings"] + [f"- {w}" for w in self.warnings]
        if self.errors:
            L += ["", "### Errors"] + [f"- {e}" for e in self.errors]
        return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", choices=sorted(SOURCES), help="run only these sources")
    ap.add_argument("--dry-run", action="store_true", help="fetch and compare, write nothing")
    ap.add_argument("--limit", type=int, help="per source: only the first N items (testing)")
    ap.add_argument("--report", help="write a Markdown report to this path")
    args = ap.parse_args(argv)

    manifest = load_manifest()
    state = load_state()
    fetch = Fetcher(manifest.get("defaults", {}))
    report = Report()
    started, t0 = now_iso(), time.monotonic()

    for name in (args.only or list(SOURCES)):
        print(f"== {name}", flush=True)
        try:
            SOURCES[name].run(manifest, state, fetch, report, dry_run=args.dry_run, limit=args.limit)
        except Exception as e:  # a crash in one source must not lose the others
            report.error(name, f"crashed: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
        c = report.counts.get(name, {})
        print(f"   {c}", flush=True)

    elapsed = time.monotonic() - t0
    md = report.to_markdown(started, elapsed, args.dry_run)
    if args.report:
        with open(args.report, "w", encoding="utf-8", newline="\n") as f:
            f.write(md)
    print(md)
    print(f"{fetch.requests_made} requests, {elapsed:.0f}s")
    if not args.dry_run and not args.limit:
        state["last_run"] = {"at": started, "changed_files": report.changed_files,
                             "errors": len(report.errors)}
        save_state(state)
    elif not args.dry_run:
        save_state(state)
    # exit 1 only when nothing could be fetched at all; partial failures are reported, not fatal
    return 1 if report.errors and not report.counts else 0


if __name__ == "__main__":
    sys.exit(main())
