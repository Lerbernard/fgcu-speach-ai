"""
Ordinary web pages listed under `pages:` in sources.yaml.

mode auto  - rewrite the data file when the page's extracted text changes
mode watch - hand-edited file; only record the page hash and report a change
"""
import os

from common import (abs_path, page_to_markdown, read_text, write_text, sha,
                    now_iso, remove_part_files, shrink_check, same_page)

SOURCE = "pages"


def run(manifest, state, fetch, report, dry_run=False, limit=None):
    entries = manifest.get("pages", [])
    if limit:
        entries = entries[:limit]
    st_all = state.setdefault("pages", {})

    for entry in entries:
        url, rel, mode = entry["url"], entry["path"], entry.get("mode", "auto")
        st = st_all.setdefault(rel, {})
        st["url"] = url
        try:
            r = fetch.get(url, cond=st if st.get("hash") else None)
        except Exception as e:  # network error: keep the old file, say so
            report.error(SOURCE, f"{rel}: {type(e).__name__}: {e}")
            continue

        if r.status_code == 304:
            st["last_checked"] = now_iso()
            report.unchanged(SOURCE)
            continue
        if r.status_code != 200:
            report.error(SOURCE, f"{rel}: HTTP {r.status_code} for {url}")
            st["last_status"] = r.status_code
            continue

        md = page_to_markdown(r.text, url)
        new_hash = sha(md)
        st.update(last_checked=now_iso(), last_status=200,
                  etag=r.headers.get("ETag"), last_modified=r.headers.get("Last-Modified"))
        if not same_page(r.url, url) and st.get("final_url") != r.url:
            report.warn(SOURCE, f"{rel}: {url} now redirects to {r.url}")
        st["final_url"] = r.url

        if mode == "watch":
            if st.get("hash") and st["hash"] != new_hash:
                report.watch_changed(rel, url, st.get("last_changed"))
                st["last_changed"] = now_iso()
            else:
                # first sighting is the baseline; nothing to compare against yet
                st.setdefault("last_changed", now_iso())
                report.unchanged(SOURCE)
            st["hash"] = new_hash
            continue

        path = abs_path(rel)
        old = read_text(path)
        if old is not None and sha(old) == new_hash:
            st["hash"] = new_hash
            report.unchanged(SOURCE)
            continue

        # A page that genuinely got shorter trips the guard every run until
        # someone confirms it with `allow_shrink: true` on the manifest entry.
        ok, why = shrink_check(old, md)
        if not ok and not entry.get("allow_shrink"):
            report.warn(SOURCE, f"{rel}: NOT replaced, {why} (set allow_shrink: true in sources.yaml if the page really shrank)")
            continue

        if not dry_run:
            write_text(path, md)
            for fn in remove_part_files(path):
                report.removed(SOURCE, f"{os.path.dirname(rel)}/{fn} (merged into {os.path.basename(rel)})")
        st["hash"] = new_hash
        st["last_changed"] = now_iso()
        report.written(SOURCE, rel, "updated" if old is not None else "new")
