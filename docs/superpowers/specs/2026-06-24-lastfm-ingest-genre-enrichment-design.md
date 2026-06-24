# Last.fm Ingest + Genre Enrichment — Design Spec

**Date:** 2026-06-24
**Phase:** 3, Sub-project A (Data foundation)
**Status:** Approved design, pending implementation plan

---

## 1. Purpose

Load the full Last.fm scrobble history into SQLite and enrich every artist with a
genre **bucket**, so later selection logic (Sub-project B) can pull tracks "across
different genres". When done, the database is independently useful: you can query
your listening by genre and (deduplicated) play count.

---

## 2. Scope

### In scope (Sub-project A)
- Stream-import the Last.fm export XML into the `plays` table (`source='lastfm'`).
- Schema migration: add `source` + `played_at_unix` to `plays`; new `artist_genres`
  table; backfill existing logger rows.
- Cross-source canonical dedup helper (`canonical_plays`).
- Genre enrichment per unique artist: Spotify primary → Last.fm fallback → unknown,
  mapped to a curated hybrid bucket set, cached in `artist_genres`.
- A CLI (`ingest.enrich_cli`) that runs migration + import + enrichment and prints a
  summary.

### Out of scope (deferred)
- Track **selection**, bi-daily window, slideshow assembly → **Sub-project B**.
- Pulling from the Last.fm **API incrementally** (replacing the logger) → later
  enhancement. For now the Phase 1 Spotify logger remains the live feed; the export
  is the one-time historical load.
- Manual genre-mapping correction UI → later (mismatches are auditable via stored
  raw genres).

### Decisions locked during brainstorming
- **Source of truth: BOTH sources, deduplicated.** Last.fm scrobbles the same plays
  the Spotify logger captures; we keep both raw and dedup when counting.
- **Genre source: Spotify primary, Last.fm top-tags fallback.** Credentials for both
  are in `.env` (`SPOTIPY_*`, `LAST_FM_API_KEY`, `LAST_FM_SHARED_SECRET`). Spotify
  Phase 0 auth is done.
- **Genre granularity: hybrid** — rap subgenres + broad buckets.

---

## 3. Data inputs

Last.fm export (`data/scrobbles-*.xml`, verified 2026-06-24): 107,890 timestamped
scrobbles (+540 `nowplaying`), 2020-08 → 2026-06, 15,470 unique tracks, 3,809 unique
artists, album art ≤300×300, ~6,151 placeholder-art scrobbles. Per `<track>`: artist
(+MBID), name (+MBID), album (+MBID), `image` sizes (use `extralarge`), `date uts`.
No genre, no duration, no popularity.

---

## 4. Architecture & module boundaries

```
ingest/
├── __init__.py
├── lastfm_import.py   # stream-parse export XML -> plays rows (source='lastfm')
├── lastfm_client.py   # Last.fm API wrapper (artist.getTopTags) for genre fallback
├── genre_map.py       # curated micro-genre -> hybrid bucket mapping (pure data + lookup)
├── genres.py          # enrich each unique artist: Spotify primary -> Last.fm fallback
└── enrich_cli.py      # CLI: migrate + import + enrich, print summary
db.py                  # EXTENDED: source/played_at_unix, migration, canonical_plays, artist_genres
config.py              # EXTENDED: LASTFM_API_KEY/SECRET, LASTFM_EXPORT_PATH
text_norm.py           # shared artist/title normalization helper
```

**Principles:**
- `lastfm_import` only parses → inserts. `genres` only resolves/caches genres.
  `genre_map` is pure data + a lookup function. `db` owns all SQL.
- `genres` depends on a Spotify client and a Last.fm client passed in (injectable),
  keeping it offline-testable.
- Normalization is one shared helper (`text_norm.normalize`) used by both import-time
  dedup and genre matching, so the rules can't drift.

---

## 5. Schema changes

All additive, applied by an idempotent `migrate()` in `db.py`.

### `plays` (extended)
- Add `source TEXT NOT NULL DEFAULT 'spotify'`.
- Add `played_at_unix INTEGER` — epoch seconds, comparable across sources.
- `track_id` may be empty (`''`) for Last.fm rows (Last.fm has no Spotify id; track
  MBID stored if present, else `''`).
- Within-source dedup: `UNIQUE(source, artist, track_id, name, played_at)`.
- Backfill: existing rows get `source='spotify'` and `played_at_unix` computed from
  the ISO `played_at`. Running `migrate()` repeatedly is a no-op.

> SQLite cannot add a column inside an existing `UNIQUE(...)` table constraint via
> `ALTER`. The migration detects the old schema and, if present, rebuilds `plays`
> (create new table with the target schema → copy rows with backfill → swap). On a
> fresh DB it simply creates the target schema directly. Either path is idempotent.

### `artist_genres` (new)
Keyed by **normalized artist name** — the authoritative genre/bucket source for
selection. The Phase 1 logger's existing `artists` cache is left untouched.

```
artist_genres(
  artist_key        TEXT PRIMARY KEY,   -- normalized artist name
  display_name      TEXT,
  spotify_artist_id TEXT,               -- matched Spotify id (audit), '' if none
  raw_genres        TEXT,               -- comma-joined Spotify genres (audit)
  lastfm_tags       TEXT,               -- comma-joined Last.fm tags used (audit)
  primary_bucket    TEXT NOT NULL,      -- one of the hybrid buckets
  genre_source      TEXT NOT NULL,      -- 'spotify' | 'lastfm' | 'none'
  fetched_at        TEXT
)
```

---

## 6. Import & dedup

### Import (`lastfm_import.py`)
- `iterparse` the XML (constant memory).
- Skip `nowplaying="true"` and any entry missing `date uts`.
- Map each `<track>` → a `plays` row: `source='lastfm'`, `track_id` = track MBID or
  `''`, `name`, `artist`, `album_art_url` = `extralarge` URL (or `''` if the Last.fm
  placeholder hash is present), `played_at` = ISO-8601 UTC from `uts`,
  `played_at_unix` = `uts`.
- `INSERT OR IGNORE` (idempotent within-source). Track a skipped tally.

### Cross-source canonical dedup (`db.canonical_plays(window_seconds=120)`)
- Load all plays ordered by `played_at_unix`.
- Two plays are the same listen iff: **different sources**, equal
  `normalize(artist)` and `normalize(title)`, and `|Δ played_at_unix| ≤ window`.
- On a match, keep one row, **preferring the Spotify row** (richer metadata); drop the
  Last.fm twin. Same-source repeats are preserved (genuine replays).
- Returns canonical rows. Default window 120s (Last.fm scrobble time lags Spotify
  `played_at`). The window is a parameter.

### Normalization (`text_norm.normalize`)
Lowercase, strip, collapse internal whitespace, and conservatively trim trailing
remaster/version noise (e.g. `" - 2011 remaster"`). Deliberately conservative to
avoid merging genuinely different songs.

---

## 7. Genre enrichment

### Buckets (`genre_map.py`)
Hybrid set:
- Rap subgenres: `rage`, `trap`, `drill`, `plugg`, `boom-bap`, `melodic-rap`
- Broad: `pop`, `r&b`, `rock`, `electronic`, `indie`, `country`, `latin`, `other`,
  `unknown`

`genre_map.py` holds a curated dict `{micro_genre: bucket}` (seeded to cover the top
~50 artists' Spotify genres) and:

`bucket_for(genres: list[str]) -> str`
- Returns the bucket of the **first** genre in the list that maps to a known bucket
  (Spotify orders an artist's genres roughly by relevance).
- `'other'` if the list is non-empty but nothing maps; `'unknown'` if empty.

### Resolution flow (`genres.py`), per unique artist
1. **Spotify primary:** `search(q=artist, type='artist', limit=1)`; accept the top hit
   only if `normalize(hit.name) == normalize(artist)`; take its `genres`. If non-empty
   → `bucket_for(genres)`, `genre_source='spotify'`.
2. **Last.fm fallback** (no match / empty genres): `artist.getTopTags`; keep tags above
   a weight threshold; `bucket_for(tags)`; `genre_source='lastfm'`.
3. **Neither:** `primary_bucket='unknown'`, `genre_source='none'`.
4. Cache full record in `artist_genres`. **Resumable:** already-cached artists are
   skipped, so the ~3,800-artist batch survives interruption and re-runs cheaply.

Unique artists are drawn from `plays` (both sources), normalized via `text_norm`.
Spotify volume is fine; Last.fm calls get a small delay (politeness).

---

## 8. Error handling

| Case | Behavior |
|------|----------|
| Malformed/missing fields in an XML `<track>` | Skip, increment skipped tally, continue. |
| `nowplaying` / missing `uts` | Skipped by design. |
| Placeholder album art (Last.fm default hash) | Store `''` → renderer fallback later. |
| Spotify search miss / API error | Fall through to Last.fm; transient error leaves artist un-enriched for the next resumable run; never aborts the batch. |
| Last.fm API error / missing `LAST_FM_API_KEY` | Caught; artist → `unknown`; clear message if the key is absent. |
| Re-run import or enrichment | Idempotent (INSERT OR IGNORE; cached artists skipped). |
| Migration on existing logger rows | Backfills `source`/`played_at_unix`; safe to run repeatedly. |

---

## 9. Testing (pytest, offline — network injected/mocked)

- `genre_map`: `bucket_for` first-match wins; known micro-genres map; `'other'` when
  non-empty-but-unmapped; `'unknown'` when empty.
- `text_norm`: case/whitespace/remaster trimming; does not merge distinct titles.
- `lastfm_import`: inline XML fixture → correct row count; `nowplaying` skipped; fields
  + `played_at_unix` mapped; malformed entry skipped; re-import adds nothing.
- `canonical_plays`: cross-source pair within window → one row (Spotify kept); outside
  window → two rows; same-source repeat preserved; different songs same second → both.
- `genres`: fake Spotify client with genres → `spotify` + correct bucket; empty Spotify
  → Last.fm fallback; both empty → `unknown`; name-mismatch guard rejects wrong hit.
- `db.migrate`: old-shape row backfilled with `source`/`played_at_unix`; second run is
  a no-op.

**Manual gate:** run the CLI against the real export and eyeball the summary (counts,
bucket distribution) for sanity.

---

## 10. CLI deliverable

`python -m ingest.enrich_cli`:
1. `db.migrate()`.
2. Import the Last.fm export (path from `config.LASTFM_EXPORT_PATH` / `.env`, default
   newest `data/scrobbles-*.xml`).
3. Enrich all not-yet-cached artists.
4. Print summary: scrobbles imported/skipped, artists enriched by source
   (spotify/lastfm/none), bucket distribution, total canonical plays.

---

## 11. Dependencies

- No new runtime deps strictly required: Last.fm API calls use stdlib `urllib`
  (consistent with `render/art.py`); Spotify uses existing `spotipy`; XML via stdlib
  `xml.etree`. (A thin Last.fm client wrapper is our own code.)
- New `.env` keys consumed: `LAST_FM_API_KEY`, `LAST_FM_SHARED_SECRET` (secret only
  needed if authenticated calls are added later; `getTopTags` needs just the API key),
  optional `LASTFM_EXPORT_PATH`.
