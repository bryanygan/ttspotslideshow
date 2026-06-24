# Slideshow Selection + Assembly — Design Spec

**Date:** 2026-06-24
**Phase:** 3, Sub-project B (Slideshow generation)
**Status:** Approved design, pending implementation plan

---

## 1. Purpose

Turn the enriched listening database (Sub-project A) into a dated folder of
ready-to-post TikTok slides: pick the recent, genre-varied tracks the user has
been listening to, and render them through the Phase 2 card/collage engine.

When done, `python -m slideshow.cli` produces `output/slides/<date>/slide_N.png`.

---

## 2. Scope

### In scope (Sub-project B)
- Resolve a candidate track pool from a recent time window, with auto-widening.
- Round-robin genre selection → an ordered track list.
- Hi-res album art resolution (iTunes Search API, Last.fm fallback).
- Slide assembly via the existing renderer → dated output folder.
- CLI entry point + run summary.

### Out of scope
- TikTok posting — manual by design (Content Posting API needs business approval).
- Task Scheduler automation — Phase 4, a thin wrapper over this CLI (later).
- Weekly recap dashboard — Phase 5.

### Decisions locked during brainstorming
- **Window:** last 2 days, auto-widen (2→4→7→14→30) if too thin.
- **Selection:** genre round-robin; within a bucket, a composite score blends
  play count (0.6) + recency (0.4), multiplied by a novelty factor that suppresses
  recently-featured tracks (14-day recovery). Requires a `featured_tracks` table.
- **Album art:** iTunes hi-res (600×600), fall back to stored Last.fm 300px.
- **Count:** target 16 (4 slides), floor 12 (3 slides); only whole 4-card slides.

---

## 3. Inputs (from Sub-project A + Phase 2)

- `db.canonical_plays(conn, window_seconds)` — cross-source deduped plays.
- `plays` rows: `name, artist, album_art_url, track_id, played_at_unix, source`.
- `artist_genres` table: `artist_key` (normalized name) → `primary_bucket`.
- `text_norm.normalize` — shared normalization.
- `render.art.load_art`, `render.card.render_card`, `render.collage.collage`.

---

## 4. Architecture & module boundaries

```
slideshow/
├── __init__.py
├── window.py       # candidate aggregation + auto-widen
├── selector.py     # round-robin genre selection (pure function)
├── art_resolve.py  # iTunes hi-res lookup + Last.fm fallback (injectable fetch)
├── builder.py      # orchestrate select -> art -> render -> collage -> files
└── cli.py          # python -m slideshow.cli (bi-daily entry point)
db.py               # ADD: window_track_candidates + featured_tracks table
                    #      + record_featured / featured_history
```

**Boundaries:**
- `selector` is a pure function (candidate list → ordered selection), no I/O.
- `window` owns the auto-widen loop and the DB aggregation query.
- `art_resolve` is the only networked unit besides art download; fetch injectable.
- `builder` is the only unit touching the renderer + filesystem.
- `cli` wires the real connection + output path and prints the summary.

---

## 5. Window resolution (`window.py` + `db.window_track_candidates`)

### Candidate aggregation
`db.window_track_candidates(conn, start_unix) -> list[dict]`:
- Source rows from `canonical_plays(conn)` filtered to `played_at_unix >= start_unix`.
- Aggregate into **unique tracks** keyed by `(normalize(artist), normalize(title))`:
  - `track_key` = `normalize(artist) + '\t' + normalize(title)` (matches the
    `featured_tracks` key, so selection/recording line up).
  - `play_count` = number of canonical plays in the window.
  - representative `track_id`, `title`, `artist`, `album_art_url` from the
    **most recent** play in the group.
  - `last_played_unix` = max `played_at_unix` in the group (for tiebreaks).
  - `primary_bucket` = `artist_genres.primary_bucket` joined on
    `normalize(artist)`, default `'unknown'`.

### Auto-widen
`resolve_window(conn, target=16, floor=12, steps=(2,4,7,14,30), now_unix=None) -> tuple[list[dict], int]`:
- For each `days` in `steps`: compute `start_unix = now_unix - days*86400`, get
  candidates. Stop at the first window with `len(candidates) >= target`.
- If none reaches `target`, keep the **largest** candidate set produced (the last
  step, 30 days). Return `(candidates, days_used)`.
- `now_unix` defaults to current time; injectable for tests.

---

## 6. Selection (`selector.py`)

Selection blends three signals — play count, recency, and novelty (not recently
featured) — within a genre round-robin. A `featured` history map is passed in so
the selector stays a pure function.

### Featured history (`featured_tracks` table)
New table, written by the builder after each run. **Date-based** (the post cadence
is daily), which keeps same-day re-runs deterministic:
```
featured_tracks(
  track_key          TEXT PRIMARY KEY,  -- normalize(artist)+'\t'+normalize(title)
  last_featured_date TEXT NOT NULL,     -- 'YYYY-MM-DD'
  times_featured     INTEGER NOT NULL
)
```
`db.featured_history(conn) -> dict[str, str]` returns `{track_key: last_featured_date}`.
`db.record_featured(conn, track_keys, run_date)` upserts each selected track
(set `last_featured_date=run_date`, increment `times_featured`).

### Composite score
`select_tracks(candidates, featured, run_date, target=16, floor=12) -> list[dict]`:

For each candidate compute:
```
base    = 0.6 * norm(play_count) + 0.4 * norm(recency)
score   = base * novelty
```
- `norm(play_count)` = `play_count / max(play_count over all candidates)` (0–1).
- `norm(recency)` = `(last_played_unix - min_last) / (max_last - min_last)` over all
  candidates (newer → higher; if all equal → 1.0). Relative to the candidate set,
  so the selector needs no "now".
- `novelty`: let `days = (run_date - last_featured_date).days`.
  `1.0` if the track is not in `featured` **or `days <= 0`** (featured *today* — not
  suppressed, so a same-day re-run reproduces the same picks); otherwise
  `min(1.0, days / 14)` — a track featured on a prior day recovers from ~0.07 (next
  day) back to 1.0 over 14 days.

Weights `0.6 / 0.4`, the 14-day recovery, and `target/floor` are module-level
constants (easy to tune after seeing real output).

### Ordering
1. Group candidates by `primary_bucket`; within each bucket sort by `score` desc,
   then `last_played_unix` desc, then `title` asc (fully deterministic).
2. Order buckets by total in-window `play_count` desc (tiebreak: bucket name asc).
3. **Round-robin:** traverse the bucket order, taking the next-highest-scoring
   unused track from each bucket per pass, until `target` reached or candidates
   exhausted. Interleaving genres means each 4-card slide tends to show 4
   different genres.
4. **Count resolution:** let `n = len(picked)`. Final count = `16` if `n >= 16`;
   else the largest multiple of 4 that is `>= floor` and `<= n` (i.e. `12` when
   `12 <= n < 16`); else the largest multiple of 4 `<= n` (`8` or `4`); if `n < 4`,
   return all `n` (builder reports it can't fill a slide). Truncate to the final
   count.
5. Return the ordered list (selection order = slide order). Each item carries
   `track_key`, `track_id`, `title`, `artist`, `album_art_url`, `primary_bucket`.

Determinism: with a fixed `featured` map and `run_date`, every sort has an
explicit tiebreak, so identical inputs → identical ordered selection.

---

## 7. Album art resolution (`art_resolve.py`)

`resolve_art_url(track, fetch=None) -> str`:
- Query iTunes Search API:
  `https://itunes.apple.com/search?term=<artist title>&entity=song&limit=1`
  (URL-encoded). Parse JSON; take `results[0].artworkUrl100`; rewrite the size
  segment `100x100` → `600x600` for hi-res.
- **Fallback chain:** no result / parse error / network error → the track's
  stored Last.fm `album_art_url` → `''` (empty → renderer fallback card).
- `fetch(url) -> str` injectable (default stdlib `urllib`). Within a run, results
  are memoized per `(normalize(artist), normalize(title))`.

---

## 8. Build pipeline (`builder.py`) & output

`build_slideshow(conn, out_root, target=16, floor=12, now_unix=None, today=None, fetch=None, cache_dir=None) -> dict`:
1. `candidates, days_used = window.resolve_window(conn, target, floor, now_unix=now_unix)`.
2. `featured = db.featured_history(conn)`; `run_date = today or date.today().isoformat()`;
   `tracks = selector.select_tracks(candidates, featured, run_date, target, floor)`.
3. For each track: `url = art_resolve.resolve_art_url(track, fetch=fetch)` →
   `path = render.art.load_art(url, cache_dir)` →
   `card = render.card.render_card(track, art_path=path)`.
4. Chunk cards into groups of 4; each group → `render.collage.collage(group)` →
   save `out_root/<today>/slide_<n>.png`. Only whole groups of 4 are rendered.
5. `db.record_featured(conn, [t["track_key"] for t in rendered_tracks], run_date)`
   — only the tracks actually rendered onto slides are recorded.
6. Return summary: `{date, days_used, track_count, slide_count, genre_spread, out_dir}`
   where `genre_spread` is `{bucket: count}` over the selected tracks.

### Output layout
```
output/slides/2026-06-24/
  slide_1.png  slide_2.png  slide_3.png  slide_4.png   (1080×1920 each)
```
Album art caches under `data/album_art/` (shared with the renderer), so re-runs
are fast and offline.

### CLI (`cli.py`)
`python -m slideshow.cli`:
- Opens a real DB connection, builds into `output/slides/<today>/`.
- Prints the summary (window days used, track count, slides written, genre
  spread, output path). If no plays exist at all, prints a clear message and
  exits without writing.

---

## 9. Error handling

| Case | Behavior |
|------|----------|
| Thin window | Auto-widen 2→4→7→14→30; below floor at 30d → render largest whole-slide set (≥4); summary notes `days_used` and the short count. |
| iTunes error / no match | Fall back to Last.fm 300px URL, then `''` → renderer fallback card. |
| Art download fails | `render.art.load_art` returns `None` → renderer fallback card (Phase 2 behavior). |
| Track with no genre | Lands in `unknown` bucket; selectable, not prioritized. |
| Empty DB / no plays | Clear message; exit without writing slides. |
| Fewer than 4 selectable tracks | No full slide possible; builder writes nothing and the summary says so. |
| Re-run same day | Deterministic: novelty treats "featured today" (`days <= 0`) as un-suppressed, so the same picks reproduce and the folder is overwritten with identical slides. (Re-recording bumps `times_featured`; harmless.) |

---

## 10. Testing (pytest, offline — iTunes/art fetch injected)

- `selector`: round-robin interleaves genres (first slide draws 4 distinct
  buckets when available); composite score blends play count + recency + novelty
  (a recently-featured track is suppressed vs. an un-featured peer; recency lifts
  a newer-played track); 14-day novelty recovery; deterministic tiebreaks;
  target/floor/sub-floor count resolution; identical output on repeat inputs.
- `db.featured_history` / `record_featured`: recording selected keys then reading
  back gives correct `last_featured_unix`/`times_featured`; re-recording
  increments the count.
- `window` / `db.window_track_candidates`: aggregation counts plays per unique
  track and joins the correct bucket; auto-widen steps out only when below target
  and stops at the first sufficient window.
- `art_resolve`: iTunes JSON → `600x600` rewrite; no-match → Last.fm fallback;
  error → fallback; memoization; injected fetch (no network).
- `builder`: end-to-end on an in-memory DB with a fake fetch → writes the right
  number of 1080×1920 PNGs, chunked into 4s, in a dated folder.

**Manual gate:** run `python -m slideshow.cli` against the real DB and eyeball
the produced slides for selection quality + visual polish.

---

## 11. Dependencies

- No new runtime dependencies: iTunes via stdlib `urllib`/`json`; rendering via
  the existing `render` package; DB via stdlib `sqlite3`.
