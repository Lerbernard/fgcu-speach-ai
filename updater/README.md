# Data updater

Keeps `data/` in step with the FGCU website without re-scraping everything by
hand. It runs daily in GitHub Actions (`.github/workflows/update-data.yml`),
rewrites only files whose source changed, and opens a pull request with the
diff and a report. Merging that PR triggers `ingest.yml`, which pushes just the
changed files into Pinecone.

```
updater/
  sources.yaml        what to fetch and where each file comes from (the manifest)
  state.json          per-source hashes, ETags, last-seen terms (committed)
  update.py           entry point
  pages.py            ordinary web pages            -> data/pages/**
  faculty.py          directory profiles            -> data/pages/engineering_faculty/
  courses.py          Gulfline schedule search      -> data/courses/courses/**
  descriptions.py     catalog course descriptions   -> data/course_descriptions/**
  events.py           WCE events calendar           -> data/pages/.../events/wce-*.md
  calendar_dates.py   academic calendar page        -> data/academic_calendar/upcoming-dates.md
  common.py           HTTP, HTML->Markdown, safety checks
  build_manifest.py   one-time helper that produced sources.yaml
```

## Running it locally

```
pip install -r updater/requirements.txt
python updater/update.py --dry-run --limit 5        # fetch and compare, write nothing
python updater/update.py --only courses             # one source
python updater/update.py --report report.md         # everything, with a Markdown report
```

Then, from `backend/` with `PINECONE_API_KEY` / `PINECONE_INDEX_NAME` set:

```
python ingest_incremental.py --dry-run
python ingest_incremental.py
```

### Trying it against a test index first

The ingest never has to touch the live index. Point it at another index and
give it its own state file (`ingest_state.*.json` is gitignored):

```
PINECONE_INDEX_NAME=fgcu-eng-test python ingest_incremental.py --state ingest_state.test.json
```

The state file records which index it belongs to; a run against a different
index ignores it and starts clean, so test runs can't make a production run
skip files. To run the backend itself against the test index, set
`PINECONE_INDEX_NAME=fgcu-eng-test` in `backend/.env` before starting it.

## How change detection works

* **Pages** are converted to Markdown and hashed; a file is rewritten only when
  that hash differs from the file on disk. Hosts that send `ETag` /
  `Last-Modified` (the catalog) get conditional requests and usually answer 304.
* **Courses / descriptions / faculty / events** are regenerated from their
  structured source every run, but a file is only written when its content
  differs, so an unchanged source produces an empty diff.
* `mode: watch` entries in `sources.yaml` are hand-edited files (split catalog
  pages, advising write-ups, event summaries). They are never overwritten; the
  report lists them under "Needs a human" when their page changes.
* `manual:` lists files with no fetchable source (club blurbs from Eagle Link,
  RateMyProfessors reviews, the old calendar grid dump).

## Safety rules

* A page that comes back less than 40% the size of the current file is not
  written (error page, login wall, layout change) and is reported instead.
  If the page really did get shorter, add `allow_shrink: true` to its entry
  in `sources.yaml` for one run.
* Faculty files are only deleted when the list page parsed normally (30+
  profiles) and every profile fetch succeeded.
* Course files for a term are only pruned when that term returned sections;
  a term the form no longer offers is left untouched and reported.
* The academic calendar's per-term pages use query strings, which
  `www.fgcu.edu/robots.txt` disallows, so they are not fetched. The updater
  watches the list of term links and asks for a manual top-up of
  `academic_calendar/*.md` and `backend/academic_calendar.py` when a new term
  appears.

## Adding a page

Add an entry under `pages:` in `sources.yaml`:

```yaml
- url: https://www.fgcu.edu/eng/new-page/
  path: pages/engineering_main/www_fgcu_edu_eng_new-page.md
  mode: auto
```

The folder decides the `doc_type` ingest assigns (see `backend/chunking.py`),
so put the file where similar content already lives.
