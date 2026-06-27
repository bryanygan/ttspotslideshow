# Cover grid slider + custom song lookup — Design

> Date: 2026-06-27
> Status: Approved design, pending implementation plan.

Two independent dashboard features:

1. **Cover grid slider** — let the user tune the cover slide's album-cover grid
   density with a slider (instead of the current fixed buttons).
2. **Custom song lookup** — a search bar in the Browse tab that filters local
   tracks, searches Spotify on demand, and supports fully manual track entry.

These are unrelated and can be built in either order.

---

## Current state (after the latest pull)

The pulled changes already added most of the cover-grid plumbing and an
unrelated slide-dimensions/layout feature:

- `render/cover.py` — `render_cover_collage(..., columns, width, height)` builds
  a full-bleed mosaic of **square** album covers. `_build_mosaic` derives rows
  as `ceil(height / (width // columns))`, so covers always stay square and the
  grid fills the frame. Column count is the only knob that changes album-cover
  size.
- `slideshow/builder.py` — threads `cover_columns`, `width`, `height` through to
  the renderer.
- `dashboard_server.py` — `/api/generate` and `/api/generate-stream` read
  `cover_columns` (default 5) from the payload.
- `dashboard/src/lib/useRecap.ts` — `coverColumns` state (default 5) +
  `setCoverColumns`; sent as `cover_columns` in the generate payload. Also
  `slideWidth` / `slideHeight` with `lockAspectRatio`.
- `dashboard/src/ui/CoverControls.tsx` — exposes cover columns as a **button
  group limited to `[3, 4, 5, 6]`** ("Cover Grid Size (Columns)"). Slide
  dimensions are already real range sliders; a separate "Grid Layout"
  (2x2/3x3/4x4) controls the non-cover card slides.
- `dashboard/src/options/pocket/PocketDJ.tsx` — the Create-tab hero preview
  already renders `r.coverColumns` columns and uses
  `rows = ceil(cols * slideHeight / slideWidth)`.

**Browse search / custom lookup does not exist.** There is no `/api/search/*`
endpoint. Candidates come only from `GET /api/candidates` (the local DB window).

A Spotify-authenticated client is available server-side via
`spotify_client.get_client()`; `slideshow/playlist_parse.py` already shapes
Spotify tracks into candidate dicts through its `_candidate()` /
`_bucket_for()` helpers.

---

## Feature 1 — Cover grid slider

### Goal

Replace the fixed 4-button column picker with a continuous **range slider** so the
user can dial album-cover density on the cover slide, with a live readout of the
resulting grid (e.g. `5 × 9 — 45 covers`). Covers remain square and full-bleed;
rows stay auto-derived. No change to the non-cover card slides.

### Scope of change

Frontend-only. The renderer, builder, server, and `useRecap` plumbing already
accept `cover_columns` and need no change beyond a widened clamp range.

1. **`render/cover.py`** (optional, defensive): clamp `columns` to a sane range
   (`max(2, min(10, columns))`) inside `render_cover_collage` so an out-of-range
   value from any caller can't produce a degenerate mosaic. The default stays 5.

2. **`dashboard/src/ui/CoverControls.tsx`** — replace the
   `[3, 4, 5, 6].map(...)` button group with a range `<input type="range">`:
   - `min={3} max={8} step={1}` bound to `r.coverColumns` /
     `r.setCoverColumns`.
   - Style/markup mirrors the existing Width/Height sliders for consistency
     (same track/accent classes).
   - A readout line showing the live grid:
     `{cols} × {rows} — {cols * rows} covers`, where
     `rows = Math.ceil(cols * (r.slideHeight / r.slideWidth))`. This matches the
     renderer's row math and the preview's formula, so the label is accurate as
     the user also changes slide dimensions.

3. No other files change. The Create-tab preview already reflects
   `coverColumns`.

### Range rationale

3–8 columns keeps covers visually meaningful: at 1080px width, 3 cols ≈ 360px
tiles (large, ~3×6 grid) and 8 cols ≈ 135px tiles (dense, ~8×14 grid). Below 3
looks empty; above 8 the covers become unrecognizable thumbnails.

### Out of scope

- Independent row control / non-square covers (rejected during brainstorming —
  square + columns-driven was chosen).
- Touching the slide-dimension sliders or the 2x2/3x3/4x4 card layout (separate,
  already-shipped feature).

---

## Feature 2 — Custom song lookup in Browse

### Goal

A search bar at the top of the Browse tab that:

1. **Filters the local grid instantly** as the user types (client-side, by title
   or artist).
2. Offers an on-demand **"Search Spotify for 'X'"** button that runs a live
   Spotify track search and shows results to add.
3. Provides a **"Can't find it? Add manually"** form (title, artist, album art
   via upload or URL) for tracks on neither the local DB nor Spotify.

Added Spotify/manual tracks become normal selectable candidates that flow into
the existing picks → generate pipeline.

### Backend

**`slideshow/playlist_parse.py`** — add a search helper next to the existing
playlist parsers, reusing `_candidate()` / `_bucket_for()` / `_dedupe()`:

```python
def search_spotify_tracks(query: str, conn=None, limit: int = 20) -> list[dict]:
    """Search Spotify for tracks matching `query`, return candidate dicts.

    Each dict matches the playlist/OCR candidate shape plus a `popularity`
    field (Spotify returns it inline on search, so the dashboard's underrated
    score works without an extra /tracks call).
    """
```

- Calls `sp.search(q=query, type="track", limit=limit)`.
- For each track: build a candidate via `_candidate(...)`, then set
  `candidate["popularity"] = track.get("popularity", 50)`.
- Skips items missing a name or artist; dedupes by `track_key`.
- Raises `PlaylistParseError` (reused) on empty query or API failure.

**`dashboard_server.py`** — new route `POST /api/search/spotify`:

- Add `elif parsed.path == "/api/search/spotify": self.handle_post_spotify_search()`
  to `do_POST`.
- Handler reads `{"q": str}` from the JSON body, opens a DB connection (for
  genre buckets), calls `search_spotify_tracks(q, conn)`, and returns
  `{"tracks": [...]}`. Empty/whitespace `q` → `400` with an error message.
  Spotify/API errors → `500` with the error string, matching the existing
  playlist-parse handler's error shape.

### Frontend

**`dashboard/src/lib/api.ts`** — add:

```ts
export async function searchSpotify(
  apiBase: string,
  q: string,
): Promise<Candidate[]>   // POSTs { q } to /api/search/spotify, returns data.tracks
```

**`dashboard/src/lib/useRecap.ts`** — add to `RecapState` and the hook:

- `searchQuery: string`, `setSearchQuery(v)`.
- `spotifyResults: Candidate[]`, `searchLoading: boolean`, `searchError: string | null`.
- `runSpotifySearch(q)` — calls `searchSpotify`, stores results, manages
  loading/error.
- `clearSearch()` — resets query, results, error.
- `addSearchTrack(track)` — merges a Spotify result into `candidates` (if not
  already present by `track_key`) **and** into the selection, mirroring
  `addPlaylistTracksToSelection`. Fills grid-required defaults the search shape
  lacks: `play_count: 0`, `last_played_unix: 0`, `last_featured: null`,
  `recently_featured: false`, `times_featured: 0`. `popularity` comes from the
  search result.
- `addCustomTrack({ title, artist, albumArtUrl })` — builds a local candidate
  with a client-side `track_key` (`normalize(artist) + "\t" + normalize(title)`,
  reusing the same scheme the server uses), `track_id: ""`, `primary_bucket:
  "unknown"`, `popularity: 50`, and the same zeroed play/feature defaults; merges
  into `candidates` + selection. If `albumArtUrl` is provided it's stored
  directly; if the user uploaded a file, the existing `uploadArtFor` /
  `saveArtLinkFor` path handles persistence so generate can resolve it.

> Note: `track_key` normalization must match `text_norm.normalize` so a manual
> entry that later appears in the DB dedupes correctly. The plan will port the
> minimal normalize (lowercase + trim + collapse whitespace) to a shared TS
> helper or inline it to match.

**`dashboard/src/options/pocket/PocketDJ.tsx`** — Browse tab UI:

- **Search bar** in `BrowseHeader` (a text input with a clear "×" button), bound
  to `r.searchQuery`.
- `BrowseGrid` filters `sortedCandidates` client-side by `searchQuery`
  (case-insensitive substring on title or artist) before rendering.
- Below the grid, when `searchQuery` is non-empty:
  - A **"Search Spotify for '{query}'"** button → `r.runSpotifySearch(query)`.
  - A results section (loading skeletons / error banner / result rows). Each row
    shows art, title, artist, a "Spotify" badge, and an **Add** button →
    `r.addSearchTrack(track)` (button flips to "Added ✓" when its `track_key` is
    selected).
  - A **"Can't find it? Add manually"** disclosure → a small form (title,
    artist, album art upload-or-URL). Submit → `r.addCustomTrack(...)` then
    clears the form.

### Candidate default contract

The Browse grid reads `play_count`, `popularity`, `primary_bucket`,
`last_played_unix`, `recently_featured`, `times_featured`, `last_featured`.
Search results carry `popularity` + `primary_bucket`; manual entries carry
neither. Both `addSearchTrack` and `addCustomTrack` MUST populate every field
above with the defaults listed so the grid and sort comparators never read
`undefined`.

### Out of scope (YAGNI)

- Debounced search-as-you-type against Spotify (button-triggered only — matches
  the chosen "on demand" flow and limits API calls).
- Persisting custom tracks to the DB / logger (they live in client state for the
  current session; art uploads persist via the existing override store).
- Any new caching layer for search results.

---

## Security note

While in `slideshow/playlist_parse.py` for this work, an automated review flagged
`ssl._create_unverified_context()` disabling TLS verification on the
`open.spotify.com` embed scrape. Fixed in this branch: removed the unverified
context (Spotify serves a valid cert) and the now-unused `ssl` import.

---

## Testing

- **Feature 1:** existing `render/cover.py` mosaic tests still pass; add a render
  smoke test asserting a non-default `columns` (e.g. 8) produces the expected
  tile size / row count. Manual: slider readout matches generated cover.
- **Feature 2:** unit-test `search_spotify_tracks` with a fake Spotify client
  (mirroring `tests/test_genres.py` fakes) — asserts candidate shape, popularity
  passthrough, dedupe, and empty-query error. Manual: search a known track →
  add → it appears in picks and generates.
