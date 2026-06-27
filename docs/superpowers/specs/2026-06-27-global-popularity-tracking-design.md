# Global popularity tracking (Last.fm + ListenBrainz) — Design

> Date: 2026-06-27
> Status: Approved design, pending implementation plan.

Restore a meaningful **global-popularity** signal for every track after Spotify
removed `track.popularity` (Feb 2026), so the dashboard's "Underrated" sort works
again. Source the signal from Last.fm (primary) with a ListenBrainz fallback,
cache it per-track, and keep it current via a batch CLI wired into the bi-daily
run.

---

## Background / problem

The "Underrated" score is `play_count / popularity` — personal plays over a
**global** popularity number. Spotify removed `track.popularity`, so:

- `logger.py:151` now writes `popularity=None`.
- `dashboard_server.py` still calls `sp.tracks()` to fetch popularity, which no
  longer returns a usable value, then defaults to `50`.
- With every track at the `50` default, "Underrated" collapses into "Most
  played" — redundant with the Plays sort.

We need an **external** global-popularity proxy to refill the denominator.

### Why Last.fm primary, ListenBrainz fallback (decided)

- **Sample size:** Last.fm's userbase (tens of millions, since 2002) gives far
  more statistically stable `listeners` counts than ListenBrainz's niche
  audience. For "how mainstream is this track," Last.fm's larger, more mainstream
  crowd is the better mirror of the general public.
- **Fewer failure points:** Last.fm is one hop (`artist+title → track.getInfo →
  listeners`). ListenBrainz needs two (metadata lookup → MBID → popularity API),
  and the MBID resolution is itself a miss point.
- **ListenBrainz's role:** its canonical-MBID matching is more *precise*, so it's
  a good fallback for the long tail Last.fm fuzzy-matches poorly or doesn't know.

The repo already has a Last.fm API key (`config.LASTFM_API_KEY`) and a stdlib
client pattern (`ingest/lastfm_client.py`); the user has a ListenBrainz token in
`.env` as `LISTENBRAINZ_TOKEN`.

---

## Current state (grounding)

- **Schema** (`db.py`): `plays.popularity INTEGER` (nullable); a separate
  `artist_genres` cache table keyed by `artist_key` with `genre_source` /
  `fetched_at` — the pattern this design mirrors for popularity.
- **Candidate aggregation** (`db.py:window_track_candidates`): groups canonical
  plays by `track_key = normalize(artist) + "\t" + normalize(title)`, joins
  `artist_genres` for the bucket, and currently carries `popularity` from the
  representative play row.
- **Dashboard** (`dashboard_server.py:135–186`): a block that collects uncached
  track IDs, calls `sp.tracks()` in chunks of 50, writes results back to
  `plays.popularity`, and defaults missing values to `50`. This block is now dead
  weight (Spotify field gone).
- **Enrichment pattern** (`ingest/enrich_cli.py`, `ingest/genres.py:enrich_all`):
  resumable, only processes rows missing from the cache, `--refresh` re-does
  them; `run_bidaily.py:run_pipeline` is where scheduled steps are wired.
- **Frontend** (`dashboard/src/lib/types.ts`): `underratedScore(c) = c.play_count
  / (c.popularity || 1)`. No frontend change needed.

---

## Design

### 1. Storage — new `track_popularity` cache table

Add to `db.py` (created in `migrate`), mirroring `artist_genres` but keyed
per-track:

```sql
CREATE TABLE IF NOT EXISTS track_popularity (
    track_key   TEXT PRIMARY KEY,   -- normalize(artist) + "\t" + normalize(title)
    listeners   INTEGER,            -- raw global listener count (audit/debug)
    popularity  INTEGER,            -- normalized 0–100 (what the score reads)
    source      TEXT NOT NULL,      -- 'lastfm' | 'listenbrainz' | 'none'
    fetched_at  TEXT
);
```

- Keyed on `track_key` (not Spotify's dead `track_id`) so it survives the API
  change and joins cleanly to candidates.
- **Decouples from `plays`:** we stop relying on `plays.popularity`.
  `window_track_candidates` joins `track_popularity` by `track_key` (exactly as
  it already joins `artist_genres`) and sets each candidate's `popularity` from
  the cache, falling back to `None` when absent (the dashboard then defaults to
  50 — see §5).
- New `db.py` helpers: `get_track_popularity(conn, track_key)`,
  `upsert_track_popularity(conn, track_key, listeners, popularity, source)`,
  and `track_keys_missing_popularity(conn)` (canonical track_keys with no
  `track_popularity` row) for the resumable CLI.

`plays.popularity` is left in place (no destructive migration) but is no longer
read for the underrated score. `logger.py` may keep writing `None` there
harmlessly.

### 2. Normalization — raw listeners → 0–100

In the new `ingest/popularity.py`:

```python
import math

POPULARITY_CEIL = 5_000_000  # ~ a megahit's Last.fm listener count

def normalize_listeners(listeners: int) -> int:
    """Log-scale a raw listener count into a 0–100 popularity score."""
    if not listeners or listeners < 0:
        return 0
    score = 100 * math.log10(listeners + 1) / math.log10(POPULARITY_CEIL + 1)
    return max(0, min(100, round(score)))
```

Linear mapping is useless on counts that span hundreds → millions; log scale
gives ~300 listeners → ~30, ~5M → ~100. Keeps the existing 0–100 range so the
`play_count / popularity` ratio and the "default 50" behavior stay intact.

### 3. Fetch + fallback — `ingest/popularity.py`

```python
def fetch_lastfm_listeners(artist, title, api_key, fetch=None) -> int | None:
    """Last.fm track.getInfo -> global listener count, or None on miss/error."""

def fetch_listenbrainz_listeners(artist, title, token, fetch=None) -> int | None:
    """ListenBrainz fallback: metadata lookup (artist+title -> MBID) then the
    popularity API (MBID -> global listen count). None on miss/error."""

def resolve_popularity(artist, title, *, lastfm_api_key, listenbrainz_token,
                       fetch=None) -> dict:
    """Try Last.fm, then ListenBrainz. Returns
    {listeners, popularity, source} where source is
    'lastfm' | 'listenbrainz' | 'none'."""
```

- **Primary (Last.fm):** `method=track.getInfo&artist=&track=&api_key=&format=json`
  → `track.listeners` (string int). Reuses `webutil.fetch_text`; wrap network in
  try/except so a miss returns `None` rather than raising.
- **Fallback (ListenBrainz), only when Last.fm returns `None`:**
  1. metadata lookup: `GET https://api.listenbrainz.org/1/metadata/lookup/?artist_name=<a>&recording_name=<t>`
     → `recording_mbid`.
  2. popularity: `POST https://api.listenbrainz.org/1/popularity/recording`
     with `{"recording_mbids": [mbid]}` → per-mbid `total_listen_count` /
     `total_user_count`; use the listener (`total_user_count`) figure.
  - Auth header `Authorization: Token <LISTENBRAINZ_TOKEN>`.
  - **The exact endpoint paths, query params, and JSON field names above are from
    training memory and MUST be verified against live ListenBrainz docs during
    implementation** (Task notes will include a curl check before wiring).
- **No match anywhere:** `{listeners: None, popularity: None, source: 'none'}`.

**Product decision — unmatched = neutral, not obscure.** At read time an
unmatched/`'none'` track resolves to popularity **50** (neutral), *not* a tiny
"super-underrated" value. A no-match is usually a data gap, so treating it as
maximal obscurity would flood the Underrated sort with false positives. A track
that *is* matched but genuinely tiny (e.g. 200 listeners → ~25) still surfaces
correctly. The two-source fallback minimizes how many tracks land in `'none'`.

### 4. Enrichment trigger — `ingest/enrich_popularity.py` CLI

Mirrors `ingest/enrich_cli.py`:

- `enrich_all_popularity(conn, *, lastfm_api_key, listenbrainz_token, fetch=None,
  sleep=None, progress=None, refresh=False) -> dict` — iterates
  `track_keys_missing_popularity(conn)` (or *all* canonical track_keys when
  `refresh=True`), calls `resolve_popularity`, upserts each result, sleeps
  politely between calls, and is **resumable** (only missing rows by default, so
  re-running after an interruption continues). Returns a summary dict
  `{lastfm, listenbrainz, none, processed}`.
- A `main()` with an argparse `--refresh` flag and logging, like `enrich_cli`.
- Run manually: `python -m ingest.enrich_popularity`.

`run_bidaily.py:run_pipeline` gains a step (after ingest, before slideshow build)
that calls `enrich_all_popularity` inside a `with db.connect()` block, guarded so
a popularity failure logs a warning but never blocks slide generation. A
`--skip-popularity` flag is added for parity with the existing skip flags.

### 5. Dashboard wiring — `dashboard_server.py`

- **Delete** the dead Spotify popularity block (collect uncached IDs → `sp.tracks()`
  → write back to `plays`).
- Instead, after building candidates, decorate each with
  `get_track_popularity(conn, track_key)`; when absent or `source='none'`, use
  **50**. (If `window_track_candidates` already joins the cache per §1, this is
  just the NULL→50 default applied where popularity is consumed.)
- Net effect: no live Spotify call on dashboard load (faster) and a real
  underrated signal.

No frontend change: `underratedScore` and the Underrated sort start receiving
meaningful numbers automatically.

### 6. Config

`config.py`: add `LISTENBRAINZ_TOKEN = os.getenv("LISTENBRAINZ_TOKEN")`. No new
required-credential assertion (popularity degrades gracefully to neutral-50 when
unavailable).

---

## Testing

Mirror `tests/test_genres.py` fakes (inject `fetch` returning canned JSON
strings; no real network):

- `normalize_listeners`: 0 → 0, 300 → ~30, 5M → ~100, negatives/None → 0, clamps.
- `fetch_lastfm_listeners`: parses `track.listeners`; returns `None` on Last.fm
  `error` payload or malformed JSON.
- `fetch_listenbrainz_listeners`: parses the metadata-lookup → popularity chain;
  `None` when no MBID match.
- `resolve_popularity`: Last.fm hit → `source='lastfm'`; Last.fm miss + LB hit →
  `source='listenbrainz'`; both miss → `source='none'`.
- DB: `upsert_track_popularity` then `get_track_popularity` round-trips;
  `track_keys_missing_popularity` excludes cached keys.
- `enrich_all_popularity`: resumable (skips cached), `--refresh` reprocesses,
  summary counts correct.
- Dashboard read: an unmatched/`'none'` track surfaces as popularity 50 (extend
  the existing `tests/test_dashboard_server.py` default-50 assertion).

---

## Scope / YAGNI

- **In:** the cache table, normalization, two-source fetch, batch CLI, bi-daily
  wiring, dashboard read-path swap, config, tests.
- **Out:** auto-staleness/TTL re-fetching (popularity drifts slowly; `--refresh`
  is enough), exposing raw listener counts in the UI, blending both sources
  (Last.fm primary + LB fallback is the decided strategy), any frontend change
  beyond what already reads `popularity`.
