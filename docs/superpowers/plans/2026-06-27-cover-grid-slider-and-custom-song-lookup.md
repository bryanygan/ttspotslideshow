# Cover Grid Slider + Custom Song Lookup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a slider to tune the cover slide's album-cover grid density, and a Browse-tab search bar that filters local tracks, searches Spotify on demand, and supports fully manual track entry.

**Architecture:** Feature 1 is a frontend swap (buttons → range slider) over already-shipped `cover_columns` plumbing, plus a defensive clamp in the renderer. Feature 2 adds a `search_spotify_tracks` helper + `/api/search/spotify` endpoint on the backend, an `searchSpotify` API call + search/manual-add state in `useRecap`, and search UI in the Browse tab. Added tracks become normal candidates flowing into the existing picks → generate pipeline.

**Tech Stack:** Python 3 (stdlib `http.server`, `spotipy`, `pytest`), React 19 + TypeScript + Tailwind 4 (Vite). Frontend has no JS test runner — verify with `npm run build` (tsc typecheck + vite build) and `npm run lint` (oxlint).

## Global Constraints

- Album covers on the cover slide are always **square** and the mosaic is **full-bleed**; rows are auto-derived (`ceil(height / (width // columns))`). Only column count changes cover size.
- Cover columns valid range: **3–8** (UI slider). Renderer clamps defensively to **2–10**. Default stays **5**.
- New candidate dicts MUST populate every field the Browse grid reads: `track_key`, `track_id`, `title`, `artist`, `album_art_url`, `play_count`, `last_played_unix`, `primary_bucket`, `popularity`, `last_featured`, `recently_featured`, `times_featured`.
- `track_key` scheme is `normalize(artist) + "\t" + normalize(title)` (tab-separated), matching `text_norm.normalize` (lowercase, trim, collapse whitespace).
- Server JSON helpers: `self._read_json_body()` (returns `None` on bad JSON), `self._send_json(status, obj)`. DB via `with db.connect() as conn:`.
- Run Python tests from the repo root with the venv: `python -m pytest <path> -v`.

---

### Task 1: Defensive column clamp in the cover renderer

**Files:**
- Modify: `render/cover.py` (function `render_cover_collage`, around line 112)
- Test: `tests/test_cover.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `render_cover_collage(art_paths, title, subtitle="", theme="purple", footer_text=None, columns=5, width=1080, height=1920)` now clamps `columns` to `[2, 10]` internally before building the mosaic.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cover.py`:

```python
from PIL import Image

from render import cover


def _solid(tmp_path, name, color):
    p = tmp_path / name
    Image.new("RGB", (64, 64), color).save(p)
    return str(p)


def test_columns_clamped_high(tmp_path):
    """An absurd column count is clamped so tiles never collapse to < width/10."""
    arts = [_solid(tmp_path, f"{i}.jpg", (i * 10 % 255, 0, 0)) for i in range(4)]
    img = cover.render_cover_collage(arts, "Hi", columns=999, width=1080, height=1920)
    assert img.size == (1080, 1920)
    # Clamp ceiling is 10 cols -> tile = 108px, so at least one full tile fits.
    assert 1080 // 10 == 108


def test_columns_clamped_low(tmp_path):
    """Zero/negative columns can't divide-by-zero; clamp floor is 2."""
    arts = [_solid(tmp_path, f"{i}.jpg", (0, i * 10 % 255, 0)) for i in range(4)]
    img = cover.render_cover_collage(arts, "Hi", columns=0, width=1080, height=1920)
    assert img.size == (1080, 1920)


def test_default_columns_render(tmp_path):
    arts = [_solid(tmp_path, f"{i}.jpg", (0, 0, i * 10 % 255)) for i in range(4)]
    img = cover.render_cover_collage(arts, "Title", subtitle="Sub", columns=5)
    assert img.size == (1080, 1920)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cover.py -v`
Expected: `test_columns_clamped_low` FAILS with `ZeroDivisionError` (current code does `width // columns` with `columns=0`). The other two may pass.

- [ ] **Step 3: Add the clamp**

In `render/cover.py`, inside `render_cover_collage`, immediately after the
`art_paths = [p for p in (art_paths or []) if p]` line (currently ~line 112),
add:

```python
    columns = max(2, min(10, int(columns)))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cover.py -v`
Expected: all three PASS.

- [ ] **Step 5: Commit**

```bash
git add render/cover.py tests/test_cover.py
git commit -m "feat: clamp cover collage columns defensively (2-10)"
```

---

### Task 2: Replace the cover-columns buttons with a slider

**Files:**
- Modify: `dashboard/src/ui/CoverControls.tsx:128-146` (the "Cover Grid Size (Columns)" block)

**Interfaces:**
- Consumes: `r.coverColumns: number`, `r.setCoverColumns(n: number)`, `r.slideWidth: number`, `r.slideHeight: number` (all already on `RecapState`).
- Produces: no new interface; UI only.

- [ ] **Step 1: Replace the button group with a range slider**

In `dashboard/src/ui/CoverControls.tsx`, replace this block (lines ~128–146):

```tsx
          <div className="flex flex-col gap-2">
            <span className={labelClass}>Cover Grid Size (Columns)</span>
            <div className="grid grid-cols-4 gap-2">
              {[3, 4, 5, 6].map((cols) => (
                <button
                  key={cols}
                  type="button"
                  onClick={() => r.setCoverColumns(cols)}
                  className={`rounded-lg border py-2 text-center text-xs font-semibold transition-all ${
                    r.coverColumns === cols
                      ? "border-violet-500 bg-violet-500/15 text-violet-200"
                      : "border-zinc-800 text-zinc-400 hover:border-zinc-600"
                  }`}
                >
                  {cols} Cols
                </button>
              ))}
            </div>
          </div>
```

with:

```tsx
          <div className="flex flex-col gap-2">
            <div className="flex items-baseline justify-between">
              <span className={labelClass}>Cover Grid Size</span>
              <span className="font-mono text-xs text-zinc-300">
                {r.coverColumns} × {Math.ceil(r.coverColumns * (r.slideHeight / r.slideWidth))}
                <span className="text-zinc-500">
                  {" "}— {r.coverColumns * Math.ceil(r.coverColumns * (r.slideHeight / r.slideWidth))} covers
                </span>
              </span>
            </div>
            <input
              type="range"
              min={3}
              max={8}
              step={1}
              value={r.coverColumns}
              onChange={(e) => r.setCoverColumns(parseInt(e.target.value))}
              className="w-full h-1 bg-zinc-800 rounded-lg appearance-none cursor-pointer accent-violet-500"
            />
            <div className="flex justify-between text-[10px] text-zinc-600">
              <span>3 (large)</span>
              <span>8 (dense)</span>
            </div>
          </div>
```

> The `rows` formula `ceil(cols * slideHeight / slideWidth)` matches
> `_build_mosaic`'s row math (`ceil(height / (width // columns))`) closely enough
> for a live label and stays correct as the user changes slide dimensions.

- [ ] **Step 2: Typecheck and build**

Run: `cd dashboard && npm run build`
Expected: builds with no TypeScript errors.

- [ ] **Step 3: Lint**

Run: `cd dashboard && npm run lint`
Expected: no new lint errors in `CoverControls.tsx`.

- [ ] **Step 4: Commit**

```bash
git add dashboard/src/ui/CoverControls.tsx
git commit -m "feat: cover grid columns as a 3-8 slider with live grid readout"
```

---

### Task 3: `search_spotify_tracks` backend helper

**Files:**
- Modify: `slideshow/playlist_parse.py` (add function after `parse_spotify_playlist`, ~line 132)
- Test: `tests/test_playlist_search.py` (create)

**Interfaces:**
- Consumes: existing `_candidate(conn, *, track_id, title, artist, album_art_url)`, `_dedupe(list)`, `PlaylistParseError` from the same module.
- Produces: `search_spotify_tracks(query: str, conn=None, limit: int = 20) -> list[dict]`. Each dict has the standard candidate keys plus `popularity: int`. Raises `PlaylistParseError` on empty query or Spotify failure.

- [ ] **Step 1: Write the failing test**

Create `tests/test_playlist_search.py`:

```python
import pytest

from slideshow.playlist_parse import search_spotify_tracks, PlaylistParseError


class FakeSpotify:
    """Minimal spotipy-compatible stub for search()."""
    def __init__(self, items):
        self._items = items

    def search(self, q, type="track", limit=20):
        return {"tracks": {"items": self._items}}


def _track(name, artist, art="http://img/x.jpg", pop=42, tid="id1"):
    return {
        "id": tid,
        "name": name,
        "type": "track",
        "popularity": pop,
        "artists": [{"name": artist}],
        "album": {"images": [{"url": art}]},
    }


def test_search_shapes_candidates(monkeypatch):
    fake = FakeSpotify([_track("Sky", "2hollis", pop=37, tid="abc")])
    monkeypatch.setattr("spotify_client.get_client", lambda: fake)
    out = search_spotify_tracks("sky", conn=None)
    assert len(out) == 1
    c = out[0]
    assert c["title"] == "Sky"
    assert c["artist"] == "2hollis"
    assert c["album_art_url"] == "http://img/x.jpg"
    assert c["track_id"] == "abc"
    assert c["popularity"] == 37
    assert c["track_key"] == "2hollis\tsky"


def test_search_dedupes_and_skips_incomplete(monkeypatch):
    items = [
        _track("Sky", "2hollis", tid="a"),
        _track("Sky", "2hollis", tid="b"),   # same track_key -> deduped
        {"id": "c", "name": "", "type": "track", "artists": [{"name": "X"}]},  # no name
    ]
    monkeypatch.setattr("spotify_client.get_client", lambda: FakeSpotify(items))
    out = search_spotify_tracks("sky", conn=None)
    assert len(out) == 1


def test_search_empty_query_raises():
    with pytest.raises(PlaylistParseError):
        search_spotify_tracks("   ", conn=None)


def test_search_api_failure_raises(monkeypatch):
    class Boom:
        def search(self, *a, **k):
            raise RuntimeError("429")
    monkeypatch.setattr("spotify_client.get_client", lambda: Boom())
    with pytest.raises(PlaylistParseError):
        search_spotify_tracks("sky", conn=None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_playlist_search.py -v`
Expected: FAILS with `ImportError: cannot import name 'search_spotify_tracks'`.

- [ ] **Step 3: Implement the helper**

In `slideshow/playlist_parse.py`, after `parse_spotify_playlist` (after line ~132), add:

```python
def search_spotify_tracks(query: str, conn=None, limit: int = 20) -> list[dict]:
    """Search Spotify for tracks matching `query`; return candidate dicts.

    Each dict matches the playlist/OCR candidate shape plus a `popularity`
    field (Spotify returns it inline on search, so the dashboard's underrated
    score works without an extra /tracks call).
    """
    from spotify_client import get_client

    q = (query or "").strip()
    if not q:
        raise PlaylistParseError("Empty search query.")

    sp = get_client()
    try:
        page = sp.search(q=q, type="track", limit=limit)
    except Exception as exc:
        raise PlaylistParseError(f"Spotify search failed: {exc}") from exc

    items = (page.get("tracks") or {}).get("items") or []
    candidates: list[dict] = []
    for track in items:
        if not track or track.get("type") not in (None, "track"):
            continue
        name = track.get("name") or ""
        artists = track.get("artists") or []
        artist = ", ".join(a.get("name", "") for a in artists).strip(", ")
        if not name or not artist:
            continue
        images = (track.get("album") or {}).get("images") or []
        art_url = images[0].get("url") if images else ""
        cand = _candidate(
            conn,
            track_id=track.get("id") or "",
            title=name,
            artist=artist,
            album_art_url=art_url,
        )
        cand["popularity"] = track.get("popularity", 50)
        candidates.append(cand)

    return _dedupe(candidates)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_playlist_search.py -v`
Expected: all four PASS.

- [ ] **Step 5: Commit**

```bash
git add slideshow/playlist_parse.py tests/test_playlist_search.py
git commit -m "feat: add search_spotify_tracks candidate helper"
```

---

### Task 4: `/api/search/spotify` endpoint

**Files:**
- Modify: `dashboard_server.py` — add route in `do_POST` (~line 109) and a handler method (near `handle_post_playlist_parse`, ~line 608)

**Interfaces:**
- Consumes: `search_spotify_tracks` (Task 3), `self._read_json_body()`, `self._send_json()`, `db.connect()`.
- Produces: `POST /api/search/spotify` with body `{"q": str}` → `200 {"tracks": [...]}`. Empty query → `400`. API failure → `500`.

- [ ] **Step 1: Register the route**

In `dashboard_server.py` `do_POST`, after the `"/api/playlist/save"` branch (line ~109), add:

```python
        elif parsed.path == "/api/search/spotify":
            self.handle_post_spotify_search()
```

- [ ] **Step 2: Add the handler**

After `handle_post_playlist_parse` (after line ~628), add:

```python
    def handle_post_spotify_search(self):
        """Search Spotify for tracks matching a query string."""
        payload = self._read_json_body()
        if payload is None:
            self._send_json(400, {"error": "Invalid JSON payload"})
            return

        q = (payload.get("q") or "").strip()
        if not q:
            self._send_json(400, {"error": "Missing 'q' (search query)"})
            return

        try:
            from slideshow.playlist_parse import search_spotify_tracks, PlaylistParseError
            with db.connect() as conn:
                tracks = search_spotify_tracks(q, conn=conn)
            self._send_json(200, {"tracks": tracks})
        except PlaylistParseError as e:
            self._send_json(400, {"error": str(e)})
        except Exception as e:
            self._send_json(500, {"error": str(e)})
```

- [ ] **Step 3: Manual smoke test**

Start the server (`python dashboard_server.py` if not already running) and run:

```bash
curl -s -X POST http://localhost:8000/api/search/spotify \
  -H "Content-Type: application/json" -d '{"q":"2hollis"}' | head -c 400
```

Expected: JSON `{"tracks": [ ... ]}` with at least one candidate having `title`, `artist`, `album_art_url`, `popularity`, `track_key`. An empty `{"q":""}` returns `{"error": "Missing 'q' ..."}` with HTTP 400.

> If Spotify OAuth isn't configured in this environment, expect a 500 with the
> auth error — that still confirms routing/handler wiring. Note the result and
> move on; the frontend tasks don't depend on a live search here.

- [ ] **Step 4: Commit**

```bash
git add dashboard_server.py
git commit -m "feat: add POST /api/search/spotify endpoint"
```

---

### Task 5: Frontend API call + search/manual-add state

**Files:**
- Modify: `dashboard/src/lib/api.ts` (add `searchSpotify`)
- Modify: `dashboard/src/lib/useRecap.ts` (extend `RecapState`, add state + handlers, export them)

**Interfaces:**
- Consumes: `searchSpotify` from `api.ts`; `Candidate` type.
- Produces, on `RecapState`:
  - `searchQuery: string`, `setSearchQuery(v: string): void`
  - `spotifyResults: Candidate[]`, `searchLoading: boolean`, `searchError: string | null`
  - `runSpotifySearch(q: string): Promise<void>`
  - `clearSearch(): void`
  - `addSearchTrack(track: Candidate): void`
  - `addCustomTrack(input: { title: string; artist: string; albumArtUrl: string }): void`

- [ ] **Step 1: Add the API call**

In `dashboard/src/lib/api.ts`, after `parsePlaylist` (~line 244), add:

```ts
// Search Spotify for tracks matching a free-text query.
export async function searchSpotify(
  apiBase: string,
  q: string,
): Promise<Candidate[]> {
  const resp = await fetch(`${apiBase}/api/search/spotify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ q }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.error || `Spotify search failed (HTTP ${resp.status}).`);
  }
  const data = await resp.json();
  return data.tracks ?? [];
}
```

- [ ] **Step 2: Add a normalize helper + defaults helper in useRecap**

In `dashboard/src/lib/useRecap.ts`, add near the top of the file (after the
imports, before `const API_BASE_KEY`):

```ts
// Mirrors text_norm.normalize on the backend (lowercase, trim, collapse
// whitespace) so a manual entry dedupes against DB tracks by track_key.
function normalizeKeyPart(s: string): string {
  return s.trim().replace(/\s+/g, " ").toLowerCase();
}

// Fill the grid-required fields that search/manual candidates don't carry.
function withCandidateDefaults(
  partial: Partial<Candidate> & Pick<Candidate, "track_key" | "title" | "artist">,
): Candidate {
  return {
    track_id: "",
    album_art_url: "",
    play_count: 0,
    last_played_unix: 0,
    primary_bucket: "unknown",
    popularity: 50,
    last_featured: null,
    recently_featured: false,
    times_featured: 0,
    ...partial,
  };
}
```

Update the `import` of `searchSpotify` by adding it to the existing `from "./api"`
import list at the top of the file.

- [ ] **Step 3: Add state + handlers**

In `useRecap.ts`, inside the hook body (alongside the other `useState`s, e.g.
after the playlist state block ~line 160), add:

```ts
  const [searchQuery, setSearchQuery] = useState("");
  const [spotifyResults, setSpotifyResults] = useState<Candidate[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
```

Then, before the `return {` block, add these callbacks:

```ts
  const runSpotifySearch = useCallback(
    async (q: string) => {
      const query = q.trim();
      if (!query) return;
      setSearchLoading(true);
      setSearchError(null);
      try {
        const results = await searchSpotify(apiBase, query);
        setSpotifyResults(results);
        if (results.length === 0) setSearchError("No Spotify results for that query.");
      } catch (err) {
        setSpotifyResults([]);
        setSearchError(err instanceof Error ? err.message : "Spotify search failed.");
      } finally {
        setSearchLoading(false);
      }
    },
    [apiBase],
  );

  const clearSearch = useCallback(() => {
    setSearchQuery("");
    setSpotifyResults([]);
    setSearchError(null);
  }, []);

  // Merge a candidate into the pool (if new) and select it. Shared by Spotify
  // results and manual entries.
  const addCandidateToSelection = useCallback((cand: Candidate) => {
    setCandidates((prev) =>
      prev.some((c) => c.track_key === cand.track_key) ? prev : [...prev, cand],
    );
    setSelectedKeys((prev) => {
      if (prev.has(cand.track_key)) return prev;
      const next = new Set(prev);
      next.add(cand.track_key);
      return next;
    });
    setSelectedOrder((prev) =>
      prev.includes(cand.track_key) ? prev : [...prev, cand.track_key],
    );
    setSummary(null);
  }, []);

  const addSearchTrack = useCallback(
    (track: Candidate) => {
      addCandidateToSelection(withCandidateDefaults(track));
    },
    [addCandidateToSelection],
  );

  const addCustomTrack = useCallback(
    (input: { title: string; artist: string; albumArtUrl: string }) => {
      const title = input.title.trim();
      const artist = input.artist.trim();
      if (!title || !artist) return;
      const track_key = `${normalizeKeyPart(artist)}\t${normalizeKeyPart(title)}`;
      addCandidateToSelection(
        withCandidateDefaults({
          track_key,
          title,
          artist,
          album_art_url: input.albumArtUrl.trim(),
        }),
      );
    },
    [addCandidateToSelection],
  );
```

Finally, add all seven new members to the returned object in the `return { ... }`
block:

```ts
    searchQuery,
    setSearchQuery,
    spotifyResults,
    searchLoading,
    searchError,
    runSpotifySearch,
    clearSearch,
    addSearchTrack,
    addCustomTrack,
```

And add their declarations to the `RecapState` interface (near the playlist
section, ~line 107):

```ts
  // Browse search / custom lookup
  searchQuery: string;
  setSearchQuery: (v: string) => void;
  spotifyResults: Candidate[];
  searchLoading: boolean;
  searchError: string | null;
  runSpotifySearch: (q: string) => Promise<void>;
  clearSearch: () => void;
  addSearchTrack: (track: Candidate) => void;
  addCustomTrack: (input: { title: string; artist: string; albumArtUrl: string }) => void;
```

- [ ] **Step 4: Typecheck and build**

Run: `cd dashboard && npm run build`
Expected: builds with no TypeScript errors (all `RecapState` members present and used or exported).

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/lib/api.ts dashboard/src/lib/useRecap.ts
git commit -m "feat: add Spotify search + manual-add state to useRecap"
```

---

### Task 6: Browse-tab search UI

**Files:**
- Modify: `dashboard/src/options/pocket/PocketDJ.tsx` — `BrowseHeader`, `BrowseGrid`, and a new `SpotifyResults` + `ManualAddForm` section.

**Interfaces:**
- Consumes: `r.searchQuery`, `r.setSearchQuery`, `r.spotifyResults`, `r.searchLoading`, `r.searchError`, `r.runSpotifySearch`, `r.clearSearch`, `r.addSearchTrack`, `r.addCustomTrack`, `r.isSelected`, `r.apiBase`, `resolveArt` (already imported).
- Produces: UI only.

- [ ] **Step 1: Add a search input to `BrowseHeader`**

In `PocketDJ.tsx` `BrowseHeader`, inside the inner `<div className="mx-auto flex max-w-3xl flex-col gap-2.5 px-4 py-3">`, as the **first** child (before the window pills row), add:

```tsx
        <div className="relative">
          <input
            type="text"
            value={r.searchQuery}
            onChange={(e) => r.setSearchQuery(e.target.value)}
            placeholder="Search your tracks or Spotify…"
            className="w-full rounded-full border border-white/10 bg-white/5 px-4 py-2 pr-9 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500/40"
          />
          {r.searchQuery && (
            <button
              type="button"
              onClick={r.clearSearch}
              aria-label="Clear search"
              className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-200"
            >
              ×
            </button>
          )}
        </div>
```

- [ ] **Step 2: Filter the local grid by query**

In `BrowseGrid`, replace the early `r.sortedCandidates` usages with a filtered
list. At the top of `BrowseGrid` (after the loading guard, before the
empty-state guard), add:

```tsx
  const q = r.searchQuery.trim().toLowerCase();
  const visible = q
    ? r.sortedCandidates.filter(
        (t) =>
          t.title.toLowerCase().includes(q) || t.artist.toLowerCase().includes(q),
      )
    : r.sortedCandidates;
```

Then change the empty-state guard from `if (r.sortedCandidates.length === 0)` to
`if (visible.length === 0 && !q)` (so a query that matches nothing locally still
shows the Spotify-search affordance from Step 3 rather than the generic empty
state), and change the `.map` from `r.sortedCandidates.map(...)` to
`visible.map(...)`.

- [ ] **Step 3: Render the Spotify-search + manual-add section under the grid**

Still in `BrowseGrid`, change the function so it returns a fragment wrapping the
existing grid plus the new section. Wrap the existing returned `<div className="grid ...">…</div>` like this:

```tsx
  return (
    <>
      <div className="grid grid-cols-2 gap-3 pt-2 sm:grid-cols-3">
        {visible.map((track) => {
          /* …existing track card JSX, unchanged… */
        })}
      </div>
      {q && <SpotifyResults r={r} query={r.searchQuery.trim()} localCount={visible.length} />}
    </>
  );
```

Then add these two components at the bottom of `PocketDJ.tsx` (before the final
`ItunesConfirmRow` or alongside the other helpers):

```tsx
function SpotifyResults({
  r,
  query,
  localCount,
}: {
  r: RecapState;
  query: string;
  localCount: number;
}) {
  return (
    <section className="mt-6 flex flex-col gap-3 border-t border-white/5 pt-5">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">
          {localCount === 0 ? "Not in your library" : "Need something else?"}
        </span>
        <button
          type="button"
          onClick={() => r.runSpotifySearch(query)}
          disabled={r.searchLoading}
          className="rounded-full bg-violet-600 px-3.5 py-1.5 text-xs font-bold text-white hover:bg-violet-500 disabled:opacity-50"
        >
          {r.searchLoading ? "Searching…" : `Search Spotify for “${query}”`}
        </button>
      </div>

      {r.searchError && <ErrorBanner message={r.searchError} />}

      {r.spotifyResults.length > 0 && (
        <div className="flex flex-col gap-2">
          {r.spotifyResults.map((track) => {
            const added = r.isSelected(track.track_key);
            return (
              <div
                key={track.track_key}
                className="flex items-center gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-2.5"
              >
                <img
                  src={resolveArt(r.apiBase, track.album_art_url)}
                  alt=""
                  className="h-12 w-12 shrink-0 rounded-lg bg-zinc-800 object-cover"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.visibility = "hidden";
                  }}
                />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold text-white">{track.title}</div>
                  <div className="truncate text-xs text-zinc-400">{track.artist}</div>
                </div>
                <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-300">
                  Spotify
                </span>
                <button
                  type="button"
                  disabled={added}
                  onClick={() => r.addSearchTrack(track)}
                  className={`shrink-0 rounded-lg px-3 py-1.5 text-xs font-bold transition-colors ${
                    added
                      ? "bg-white/5 text-zinc-500"
                      : "bg-violet-600 text-white hover:bg-violet-500"
                  }`}
                >
                  {added ? "Added ✓" : "Add"}
                </button>
              </div>
            );
          })}
        </div>
      )}

      <ManualAddForm r={r} />
    </section>
  );
}

function ManualAddForm({ r }: { r: RecapState }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [artist, setArtist] = useState("");
  const [artUrl, setArtUrl] = useState("");

  const submit = () => {
    if (!title.trim() || !artist.trim()) return;
    r.addCustomTrack({ title, artist, albumArtUrl: artUrl });
    setTitle("");
    setArtist("");
    setArtUrl("");
    setOpen(false);
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="self-start text-xs font-semibold text-violet-400 hover:text-violet-300"
      >
        Can't find it? Add manually
      </button>
    );
  }

  const inputClass =
    "w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-violet-500 focus:outline-none";

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-white/5 bg-white/[0.02] p-3">
      <input className={inputClass} placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
      <input className={inputClass} placeholder="Artist" value={artist} onChange={(e) => setArtist(e.target.value)} />
      <input className={inputClass} placeholder="Album art URL (optional)" value={artUrl} onChange={(e) => setArtUrl(e.target.value)} />
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={submit}
          disabled={!title.trim() || !artist.trim()}
          className="rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-violet-500 disabled:opacity-50"
        >
          Add to picks
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-xs font-semibold text-zinc-400 hover:text-zinc-200"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
```

> `RecapState` is already imported at the top of `PocketDJ.tsx`; `ErrorBanner`,
> `resolveArt`, and `useState` are already imported. No new imports needed.

- [ ] **Step 4: Typecheck and build**

Run: `cd dashboard && npm run build`
Expected: builds with no TypeScript errors.

- [ ] **Step 5: Lint**

Run: `cd dashboard && npm run lint`
Expected: no new lint errors in `PocketDJ.tsx`.

- [ ] **Step 6: Manual verification**

With the dashboard running (`cd dashboard && npm run dev`) and the backend up:
1. Type a partial title in the Browse search — the grid filters live.
2. Type something not in your library — the "Search Spotify" button appears;
   click it and confirm results render with Add buttons.
3. Click Add on a result — it appears in the Picks tab and the button flips to
   "Added ✓".
4. Open "Add manually", enter title/artist (+ optional art URL), submit — it
   lands in Picks.

- [ ] **Step 7: Commit**

```bash
git add dashboard/src/options/pocket/PocketDJ.tsx
git commit -m "feat: Browse search bar with local filter, Spotify search, manual add"
```

---

## Self-Review

**Spec coverage:**
- Feature 1 slider → Task 2; defensive clamp → Task 1. ✅
- Feature 2 backend helper → Task 3; endpoint → Task 4; api+state → Task 5; UI (search bar, local filter, Spotify results, manual form) → Task 6. ✅
- Candidate default contract → enforced in Task 5 (`withCandidateDefaults`). ✅
- Security TLS fix → already committed on this branch (noted in spec). ✅

**Placeholder scan:** No TBD/TODO; every code step shows full code. The one
"…existing track card JSX, unchanged…" comment in Task 6 Step 3 refers to the
block already present in the file being wrapped, not omitted new code. ✅

**Type consistency:** `addSearchTrack(track: Candidate)`, `addCustomTrack({title,
artist, albumArtUrl})`, `runSpotifySearch(q)`, `clearSearch()` names match
between the `RecapState` interface (Task 5), the return object (Task 5), and the
consumers (Task 6). `withCandidateDefaults` / `normalizeKeyPart` are module-local
to `useRecap.ts`. `search_spotify_tracks(query, conn, limit)` signature matches
between Task 3 (def), Task 4 (call), and tests. ✅
