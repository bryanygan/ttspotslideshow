# Comprehensive Code Review: ttspotslideshow

> **Reviewer**: Antigravity (Claude Opus 4.6)
> **Date**: 2026-06-25
> **Scope**: Full codebase — 55 commits, 9 modules, 27 test files, ~40 source files, 6 design specs/plans, 8 SDD task briefs/reports
> **Status**: Read-only review — no changes implemented

---

## Table of Contents

1. [Project Overview & Original Vision](#1-project-overview--original-vision)
2. [Development History & Agent Decisions](#2-development-history--agent-decisions)
3. [Architecture Assessment](#3-architecture-assessment)
4. [Module-by-Module Analysis](#4-module-by-module-analysis)
5. [Test Suite Assessment](#5-test-suite-assessment)
6. [Cross-Cutting Concerns](#6-cross-cutting-concerns)
7. [Issues & Recommendations](#7-issues--recommendations)
8. [Summary Scorecard](#8-summary-scorecard)

---

## 1. Project Overview & Original Vision

**ttspotslideshow** ("TikTok Spotify Slideshow") is a personal Python pipeline that:

1. **Ingests** listening data from Spotify API + Last.fm XML exports + OCR screenshots
2. **Enriches** artists with genre tags from Spotify + Last.fm APIs
3. **Selects** 12–16 diverse tracks every 2 days using a genre-aware round-robin algorithm
4. **Renders** Spotify-style "Now-Playing" cards (540×960) and assembles them into 2×2 collage slides (1080×1920)
5. **Serves** a weekly recap dashboard (React 19 + TypeScript + Tailwind CSS) for manual track picking and slide generation

The core product goal is **automated content creation for TikTok** — generating visually appealing slideshow images of current listening habits for social media posting.

### Bryan's Original Idea (from CLAUDE.md)

> Automate music rotation posts for TikTok: every other day pull top 12–16 unique songs from different genres from listening history, create Spotify/Apple Music-style "now playing" card images, collage 4 into slideshow slides. Also wants a weekly recap of best/most underrated songs (manual pick, not automated).

### Key Requirements vs. Delivery Status

| Requirement | Status | Notes |
|---|---|---|
| Log Spotify plays to SQLite | ✅ Done | `logger.py` — last 50 plays per run |
| Import Last.fm scrobble history (XML) | ✅ Done | ~108K scrobbles from 91 MB XML |
| Cross-source deduplication | ✅ Done | 120-second window, prefers Spotify metadata |
| Genre enrichment (Spotify + Last.fm) | ✅ Done | Spotify primary, Last.fm fallback |
| Hip-hop subgenre granularity | ✅ Done | 6 rap subgenres (rage, trap, drill, plugg, boom-bap, melodic-rap) |
| Genre-diverse track selection (round-robin) | ✅ Done | Composite score: 0.6×plays + 0.4×recency × novelty |
| Freshness penalty for recently-featured tracks | ✅ Done | 14-day linear recovery |
| Pillow-based card rendering (540×960) | ✅ Done | With seeded deterministic scrubber |
| 2×2 collage assembly (1080×1920) | ✅ Done | Edge-to-edge, no gutters |
| Hi-res art via iTunes Search API fallback | ✅ Done | 600×600 from iTunes, 300×300 Last.fm fallback |
| Auto-widen window for sparse data | ✅ Done | Steps: 2→4→7→14→30 days |
| 429-resilient enrichment with backoff/defer | ✅ Done | Circuit breaker after 20 consecutive transients |
| Bi-daily automation orchestrator | ✅ Done | `run_bidaily.py` for Task Scheduler |
| Weekly recap dashboard (manual pick) | ✅ Done | React 19 + Vite 8 + Tailwind v4 |
| Screenshot OCR ingest (bonus) | ✅ Done | Windows native OCR via PowerShell |
| Slide diversity (no duplicate artist/album per slide) | ✅ Done | `disperse_tracks()` greedy algorithm |

**All planned features have been delivered.** The project is feature-complete relative to its design specs, plus several beyond-plan additions (OCR, dashboard, dispersion algorithm).

---

## 2. Development History & Agent Decisions

### Commit History (55 commits, 3 merged PRs)

```
Phase 1  (1 commit)   — Foundation: Spotify logger, SQLite DB, config
Phase 2  (13 commits) — Card renderer (Pillow): colors, fonts, art, card, collage, demo
Phase 3A (12 commits) — Last.fm ingest: XML import, genre mapping, enrichment CLI, hardening
Phase 3B (8 commits)  — Slideshow: window, selector, art_resolve, builder, CLI
Phase 4  (1 commit)   — Bi-daily automation pipeline
Phase 5  (3 commits)  — Recap dashboard (React/TS/Tailwind) + OCR ingest
Cleanup  (4 commits)  — Docs refresh, deferred review cleanup, genre coverage
Latest   (2 commits)  — Card redesign, Cloudflare Pages base URL
```

### Branch Structure

| Branch | Purpose | Status |
|---|---|---|
| `master` | Main branch | Active |
| `phase3a-lastfm-ingest` | Last.fm import + enrichment | Merged (PR #1) |
| `phase3b-slideshow` | Slideshow selection + assembly | Merged (PR #2) |
| `harden-enrichment` | 429 resilience hardening | Merged (PR #3) |

### SDD Task Breakdown (8 Tasks across Phase 3B)

The agents used a Superpowers-Driven Development (SDD) workflow: **design spec → implementation plan → task briefs → TDD implementation → task reports → review**. Every task has both a brief and a report in `.superpowers/sdd/`.

| Task | Objective | Outcome |
|---|---|---|
| Task 1 | `featured_tracks` table + upsert | ✅ 3 tests, commit `db8689c` |
| Task 2 | `window_track_candidates` aggregation | ✅ 2 tests, commit `15b9972` |
| Task 3 | Window resolution with auto-widen | ✅ 3 tests, commit `32ad4a4` |
| Task 4 | Genre round-robin selector | ✅ 6 tests, commit `9cdd34f` |
| Task 5 | iTunes art resolution with fallback | ✅ 4 tests, commit `059aa1b` |
| Task 6 | Build pipeline orchestration | ✅ 2 tests, commit `9714878` |
| Task 7 | CLI entry point + summary formatter | ✅ 2 tests, commit `8814434` |
| Task 8 | Config + enrichment CLI orchestration | ✅ 1 test, commit `7a559ab` |

### How the Agents Coded — Patterns & Observations

#### Strengths in Agent Approach

1. **Rigorous brief → implement → test → report cycle**: Every task had a design spec, implementation plan, task brief, and completion report. Strict TDD (RED→GREEN→full-suite) was followed for every task. This is exceptionally well-documented.

2. **Conservative technology choices**: Raw SQL over ORM, stdlib `urllib` over `requests`, Pillow over headless browser rendering, stdlib `http.server` over Flask/FastAPI. Each choice was justified in design specs and correct for a single-user personal tool.

3. **Bottom-up layered implementation**: Tasks were ordered carefully — DB schema (T1) → data aggregation (T2) → window logic (T3) → selection algorithm (T4) → art resolution (T5) → pipeline orchestration (T6) → CLI (T7) → config (T8). Each layer consumed only interfaces produced by prior tasks.

4. **Dependency injection for testability**: Consistently used injectable `fetch`, `sleep`, `now_unix`, `cache`, `progress` callables to enable fully offline testing without network calls or time dependencies. This is the codebase's best architectural pattern.

5. **Iterative bug discovery and fixing**: Several bugs were found and fixed promptly:
   - Grayscale art producing tinted gradients → achromatic detection added
   - Light album art washing out cards → brightness cap tightened
   - Text normalization over-stripping multi-dash titles → regex changed from `.*$` to `[^-]*$`
   - "feat" matching as substring → regex anchoring fixed

6. **Conservative with reviewer feedback**: The agent explicitly rejected a reviewer's suggestion to "fix" the unused `floor` parameter because it would break the multiple-of-4 invariant. Good engineering judgment.

7. **Hardening as a dedicated phase**: The enrichment hardening (429 resilience, circuit breaker, incremental commits) was recognized as needing its own focused task rather than being bolted on.

#### Weaknesses in Agent Approach

1. **Tests written after implementation in Phase 1–2**: Testing was deferred from Task 1 and added incrementally. By Phase 3B, strict TDD was followed, but early phases lacked this discipline.

2. **Dashboard scoped in a task brief, not a design spec**: Every other subsystem got a dedicated design spec document. The dashboard was tacked onto Task 8's scope without its own architectural document. This shows in the implementation — it's a 552-line monolithic React component.

3. **No shared test infrastructure**: Each test file independently creates mocks, temp databases, and fake objects. A `conftest.py` would have eliminated significant duplication. `FakeSpotify` is reused across files (good), but most helpers are duplicated.

4. **Cleanup as a separate pass**: The WI-2 (deferred code review findings — 14 specific issues) and `final-fix-report.md` show issues that ideally should have been caught during initial implementation.

5. **Some code duplication introduced late**: `build_recap_slideshow` duplicates ~50 lines from `build_slideshow`. Three separate places build iTunes API URLs. Two modules define identical `_default_fetch` functions.

---

## 3. Architecture Assessment

### Data Flow

```
Data Sources                  Ingest Layer               Storage
─────────────                 ────────────               ───────
Spotify API ──────→ logger.py ──────────────→ ┌─────────────────┐
Last.fm XML ──────→ lastfm_import.py ────────→│   plays.db      │
Screenshots ──────→ ocr.py ─────────────────→ │   (SQLite)      │
                                              │                 │
                    Enrichment                │  plays          │
                    ──────────                │  artist_genres  │
                    enrich_cli.py ←──────────→│  featured_tracks│
                    ├── genres.py             │  artists        │
                    ├── lastfm_client.py      └────────┬────────┘
                    └── genre_map.py                   │
                                                       ▼
                    Selection                   Rendering
                    ─────────                   ─────────
                    window.py ──→ selector.py    art_resolve.py
                         │            │         art.py
                         └────────────┘         card.py (540×960)
                              │                 collage.py (1080×1920)
                              ▼                      │
                         builder.py ─────────────────┘
                              │
                              ▼
                    Output: output/slides/YYYY-MM-DD/slide_N.png
                              │
                    Dashboard: dashboard_server.py (port 8000)
                              └── dashboard/ (React 19 + Vite 8)
```

### Architecture Strengths

| Aspect | Assessment |
|---|---|
| **Separation of concerns** | ✅ Excellent — each module has a single, clear responsibility |
| **Data flow direction** | ✅ Unidirectional — ingest → store → select → render → output |
| **No circular dependencies** | ⚠️ Mostly clean — one cross-package import: `ingest/lastfm_import.py` imports from `render.art` |
| **Single source of truth** | ✅ SQLite DB is the only data store |
| **Idempotent operations** | ✅ All major operations are safe to re-run (INSERT OR IGNORE, cached skipping, migration detection) |
| **Configuration centralization** | ✅ All config in `config.py` with `.env` support |
| **Testability** | ✅ Excellent DI pattern — injectable `fetch`/`sleep`/`now_unix` throughout |
| **Pure functions at core** | ✅ `render_card` and `select_tracks` are pure (no I/O) — deterministic and testable |
| **Determinism** | ✅ Seeded RNG for scrubber, explicit tiebreaks in sorting, date-based featured tracking |

### Architecture Weaknesses

| Aspect | Assessment |
|---|---|
| **Connection management** | ⚠️ Mixed patterns — some functions use `db.connect()` context manager, others require `conn` parameter |
| **Schema migration** | ⚠️ Fragile "detect old schema and rebuild" — no versioning system |
| **Error propagation** | ⚠️ Three different strategies used (fail-soft, fail-hard, log+continue) |
| **Observability** | ⚠️ Uses `print()` / `print(stderr)` everywhere — no `logging` framework |
| **Concurrency** | ⚠️ No explicit WAL mode, no connection pooling — DB lock encountered during development |
| **Cross-package dependency** | ⚠️ `ingest.lastfm_import` → `render.art.is_placeholder` couples ingest to render |
| **Dashboard server** | ⚠️ Single-threaded `http.server` blocks on Spotify API calls |

---

## 4. Module-by-Module Analysis

### 4.1 Core Backend

#### `config.py` (92 lines) — Configuration

- **Quality**: Clean, well-documented, single responsibility.
- **Pattern**: Module-as-singleton — loads `.env` at import time via `load_dotenv()`.
- **Key functions**: `ensure_dirs()`, `assert_credentials()`, `resolve_export_path()` (auto-detects newest `data/scrobbles-*.xml`), `get_lastfm_user()` (auto-detects from filename).
- **Issues**:
  - `get_lastfm_user()` has bare `except Exception: pass` — silently swallows errors.
  - `assert_credentials()` only validates Spotify creds despite its generic name.
  - Eager loading at import time can break tests that `import config` without env vars.

#### `db.py` (398 lines) — Database Layer (largest file)

- **Quality**: Well-structured, good parameterized SQL, idempotent migration.
- **Key design**: Context manager for connections (`@contextmanager`), keyword-only args on inserts, INSERT OR IGNORE for idempotency.
- **Tables**: `plays`, `artists`, `artist_genres`, `featured_tracks`.
- **Critical function** — `canonical_plays(conn, window_seconds=120)`: Cross-source dedup. Loads ALL plays into memory, scans with a sliding window, prefers Spotify rows over Last.fm within 120 seconds of each other.
- **Critical function** — `window_track_candidates(conn, start_unix)`: Calls `canonical_plays()` (full table load), then filters by `start_unix` in Python. This is the bottleneck query for selection.
- **Issues**:
  - **Mixed connection patterns**: `insert_play()` takes `conn` but `latest_played_at()` opens its own. Makes composing transactions difficult.
  - **`canonical_plays` loads ALL plays into memory**: O(n) scan of tens of thousands of rows. Will degrade as data grows.
  - **`window_track_candidates` calls `canonical_plays` without a start filter**: Processes the entire canonical set, then filters by `start_unix` in Python — wasted work.
  - **No explicit indexes beyond UNIQUE constraints**: The window query filters on `played_at_unix` which has no index.
  - **`played_at_unix` can be NULL for old rows**: Pre-migration Spotify rows lack this field. `canonical_plays` filters these out, which means some Spotify data may be invisible.

#### `spotify_client.py` (35 lines) — Spotify API Wrapper

- **Quality**: Thin, focused. Good.
- **Key design**: Factory function. `retries=0, status_retries=0` — deliberately propagates 429s immediately rather than sleeping (documented in comments).
- **Issues**:
  - No singleton/caching — every call to `get_client()` creates a new client. Called per-request in `dashboard_server.py`.
  - `open_browser=True` problematic for headless/Task Scheduler environments.
  - No error handling around token refresh failures.

#### `logger.py` (127 lines) — Spotify Ingest

- **Quality**: Clean, well-structured. Cache-aside pattern for genre lookups.
- **Key design**: Incremental fetch via `after` cursor (Spotify's pagination). Idempotent inserts.
- **Issues**:
  - `popularity=None` hardcoded with comment "field removed from Spotify API (Feb 2026)" — dead code path but `popularity` column still exists in schema.
  - `_resolve_genre` catches only `SpotifyException`, not network errors (`ConnectionError`, `Timeout`).
  - The `after` parameter uses `latest_played_at()` across ALL sources (including Last.fm). If a Last.fm timestamp is slightly ahead, Spotify plays could theoretically be skipped.
  - **Zero tests** for this module.

#### `text_norm.py` (22 lines) — Text Normalization

- **Quality**: Excellent — tiny, focused, pure function, well-documented rationale.
- **What it does**: Lowercase, strip, collapse whitespace, trim trailing `" - <something> remaster/version"` suffix.
- **Deliberately conservative**: Only strips `remaster`, `remastered`, and `version`. Other suffixes (`deluxe`, `remix`, `live`, `acoustic`) are intentionally preserved to avoid false merges.
- **Issues**: No Unicode normalization (equivalent Unicode representations won't match). Minor: only handles parenthetical `()` not square bracket `[]` suffixes.

#### `run_bidaily.py` (112 lines) — Pipeline Orchestrator

- **Quality**: Good orchestration with appropriate error boundaries.
- **Pattern**: Each ingest step wrapped in `try/except Exception` with stderr warnings, allowing pipeline to continue. Slideshow build step is NOT wrapped — failure propagates (intentional — it's the primary output).
- **Issues**:
  - Dead imports: `datetime` and `timezone` are imported but never used.
  - No `logging` framework — uses `print()` statements. For a Task Scheduler job, file logging would be more robust.
  - No return value or exit code to indicate partial success vs. full success.
  - Import-time coupling: if `ingest.lastfm_import` has a missing dependency, script fails even with `--skip-lastfm`.

#### `dashboard_server.py` (246 lines) — HTTP Server

- **Quality**: Functional, clear. Welcome page fallback is a nice touch.
- **Pattern**: stdlib `http.server.BaseHTTPRequestHandler` with path-based routing. No framework.
- **Endpoints**: `GET /api/candidates?days=N`, `POST /api/generate`, static file serving from `dashboard/dist/`.
- **Issues**:
  - **Path traversal vulnerability**: Uses `str(file_path).startswith(str(dist_resolved))` which is a known anti-pattern on Windows. Should use `file_path.is_relative_to(dist_resolved)` (Python 3.9+).
  - **`Access-Control-Allow-Origin: *`**: Wide-open CORS. Fine for local dev, risky if deployed.
  - **Single-threaded**: Blocks on Spotify API calls (potentially 10+ seconds for popularity batch). Server is unresponsive during that time.
  - Dead import: `os` is imported but never used.
  - `content_length` parsing doesn't handle missing `Content-Length` header gracefully.
  - Hardcoded port 8000 with no CLI flag or env var override.
  - Incomplete MIME type map (no `.woff`, `.woff2`, `.map`, `.ico`).

---

### 4.2 Ingest Module (`ingest/`)

#### `lastfm_import.py` (195 lines) — XML Stream Importer + API Importer

- **Quality**: Excellent memory management with `iterparse` + `root.clear()`.
- **Two import paths**:
  1. `import_scrobbles(conn, xml_path)` — Batch import from XML export. Idempotent via INSERT OR IGNORE.
  2. `import_recent_from_api(conn, api_key, username, since_unix)` — Incremental API import (paginated, 200/page).
- **Issues**:
  - **Double XML parse**: `import_scrobbles` calls both `iter_scrobbles()` and `_count_tracks()`, each doing a full 91 MB parse. Fix: count during iteration.
  - **Duplicate `_default_fetch`**: Identical function exists in `lastfm_client.py`. Should be extracted to shared utility.
  - **Cross-package import**: `from render.art import is_placeholder` couples ingest to render. The `is_placeholder` function (checks for Last.fm's default "no image" hash) is simple enough to live in a shared utility.

#### `genres.py` (153 lines) — Genre Resolution Engine

- **Quality**: Very well-designed for API flakiness. Excellent transient-vs-permanent failure distinction.
- **Strategy**: Tier 1 Spotify → Tier 2 Last.fm → Tier 3 `unknown`.
- **Key design** — `resolve_artist_genre()`:
  - Spotify search with **name-match guard**: `normalize(result_name) == normalize(input_name)` — prevents false artist matches.
  - If Spotify returns 429 or network error: sets `transient=True` and returns early — artist is NOT cached, so future runs can retry. This is the most sophisticated error handling in the codebase.
- **Key design** — `enrich_all()`:
  - **Circuit breaker**: After 20 consecutive transient failures, stops early to avoid burning API quota.
  - **Batched commits**: Every 50 artists for crash resilience.
  - **Resumability**: Already-cached artists are skipped (unless `refresh=True` AND cached source isn't Spotify).
  - **Rate limiting**: 0.25s sleep after each Last.fm call (reactive backoff for Spotify via circuit breaker).
- **Issues**:
  - When `refresh=True` and an artist has a transient failure, the existing cached row is untouched (good), but the `continue` skips Last.fm retry. Correct behavior but worth documenting.

#### `genre_map.py` (116 lines) — Genre Mapping

- **Quality**: Well-curated, domain-appropriate.
- **Buckets** (16): `rage, trap, drill, plugg, boom-bap, melodic-rap, hip-hop, pop, r&b, rock, electronic, indie, country, latin, other, unknown`. Heavy hip-hop granularity reflects the catalog composition.
- **Key design**: First-match wins via `bucket_for(genres)`. Deny-list filtering for noise tags via `_NON_GENRE_TAGS` frozenset (~60 tags: nationalities, cities, meta labels like "seen live").
- **Clever decade detection**: `stripped = t[:-1] if t.endswith("s") else t; if stripped.isdigit()` catches "90s", "2010s", "1999".

#### `lastfm_client.py` (56 lines) — Last.fm API Client

- **Quality**: Clean, minimal, no unnecessary dependencies. 15-second timeout.
- **Key design**: `min_weight=1` is deliberately low — noise filtering happens downstream in `genre_map.is_genre_noise`.
- **Error handling**: Blanket `except Exception` returns `[]` (intentional — caller treats as "no data"). Defensive `int()` parsing of `count` values.

#### `enrich_cli.py` (105 lines) — Enrichment CLI Orchestrator

- **Quality**: Clean CLI with good flag design.
- **Pipeline**: `db.migrate()` → `import_scrobbles()` → commit → `enrich_all()` → return summary.
- **Good**: Commits after import before enrichment — import progress survives crashes during the long enrichment phase.
- **CLI modes**: `--lastfm-only`, `--refresh`, `--lastfm-refresh` (re-do Last.fm with updated genre map).

---

### 4.3 Render Module (`render/`)

#### `card.py` (173 lines) — Card Compositor (Core)

- **Quality**: Clean Pillow composition. Good rounded-corner technique. Deterministic output.
- **Constants**: `CARD_W=540, CARD_H=960, PAD=32, ART=476, ART_Y=130, ART_RADIUS=14`.
- **Rendering pipeline**:
  1. Open & resize album art to 476×476 (or placeholder on failure)
  2. Extract dominant color → clamp → compute darker bottom color
  3. Create vertical gradient background (540×960)
  4. Paste art with rounded corners
  5. Draw title text (Montserrat Bold 30px) and artist text (Montserrat Medium 20px)
  6. Draw plus-in-circle icon (add-to-library)
  7. Draw scrubber bar (background track, filled portion, knob circle)
  8. Draw elapsed/total time labels
  9. Composite RGBA overlay onto gradient
- **Clever**: `scrubber_values(track_id)` uses `random.Random(track_id)` as a seeded RNG — same track always renders with the same playback position.
- **Placeholder fallback**: When art is missing, draws a music note using Pillow primitives (ellipse + stem + polygon).
- **Issues**:
  - `track` is an untyped `dict` — would benefit from a TypedDict or dataclass.
  - Many magic numbers in layout: `text_y=698`, `bar_y` offset `46`, icon size `38`, arm lengths. These could be named constants.
  - No text wrapping — long names are truncated with "…".

#### `colors.py` (51 lines) — Colour Processing

- **Quality**: Smart HSL/HSV-space clamping. Good achromatic preservation.
- **Key functions**:
  - `dominant_color(img)`: Resize to 64×64, quantize to 8 colors via median-cut, return most frequent.
  - `clamp_color(rgb, min_lum=50, min_sat=0.20, max_lum=210)`: HSV clamping for contrast. Achromatic colors (s=0) skip saturation boosting.
  - `vertical_gradient(size, top, bottom)`: Creates a 1-pixel-wide column with interpolated colors, then stretches to full width with NEAREST resampling. Very efficient.
- **Minor issue**: Parameter names `min_lum`/`max_lum` are misleading — they clamp HSV Value (brightness), not perceptual luminance.

#### `art.py` (50 lines) — Art Caching

- **Quality**: Simple, effective. Strategy pattern for testability.
- **Key design**: SHA-1 hash of URL → `cache_dir/<hash>.jpg`. DI-friendly with injectable `fetch` parameter.
- **Features**: `is_placeholder(url)` detects Last.fm's default "no image" placeholder by known hash.
- **Issues**:
  - `urllib.request.urlretrieve` has no timeout — could hang indefinitely.
  - No logging on download failure — silent fallback.
  - `.jpg` extension hardcoded regardless of actual format (harmless — Pillow opens by content).
  - No cache eviction — grows indefinitely.

#### `fonts.py` (38 lines) — Font Loading

- **Quality**: Good caching, validates weight against known font files.
- **`truncate_to_width`**: Character-by-character trimming with "…" suffix. O(n²) worst case (calls `getlength()` each iteration), but acceptable for short track titles.
- **Three weights available**: Bold, Medium, Regular (Montserrat TTFs bundled in `render/assets/fonts/`).

#### `collage.py` (22 lines) — Collage Assembly

- **Quality**: Simple, correct, validated.
- **Output**: 1080×1920 (2×540, 2×960) — perfect 9:16 portrait for TikTok.
- **Safety**: Resizes cards with LANCZOS if not exactly 540×960. Raises `ValueError` if not exactly 4 cards.

#### `render_demo.py` (53 lines) — Demo CLI

- **Quality**: Good for prototyping. Uses real Last.fm art URLs.
- **4 hardcoded sample tracks** with Last.fm CDN URLs.
- **Issue**: No guard for `len(tracks) < 4` — would crash in `collage()`.

---

### 4.4 Slideshow Module (`slideshow/`)

#### `selector.py` (77 lines) — Track Selection Algorithm

- **Quality**: Well-designed, pure function (no I/O), highly testable.
- **Scoring formula**:
  ```
  base_score = 0.6 × (play_count / max_play_count) + 0.4 × (recency_normalized)
  final_score = base_score × novelty_factor
  ```
- **Novelty**: `_novelty(track_key, featured, run_date)` — linear recovery from 0→1 over 14 days. `min(1.0, days / 14)`.
- **Round-robin algorithm**:
  1. Score all candidates
  2. Group by genre bucket
  3. Sort each bucket by score desc (tiebreaker: recency desc, then title asc)
  4. Order buckets by total play count desc
  5. Pick one from each bucket per pass, cycle until target reached
  6. Truncate to nearest multiple of 4 (whole slides only)
- **Issues**:
  - **Novelty bug**: When `days <= 0` (featured today), returns `1.0` (no suppression). A track featured TODAY can be re-selected immediately. The comment says "not suppressed" — this is intentional for same-day determinism but is surprising behavior.
  - `floor` parameter is accepted but intentionally unused (documented — the `(n//4)*4` logic already reproduces floor tiers).

#### `window.py` (25 lines) — Window Resolution

- **Quality**: Simple, effective, testable (injectable `now_unix`).
- **Steps**: Iterates through window sizes [2, 4, 7, 14, 30 days]. Stops at first window yielding ≥ target unique tracks. Falls back to widest if none meets target.
- **Issue**: `floor` parameter accepted but never used inside the function — dead parameter kept for "caller symmetry."

#### `builder.py` (177 lines) — Pipeline Orchestrator

- **Quality**: Clean orchestration tying together all subsystems.
- **Key function** — `disperse_tracks(tracks, slide_size=4, max_artist=1, max_album=1)`:
  - Reorders tracks so no single 4-card slide has >1 track from the same artist or album.
  - Uses `album_art_url` as proxy for album identity (no dedicated album key).
  - Greedy slot-filling algorithm.
- **Key function** — `build_slideshow(conn, out_root, ...)`:
  - Pipeline: `resolve_window()` → `select_tracks()` → `disperse_tracks()` → truncate to multiple of 4 → resolve art → render cards → collage → save → `record_featured()`
  - Returns summary dict with `{date, days_used, track_count, slide_count, genre_spread, out_dir}`.
- **Issues**:
  - **DRY violation**: `build_recap_slideshow` duplicates ~50 lines from `build_slideshow`. Lines 127–176 are nearly identical to lines 78–124. A shared `_render_and_save` helper could eliminate ~40 lines.
  - **Potential crash**: `build_recap_slideshow` records `"recap-2026-06-25"` as a date in `featured_tracks`, but `_novelty()` in `selector.py` calls `date.fromisoformat()` on stored dates — this would raise `ValueError` on `"recap-2026-06-25"`.
  - **Redundant imports**: `build_recap_slideshow` re-imports modules already imported at module top.

#### `art_resolve.py` (44 lines) — iTunes Art Fallback

- **Quality**: Smart URL template trick. Good DI with injectable `fetch` and optional `cache` dict.
- **Fallback chain**: iTunes 600×600 → stored Last.fm `album_art_url` → empty string.
- **URL rewrite**: Replaces `100x100` with `600x600` in the iTunes artwork URL.
- **Issues**:
  - Broad `except Exception: pass` — silently swallows all errors with no logging.
  - The `100x100` → `600x600` string replacement is fragile if Apple changes URL scheme.
  - **Code duplication**: This is the third place iTunes API calling logic appears (also in `ocr.py`).

#### `ocr.py` (269 lines) — Screenshot OCR (Windows-only)

- **Quality**: Creative alternative input path. Good `disperse_timestamps` utility.
- **Pipeline**: `run_windows_ocr()` (PowerShell subprocess → Windows.Media.Ocr) → `parse_tracks_from_lines()` (pair consecutive lines, query iTunes, validate match) → `build_recap_slideshow()`.
- **Issues**:
  - **Platform-locked**: Windows-only with no platform guard or fallback.
  - **Security**: PowerShell script embeds file path via f-string with only single-quote escaping — potential injection vector for unusual paths.
  - **Colon filter too aggressive**: Lines containing `:` are skipped (assumed durations like "3:45"), but this incorrectly skips track/artist names with colons (e.g., "Re: Stacks" by Bon Iver).
  - **`pytesseract` not in `requirements.txt`**: The module actually uses Windows native OCR, not pytesseract — but this should be documented.
  - **Duplicate iTunes API logic**: `search_itunes()` here duplicates logic from `art_resolve.py`.
  - `sqlite3_connect_helper` at line 259 creates a raw connection vs. `db.connect()` used elsewhere — inconsistent.

#### `cli.py` (37 lines) — CLI Entry Point

- **Quality**: Simple, clean.
- **Issues**: Hardcoded output path `output/slides/` with no CLI argument to override. No `--date` flag for past dates. No argparse usage at all.

---

### 4.5 Dashboard (`dashboard/`)

#### Tech Stack

- **React 19.2.7** + **TypeScript 6.0.2** + **Vite 8.1.0** + **Tailwind CSS 4.3.1**
- **Linter**: OxLint 1.69.0 (Rust-based, replaces ESLint)
- **Zero runtime dependencies** beyond React + Tailwind (no router, no state lib, no HTTP client lib)

#### Frontend Architecture

**The entire app is ONE component**: `App.tsx` (552 lines). No child components, no custom hooks, no utility files.

**State** (9 `useState` hooks in `App`):

| State | Type | Purpose |
|---|---|---|
| `apiBase` | `string` | Backend URL, persisted to localStorage |
| `days` | `number` | Time window filter (7/14/30 days) |
| `sortBy` | `'plays' \| 'underrated'` | Sorting mode |
| `candidates` | `Candidate[]` | Raw candidate list from API |
| `selectedKeys` | `Set<string>` | Selected track keys |
| `loading` | `boolean` | Loading state for fetch |
| `generating` | `boolean` | Loading state for generation |
| `error` | `string \| null` | Error message |
| `successSummary` | `any` | ⚠️ Typed as `any` — success response |

**API Integration** (2 endpoints):
- `GET /api/candidates?days={N}` — fetches candidate tracks
- `POST /api/generate` — sends selected tracks, receives slide summary

**UI/UX Design**:
- Dark theme (`#0f1115` background)
- Purple/pink accent color scheme
- Responsive grid: 1 sidebar + 3 main columns
- Track list with album art thumbnails, genre pills, play counts, popularity bars
- Quick select shortcuts (Top 4/8/12/16)
- "Underrated" sort mode: `play_count / max(popularity, 1)`
- Sticky header with backdrop blur
- Gradient "Generate" CTA button

#### Issues

1. **Monolithic 552-line component**: Should decompose into `TrackList`, `TrackRow`, `ControlPanel`, `RecapSummary`, `Header` components.
2. **`successSummary` typed as `any`**: Should be `{ slide_count: number; out_dir: string }`.
3. **`err: any` in catch blocks**: Should use `unknown` and type-narrow.
4. **`useEffect` stale closure bug**: `fetchCandidates` captures `apiBase` but the effect only depends on `[days]`. If user changes API base, it won't re-fetch until `days` changes.
5. **No `useMemo` on expensive sorts**: `getSortedCandidates()` creates a new sorted array on every render.
6. **`strict: true` not enabled in tsconfig**: `strictNullChecks`, `noImplicitAny`, etc. are all OFF — reduces TypeScript's value significantly.
7. **Inline SVGs everywhere**: 6+ SVG icons inlined in JSX. Should use the `icons.svg` file in `public/`.
8. **Unused assets**: `src/assets/hero.png`, `react.svg`, `vite.svg` — leftover Vite template files.
9. **No loading state or error boundary**: Blank screen during API fetch. No React Error Boundary for crash recovery.
10. **No auto-refresh or manual refresh button**: Data fetched once on load.
11. **Dashboard README is boilerplate**: Default Vite template README, not project-specific docs.
12. **`App.css` exists but is never imported**: Empty file with placeholder comment. Should be deleted.
13. **Zero tests for frontend code**.

---

## 5. Test Suite Assessment

### Coverage Summary

| Module | Test Files | Tests | Key Coverage | Notable Gaps |
|---|---|---|---|---|
| `db.py` (398 lines) | 4 files | ~15 | Migration, dedup, featured, window, insert | `connect()`, `latest_played_at()`, `play_count()`, `get_cached_genres()`, `cache_artist()`, `distinct_artist_names()`, `bucket_distribution()` |
| `text_norm.py` | 1 file | 6 | All normalization rules | Unicode normalization |
| `logger.py` (127 lines) | **0 files** | **0** | **NONE** | `log_recent_plays()`, `_resolve_genre()`, `_primary_image_url()`, `_iso_to_unix_ms()` |
| `config.py` (92 lines) | **0 files** | **0** | **NONE** | `assert_credentials`, `resolve_export_path`, `get_lastfm_user` |
| `spotify_client.py` | **0 files** | **0** | **NONE** | `get_client()` (auth wiring — understandable) |
| `run_bidaily.py` | 1 file | 2 | Happy path, skip flags | CLI arg parsing, error branches |
| `dashboard_server.py` | 1 file | 2 | GET candidates, static files | POST endpoint, error paths, CORS preflight, welcome page |
| `ingest/*` | 6 files | ~31 | Import, enrichment, hardening, genres, noise | Network timeouts, API pagination errors |
| `render/*` | 5 files | ~19 | Art, card, collage, colors, fonts, demo | Visual correctness, error paths, wrong-sized cards |
| `slideshow/*` | 6 files | ~17 | Selection, window, builder, OCR, art resolve | Mid-pipeline failures, 0 candidates, same-genre-only |
| `dashboard/src/*` | **0 files** | **0** | **NONE** | Entire frontend untested |

**Total: ~96 test functions across 26 active test files**

### Test Quality Highlights

**Excellent patterns**:
- **Dependency injection throughout**: Almost every external dependency is injected as a parameter rather than mocked at module level. `FakeSpotify`, `RateLimitedSpotify`, `BadRequestSpotify`, `ExplodingSpotify` — well-designed stubs.
- **In-memory SQLite**: Nearly all DB tests use `:memory:` databases. One test deliberately uses a file-based DB to verify commit semantics across separate connections — very thoughtful.
- **Pixel-level image verification**: `test_collage_quadrant_placement` checks specific pixel colors at quadrant centers.
- **Idempotency verified**: Both import and schema migration are tested for safe re-runs.
- **Best test file**: `test_enrich_hardening.py` (176 lines, 8 tests) — thorough coverage of backoff, deferral, stop-early, incremental commits. This is the gold standard for the suite.

**Fragile tests**:
1. `test_dashboard_server.py:test_static_file_serving` depends on `dashboard/dist/index.html` existing on the real filesystem. The weak assertion `b"html" in content.lower()` passes for both the real app and the fallback welcome page.
2. `test_run_bidaily.py` mock signatures don't match real function contracts — `lambda *a, **kw` swallows anything.
3. `test_ocr.py:test_parse_tracks_from_lines_mocked` is coupled to exact query string construction and whitespace.

### Missing Test Infrastructure

- **No `conftest.py`**: Shared fixtures (temp DB setup, mock data factories) duplicated across files.
- **No `pytest-cov`**: No coverage measurement in `requirements-dev.txt`.
- **No `mypy` or `ruff`**: Type hints exist but no static analysis tools configured.
- **No frontend tests**: Dashboard has zero test coverage.

---

## 6. Cross-Cutting Concerns

### 6.1 Error Handling — Inconsistent

The codebase uses three different strategies without clear rules:

| Pattern | Where Used | Risk |
|---|---|---|
| **Fail-soft** (return `None`/`[]`, `except: pass`) | `lastfm_client`, `art_resolve`, `config.get_lastfm_user` | Errors silently swallowed; debugging is harder |
| **Fail-hard** (`SystemExit`, raw exception) | `config.assert_credentials`, `spotify_client` | Crashes the pipeline |
| **Log + continue** | `run_bidaily`, `enrich_cli` (transient handling) | Best approach but not universal |

The enrichment pipeline's transient-vs-permanent failure distinction is the most sophisticated error handling — it should be the model for other modules.

### 6.2 Logging — Absent

The entire codebase uses `print()` / `print(..., file=sys.stderr)`. There is no `logging` framework usage anywhere. For a pipeline that runs as a Task Scheduler job, proper file-backed logging with levels would be significantly more robust.

### 6.3 Dependency Management

**`requirements.txt`** (3 pinned dependencies):
```
spotipy==2.24.0
python-dotenv==1.0.1
Pillow==10.4.0
```

- Pinned to exact versions — good for reproducibility.
- **Missing**: No `flask`, `flask-cors`, or `requests` — the server uses stdlib `http.server`, and `requests` is a transitive dep of `spotipy`.
- No lock file (`pip-tools` or `pip freeze`).

**`requirements-dev.txt`**: Only `pytest==8.3.2`. No `pytest-cov`, `mypy`, `ruff`, `black`, or any quality tooling.

### 6.4 Security

| Aspect | Status | Notes |
|---|---|---|
| SQL injection | ✅ Safe | Parameterized `?` placeholders everywhere |
| Credentials | ✅ Safe | `.env` file, gitignored |
| CORS | ⚠️ Wide open | `Access-Control-Allow-Origin: *` on dashboard server |
| Path traversal | ❌ Vulnerable | `startswith()` string check in `dashboard_server.py` — bypassable on Windows |
| Debug mode | ⚠️ Risk | Dashboard server has no debug flag, but `http.server` in dev mode |
| OCR path injection | ⚠️ Risk | PowerShell script embeds file path via f-string |
| `innerHTML` / XSS | ✅ Low risk | Dashboard only renders data from own API |

### 6.5 Performance

| Aspect | Status | Notes |
|---|---|---|
| XML parsing | ✅ Good | `iterparse` + `root.clear()` for constant memory |
| Art caching | ✅ Good | SHA-1 hash → disk cache |
| Font caching | ✅ Good | Module-level dict cache |
| Gradient rendering | ✅ Good | 1-pixel column + NEAREST stretch (efficient) |
| `canonical_plays` | ⚠️ Concern | Full table load into memory — O(n) per call |
| `window_track_candidates` | ⚠️ Concern | Calls `canonical_plays` without start filter — wasted work |
| Double XML parse | ⚠️ Waste | `_count_tracks` + `iter_scrobbles` each parse 91 MB file |
| Dashboard server | ⚠️ Blocking | Single-threaded, blocks on Spotify API calls |
| Text truncation | ⚠️ Minor | O(n²) character-by-character — fine for short strings |

### 6.6 Documentation Quality

| Document | Quality | Notes |
|---|---|---|
| `README.md` | ⭐⭐⭐⭐⭐ | Comprehensive: setup, usage, architecture, data model, known issues |
| `CLAUDE.md` | ⭐⭐⭐⭐⭐ | Excellent agent guidance: original idea, constraints, stack conventions |
| Design specs (3) | ⭐⭐⭐⭐⭐ | Thorough: module structure, algorithms, success criteria, rationale |
| Implementation plans (3) | ⭐⭐⭐⭐⭐ | Full TDD code for every task, self-review sections |
| Task briefs/reports (16) | ⭐⭐⭐⭐⭐ | Complete audit trail of every decision and outcome |
| Handoff doc | ⭐⭐⭐⭐⭐ | Self-contained context + 4 actionable work items |
| `future_ideas.md` | ⭐⭐⭐⭐ | 5 creative feature proposals (TikTok upload, MP4 video, bot) |
| Dashboard README | ⭐⭐ | Default Vite template boilerplate — not project-specific |
| API documentation | ❌ Missing | No docs for `GET /api/candidates` or `POST /api/generate` |
| Changelog | ❌ Missing | No version numbering or changelog |

---

## 7. Issues & Recommendations

### 🔴 Critical Issues (2)

| # | Issue | Location | Impact | Recommendation |
|---|---|---|---|---|
| 1 | **Recap date format crash**: `build_recap_slideshow` stores `"recap-2026-06-25"` in `featured_tracks`, but `_novelty()` calls `date.fromisoformat()` on it → `ValueError` | `builder.py` L167, `selector.py` L14 | Recap tracks crash novelty calculation on next regular slideshow run | Store ISO date only, use a separate column for recap flag |
| 2 | **Path traversal vulnerability**: `startswith()` string check bypasses path validation on Windows | `dashboard_server.py` static file handler | Arbitrary file read if server is network-accessible | Use `Path.is_relative_to()` (Python 3.9+) |

### 🟡 Important Issues (10)

| # | Issue | Location | Impact |
|---|---|---|---|
| 3 | **`canonical_plays` loads ALL plays into memory** and `window_track_candidates` re-processes the full set | `db.py` | Performance degrades as data grows (currently ~108K plays) |
| 4 | **Novelty bug**: Tracks featured today get `novelty=1.0` (no suppression) — can be re-selected immediately | `selector.py` L15-16 | Unexpected re-featuring on same-day re-runs |
| 5 | **DRY violation**: `build_slideshow` and `build_recap_slideshow` share ~50 duplicated lines | `builder.py` | Maintenance burden; bugs fixed in one may be missed in the other |
| 6 | **No `logging` framework**: Entire codebase uses `print()` / `print(stderr)` | All modules | Debugging task scheduler jobs is difficult; no log levels or rotation |
| 7 | **Mixed connection patterns**: Some functions use `db.connect()`, others require `conn` parameter | `db.py` | Hard to compose operations in transactions; unclear ownership |
| 8 | **Three duplicate iTunes API implementations** | `art_resolve.py`, `ocr.py` (2 places) | DRY violation; inconsistent error handling across copies |
| 9 | **Two duplicate `_default_fetch` functions** | `lastfm_import.py`, `lastfm_client.py` | Same function defined twice |
| 10 | **`logger.py` has zero tests** | `tests/` | Core Spotify ingest entry point is entirely untested |
| 11 | **552-line monolithic `App.tsx`** | `dashboard/src/App.tsx` | Poor maintainability; no component reuse |
| 12 | **`useEffect` stale closure**: Effect depends on `[days]` but captures `apiBase` | `dashboard/src/App.tsx` L29-31 | Changing API base URL doesn't trigger refetch |

### 🟢 Minor / Nice-to-Have (10)

| # | Issue | Location | Suggestion |
|---|---|---|---|
| 13 | Double XML parse (91 MB file parsed twice) | `lastfm_import.py` | Count during iteration |
| 14 | Cross-package import: `ingest` → `render.art.is_placeholder` | `lastfm_import.py` | Move `is_placeholder` to shared utility |
| 15 | Dead imports: `os` in `dashboard_server.py`, `datetime`/`timezone` in `run_bidaily.py` | Multiple | Remove |
| 16 | `popularity` column dead code path (`popularity=None` hardcoded) | `logger.py`, `db.py` | Clean up or remove column |
| 17 | CLI missing `--date` flag for past-date slide generation | `slideshow/cli.py` | Add argparse |
| 18 | `strict: true` not enabled in dashboard tsconfig | `dashboard/tsconfig.app.json` | Enable for proper TypeScript safety |
| 19 | Unused `App.css` and template assets in dashboard | `dashboard/src/` | Delete `App.css`, `hero.png`, `react.svg`, `vite.svg` |
| 20 | OCR colon filter too aggressive (skips "Re: Stacks") | `slideshow/ocr.py` L131 | Use duration-specific regex instead of `:` substring check |
| 21 | No `conftest.py` for shared test fixtures | `tests/` | Extract `_conn()`, `_play()`, `FakeSpotify` etc. |
| 22 | Dashboard README is Vite boilerplate | `dashboard/README.md` | Write project-specific docs |

---

## 8. Summary Scorecard

| Category | Score | Notes |
|---|---|---|
| **Architecture** | ⭐⭐⭐⭐ (4/5) | Clean separation, unidirectional data flow, excellent DI pattern. Weakened by connection management inconsistency and cross-package coupling. |
| **Code Quality** | ⭐⭐⭐⭐ (4/5) | Well-structured, typed, docstrings throughout. Some DRY violations and untyped dicts. |
| **Test Coverage** | ⭐⭐⭐½ (3.5/5) | 96 tests across 26 files with excellent patterns (DI, in-memory DB, stubs). Gaps: `logger.py` (0 tests), `config.py` (0 tests), dashboard (0 tests). |
| **Documentation** | ⭐⭐⭐⭐⭐ (5/5) | Exceptional — design specs, implementation plans, task briefs/reports, handoff docs, agent guidelines. Best-documented personal project I've reviewed. |
| **Error Handling** | ⭐⭐⭐ (3/5) | Enrichment pipeline is excellent (transient/permanent distinction, circuit breaker). Other modules are inconsistent (silent swallowing vs. raw exceptions). |
| **Security** | ⭐⭐⭐ (3/5) | Good SQL parameterization. Path traversal vulnerability and wide-open CORS are notable risks. |
| **Dependencies** | ⭐⭐⭐⭐ (4/5) | Minimal and pinned. Missing `pytesseract` doc. No `mypy`/`ruff` dev tooling. |
| **Performance** | ⭐⭐⭐½ (3.5/5) | Good for current scale (efficient XML parsing, art caching, gradient rendering). `canonical_plays` full-table scan will degrade at larger scale. |
| **Agent Process** | ⭐⭐⭐⭐⭐ (5/5) | Methodical SDD workflow: spec → plan → TDD → report. Strict bottom-up layering. Conservative technology choices. Good judgment on rejected reviewer feedback. |
| **Frontend** | ⭐⭐⭐ (3/5) | Functional and visually polished. Monolithic component, missing strict TypeScript, stale closure bug, no tests. |

### Overall: ⭐⭐⭐⭐ (4/5)

**This is a well-built personal project with exceptional documentation and clean architecture.** The agents followed a disciplined development process with proper design specs, phased implementation, strict TDD (in later phases), and post-implementation review. The most impactful improvements would be:

1. **Fix the recap date crash** (Critical #1) — immediate data integrity risk
2. **Fix the path traversal vulnerability** (Critical #2) — security risk if server is accessible
3. **Standardize error handling** around the enrichment pipeline's transient/permanent pattern
4. **Add `logging` framework** to replace `print()` statements
5. **Decompose the dashboard** into proper React components

---

> **Note**: This review is read-only. No changes have been implemented. Awaiting green light on which items to address.
