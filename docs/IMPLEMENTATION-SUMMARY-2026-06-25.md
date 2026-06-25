# Implementation Summary & Technical Handoff (2026-06-25)

This document summaries the architecture, changes, and testing implementations completed on **2026-06-25** covering **Phase 4 (Automation)**, **Phase 5 (Weekly Recap Dashboard)**, **Slide Diversity & Dispersion**, and **Screenshot OCR Ingest**. It serves as the primary technical context for any future agents picking up the repository.

---

## 1. Architecture Overview & File Map

The codebase has been completed through Phase 5 of the original roadmap. Below is the updated layout of modified and untracked files:

```
ttspotslideshow/
├── README.md                      # Updated setup guides, Task Scheduler config, & OCR command details
├── CLAUDE.md                      # Roadmap updated; all Phases 0–5 marked complete
├── config.py                      # ADDED: LASTFM_USER config, get_lastfm_user() helper with auto-detection
├── db.py                          # ADDED: latest_lastfm_played_at_unix() query helper
├── run_bidaily.py                 # NEW: Unified bi-daily orchestration pipeline (Spotify logger + Last.fm API)
├── dashboard_server.py            # NEW: Zero-dependency Python HTTP API + Static file server (port 8000)
├── dashboard/                     # NEW React/TypeScript + Tailwind CSS v4 dashboard client (Vite)
│   ├── src/App.tsx                #   Configurable Backend API Base input, Candidate list, & Slideshow compiler
│   └── src/index.css              #   Tailwind imports and custom dark-mode baseline
├── ingest/
│   └── lastfm_import.py           # ADDED: import_recent_from_api() incremental API scrobble loader
├── slideshow/
│   ├── builder.py                 # ADDED: disperse_tracks() balance engine & build_recap_slideshow() compiler
│   └── ocr.py                     # NEW: Native Windows OCR parser via PowerShell & iTunes Search resolver
└── tests/                         # Test Suite expanded from 88 to 115 tests
    ├── test_run_bidaily.py        # NEW: Orchestration pipeline stub mock tests
    ├── test_dashboard_server.py   # NEW: Mock HTTP server endpoint checks (GET/POST/Static files)
    ├── test_ocr.py                # NEW: iTunes fuzzy alignment & pairing validation tests
    └── test_builder.py            # ADDED: test_disperse_tracks() and test_build_recap_slideshow()
```

---

## 2. Completed Phase Implementations

### A. Phase 4 — Automation (`run_bidaily.py`)
* **Goal**: Orchestrate database migrations, live capturer, and slideshow builds into a single entry script fit for Task Scheduler.
* **Implementation Details**:
  * Calls `db.init_db()` to automatically run migrations.
  * Pulls from Spotify via `logger.log_recent_plays()`.
  * Pulls from the Last.fm API using `ingest.lastfm_import.import_recent_from_api()`.
  * Selects tracks, resolves cover art, renders slides, and updates `featured_tracks` history.
  * Captures exceptions gracefully on individual ingests so rate blocks or offline states don't halt the pipeline.
* **Incremental Ingest**:
  * [latest_lastfm_played_at_unix](file:///C:/Users/prinp/Documents/GitHub/ttspotslideshow/db.py#L140) queries `MAX(played_at_unix) WHERE source = 'lastfm'` to fetch only newer plays.
  * [import_recent_from_api](file:///C:/Users/prinp/Documents/GitHub/ttspotslideshow/ingest/lastfm_import.py#L88) queries `user.getrecenttracks` from Last.fm, paging from page 1 and stopping once `page >= totalPages`.

### B. Phase 5 — Weekly Recap Dashboard (`dashboard/` + `dashboard_server.py`)
* **Goal**: User-facing visual dashboard to pick tracks and render recap slide packages manually.
* **Backend Server** (`dashboard_server.py`):
  * Zero-dependency implementation using `http.server.BaseHTTPRequestHandler`.
  * Exposes `GET /api/candidates?days=N` to query tracks. Decorates tracks with Spotify popularity scores by batching track IDs (chunks of 50) via `sp.tracks()`.
  * Exposes `POST /api/generate` receiving a list of tracks and calling `build_recap_slideshow()`.
  * Supports full CORS (`Access-Control-Allow-Origin: *`) for Vite development mode.
  * Safely serves files from `dashboard/dist` for production deployment.
* **React Frontend** (`dashboard/`):
  * Built using React 19, TypeScript, and **Tailwind CSS v4** (utilizing `@tailwindcss/vite`).
  * Supports dynamic backend endpoints. The **Backend API** input field in the header saves to `localStorage` (default: `http://localhost:8000`). This permits deploying the static bundle to **Cloudflare Pages** and bridging requests back to a local HTTPS tunnel.
  * Offers sorting (by Plays or Underrated Score) and quick-selection shortcuts (Top 4, 8, 12, 16).

### C. Slide Diversity & Dispersion (`disperse_tracks()`)
* **Goal**: Disperse duplicate artists or albums across slides to maximize visual variety.
* **Implementation Details**:
  * [disperse_tracks](file:///C:/Users/prinp/Documents/GitHub/ttspotslideshow/slideshow/builder.py#L15) takes a flat list of tracks and greedily sorts them into slides of size 4.
  * Enforces `max_artist` (1) and `max_album` (1) constraints (using `album_art_url` as unique album proxy).
  * If a constraint is violated, it falls back to matching only the artist constraint, and finally falls back to taking the next available track.
  * Integrates seamlessly into the automated builder and the manual recap compiler.

### D. Screenshot OCR Ingest (`slideshow/ocr.py`)
* **Goal**: Read track titles and artists from images (Spotify queue or playlist screenshots) and compile slides directly.
* **Implementation Details**:
  * **Native Windows OCR**: Executes a PowerShell script via Python `subprocess` accessing the native `Windows.Media.Ocr.OcrEngine`. Fast, offline, and zero python dependencies.
  * **Fuzzy Parser**: Loops through raw text lines pairing consecutive lines. Queries the iTunes Search API for matches. Checks that the matched `trackName` and `artistName` are substrings of the paired OCR lines to filter out noise (such as song durations or page numbers).
  * Shuffles and disperses resolved tracks, download artwork, and compiles slides.

---

## 3. Test Coverage & Verification

The testing framework uses `pytest` offline. Total tests grew from 88 to **113 passing**.

Key test suites added:
* **`tests/test_run_bidaily.py`**:
  * Stubs `log_recent_plays`, `import_recent_from_api`, and `build_slideshow` to test the pipeline orchestration flow.
  * Verifies skip flags (`--skip-spotify`, `--skip-lastfm`) bypass individual ingests correctly.
* **`tests/test_dashboard_server.py`**:
  * Mocks `BaseHTTPRequestHandler` using a dummy subclass containing a fake socket writer.
  * Asserts correct REST routing, CORS headers, JSON payloads, and local file lookup resolution.
* **`tests/test_ocr.py`**:
  * Tests fuzzy alignment matching (`is_valid_match`) under direct, reverse, and combined text blocks.
  * Mocks the iTunes search fetcher with local mock JSON files to verify that lines are paired and resolved correctly.

To run verification:
```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

---

## 4. Technical Roadmap & Future Work

If you are branching off this work, consider the following future items:
1. **Spotify Rate Limit Resilience**:
   * Spotify's API has strict rate limits. A background daily schedule of `python -m ingest.enrich_cli --refresh` is configured to slowly upgrade Last.fm tags to Spotify subgenres, but if the block returns, ensure the exception catches stay active.
2. **Weekly Recap Deployment**:
   * The React dashboard is ready to deploy to Cloudflare Pages. Ensure developers running the app set up `cloudflared` (Cloudflare Tunnel) or `ngrok` locally, and insert the tunnel URL into the Backend API header input.
3. **Weekly recap custom picker picker**:
   * Currently, the dashboard allows selecting a multiple of 4 tracks and compiles them. In the future (Phase 5 extension), you could allow manual picking of "most underrated" candidates directly based on a combined visual metric.
