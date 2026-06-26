# Security Audit & Optimization Recommendations

**Date:** 2026-06-26
**Scope:** Full codebase review — backend server, frontend dashboard, pipeline, data layer
**Status:** Findings only — no changes implemented yet. Awaiting green light.

---

## Table of Contents

1. [Security Vulnerabilities](#1-security-vulnerabilities)
   - [Critical](#critical)
   - [High](#high)
   - [Medium](#medium)
   - [Low / Informational](#low--informational)
2. [Performance & Optimization Opportunities](#2-performance--optimization-opportunities)
3. [UX & Dashboard Improvements](#3-ux--dashboard-improvements)
4. [Architecture & Code Quality](#4-architecture--code-quality)
5. [Reliability & Robustness](#5-reliability--robustness)

---

## 1. Security Vulnerabilities

### Critical

#### C-1: No authentication or authorization on the dashboard server

**File:** `dashboard_server.py`
**Risk:** The HTTP server at `http://localhost:8000` has **zero authentication**. Any process or user on the same machine (or network, if bound to `0.0.0.0`) can:
- Trigger slideshow generation (expensive CPU/image operations)
- Upload arbitrary files via `/api/overrides/upload` and `/api/ocr`
- Read any slide from `output/slides/` via path traversal (see C-2)
- Read any art override from `data/art_overrides/`
- Modify track art in the DB via `/api/art-test/save`

**Impact:** Denial-of-service (flood the generation endpoint), arbitrary file upload (see C-2), data tampering.

**Recommendation:**
- Add a shared secret / API token check (e.g., `Authorization: Bearer <token>` header) validated on every request
- For local-only use, bind to `127.0.0.1` explicitly (currently `""` which binds to all interfaces) in `dashboard_server.py:main()`:
  ```python
  server_address = ("127.0.0.1", port)  # instead of ("", port)
  ```
- Consider rate-limiting the generation endpoints

---

#### C-2: Insufficient upload validation — arbitrary file upload risk

**Files:** `dashboard_server.py` — `handle_post_override_upload()`, `handle_post_ocr()`

**Risk:** The upload endpoint accepts raw binary data and writes it to disk with only a file-extension guess from `Content-Type`. An attacker can:
- Send `Content-Type: image/png` with a `.png` extension containing a polyglot file (e.g., a malicious Python script, HTML with XSS, or a specially crafted image with embedded exploits)
- The file is written to `data/art_overrides/` and later served back via `/api/overrides/<filename>` with `image/png` MIME type — the browser may interpret it differently
- No file size limit is enforced (only `Content-Length > 0` is checked)

The OCR endpoint (`handle_post_ocr()`) has the same issue — writes to `output/ocr_temp/temp_screenshot.png` with no size validation.

**Impact:** Stored XSS (if served as HTML in some contexts), disk exhaustion, potential code execution if the server's MIME handling is bypassed.

**Recommendation:**
- Enforce a maximum file size (e.g., 10 MB) — check `Content-Length` before reading
- Validate the actual file content using `Pillow`'s `Image.open()` to verify it's a real image:
  ```python
  from PIL import Image
  import io
  try:
      img = Image.open(io.BytesIO(file_data))
      img.verify()  # raises on invalid/malformed images
  except Exception:
      return error
  ```
- Restrict allowed extensions to a whitelist (`.png`, `.jpg`, `.jpeg`, `.webp`)
- Rename uploaded files to a UUID to prevent any filename-based attacks

---

### High

#### H-1: Path traversal partially mitigated but with edge cases

**File:** `dashboard_server.py` — `handle_get_slide()`, `handle_static_files()`

**Status:** The code correctly uses `resolve()` + `is_relative_to()` for path containment, which is the right approach. **However**, `handle_get_override()` uses a simpler check:

```python
file_path = (overrides_root / rel).resolve()
if not file_path.is_relative_to(overrides_root) ...
```

This is *generally* safe but doesn't account for Windows-specific path canonicalization edge cases (e.g., `..` with symlinks, short filenames `PROGRA~1`).

**Recommendation:**
- Add the same `try/except` wrapping around the resolve that `handle_get_slide()` has
- Consider adding a filename whitelist for override lookups (only serve files that match the `{artist} - {title}.{ext}` pattern)

---

#### H-2: CORS policy allows all origins (`*`)

**File:** `dashboard_server.py` — `end_headers()`

```python
self.send_header("Access-Control-Allow-Origin", "*")
self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Artist, X-Title")
```

**Risk:** With `Access-Control-Allow-Origin: *`, any website the user visits can make cross-origin requests to the dashboard server running on `localhost:8000`. If the server is ever bound to a non-loopback interface, this becomes a significant CSRF/XSS vector.

**Impact:** A malicious webpage could read the user's listening history, trigger slideshow generation, or upload override files.

**Recommendation:**
- Restrict to specific origins: `Access-Control-Allow-Origin: http://localhost:5173` (Vite dev server) or the production domain
- Add CSRF protection (e.g., a custom header that browsers won't send cross-origin without permission)

---

#### H-3: Spotify credentials and OAuth token stored on disk

**Files:** `config.py`, `.spotify_cache`, `.env`

**Risk:**
- The `.spotify_cache` file contains a valid OAuth refresh token that can be used to impersonate the user's Spotify account
- The `.env` file contains `SPOTIPY_CLIENT_SECRET` in plaintext
- Neither file has restricted file permissions (any user on the machine can read them)

**Impact:** Account compromise — an attacker with local file access could use the Spotify token to read listening history, create playlists, or modify the user's Spotify account.

**Recommendation:**
- Set restrictive file permissions on `.spotify_cache` and `.env` (read-only by owner)
- Add `.spotify_cache` to `.gitignore` (already done — good)
- Document in README that these files should be protected

---

#### H-4: SQL injection via `handle_post_art_test_save()`

**File:** `dashboard_server.py` — `handle_post_art_test_save()`

The endpoint accepts `artist`, `title`, and `album_art_url` from the user and passes them to `db.update_track_art()`:

```python
db.update_track_art(conn, artist, title, album_art_url or "")
```

The DB layer uses parameterized queries (`?` placeholders), so **direct SQL injection is not possible**. However, the `album_art_url` is not validated — a user could inject an arbitrary URL string that gets stored and later used in HTTP requests (`load_art()`), potentially enabling SSRF (Server-Side Request Forgery).

**Impact:** SSRF — an attacker could cause the server to make arbitrary HTTP requests to internal network resources.

**Recommendation:**
- Validate that `album_art_url` matches a known pattern (e.g., starts with `https://i.scdn.co/` for Spotify or `https://is1-ssl.mzstatic.com/` for iTunes)
- Or restrict to known CDN domains

---

### Medium

#### M-1: No input sanitization on `X-Artist` / `X-Title` headers

**File:** `dashboard_server.py` — `handle_post_override_upload()`

Headers are URL-decoded and sanitized for filesystem-illegal characters, but not for XSS if reflected in any HTML response. Currently they're only reflected in JSON, but this could change.

**Recommendation:** Apply HTML-encoding if any user-provided data is ever embedded in HTML responses.

---

#### M-2: SSE endpoint holds connection open indefinitely

**File:** `dashboard_server.py` — `handle_post_generate_stream()`

The SSE loop uses `q.get(timeout=120)` but has no maximum request duration. If the generation thread hangs (e.g., network timeout downloading covers), the HTTP connection stays open.

**Impact:** Connection exhaustion — an attacker could send many requests that each hold a connection open, starving the server.

**Recommendation:**
- Add an absolute timeout (e.g., 5 minutes) after which the SSE loop breaks
- Add a maximum concurrent generation limit (semaphore)

---

#### M-3: Temporary OCR file not cleaned up on crash

**File:** `dashboard_server.py` — `handle_post_ocr()`

The temp file is cleaned in a `finally` block, which is correct. However, if the server crashes between write and cleanup, stale files accumulate in `output/ocr_temp/`.

**Recommendation:** Clean up stale temp files on server startup, or use `tempfile.NamedTemporaryFile` with `delete=True`.

---

#### M-4: `playlist_id` and `export_video` parameters have no validation

**File:** `dashboard_server.py` — both `handle_post_generate()` and `handle_post_generate_stream()`

These values come directly from the JSON payload with no type or range checking. A malformed `playlist_id` (e.g., a very long string) could cause issues in the Spotify API client.

**Recommendation:**
- Validate `playlist_id` is a reasonable Spotify playlist ID format (alphanumeric, < 50 chars)
- Validate `export_video` is a boolean

---

#### M-5: `cover_pool` array can be arbitrarily large

**File:** `dashboard_server.py`

The `cover_pool` field from the request is passed directly into `_collage_art_paths()`, which downloads and caches all URLs. An attacker could send thousands of URLs to trigger mass downloads.

**Recommendation:** Limit `cover_pool` to a reasonable maximum (e.g., 200 items).

---

### Low / Informational

#### L-1: `requirements.txt` includes `imageio[ffmpeg]` but no version pin

The `imageio[ffmpeg]` dependency has no version constraint. A future version could introduce breaking changes or pull in unexpected transitive dependencies.

**Recommendation:** Pin to a known-good version.

---

#### L-2: `.env` file not checked for existence

If `.env` is missing, `load_dotenv()` silently does nothing and the app proceeds with empty credentials, which may cause confusing errors.

**Recommendation:** Fail fast in `config.py` if `.env` doesn't exist.

---

#### L-3: No HTTPS enforcement

The server is plain HTTP. If ever deployed to a network-accessible machine, credentials (including Spotify OAuth tokens in transit) would be sent in cleartext.

**Recommendation:** Document that this server should never be exposed to untrusted networks without a reverse proxy providing TLS.

---

## 2. Performance & Optimization Opportunities

### P-1: Cover art downloads are sequential per-track, not batched

**File:** `slideshow/builder.py` — `_render_and_save()`

The download phase creates a `ThreadPoolExecutor(max_workers=8)` which is good, but the *resolve* phase iterates over all tracks sequentially, calling `resolve_art_url()` for each one. This function may make a Spotify or iTunes API call per track.

**Recommendation:** Batch Spotify API calls where possible. The `sp.tracks()` endpoint already batches 50 tracks at a time — extend this pattern to art resolution.

---

### P-2: No image caching layer for rendered slides

Every call to `generateRecapStream()` re-renders all cards and collages from scratch, even if the same track set was generated before.

**Recommendation:** Add a simple cache key based on the sorted list of track keys + cover settings. If a matching `recap-*` folder already exists, return the existing slides without re-rendering.

---

### P-3: SQLite `canonical_plays()` loads all matching rows into memory

**File:** `db.py` — `canonical_plays()`

For large play histories (thousands of rows), this loads everything into a Python list for deduplication.

**Recommendation:** Use a windowing approach or let SQLite do more of the work with CTEs. For the current scale (personal listening history), this is fine, but it will degrade as the DB grows.

---

### P-4: Video export creates uncompressed frame buffer in memory

**File:** `render/video_export.py`

The current implementation reads each slide image once, then appends the same frame N times (for `duration_per_slide` seconds at 30 fps). This means a 1080p image is duplicated 90 times in the video file.

**Recommendation:** Use FFmpeg directly with `-loop 1 -t 3` per image and a concat filter, which would produce a much smaller file with proper keyframe intervals. The current approach creates bloated MP4s.

---

### P-5: `generateRecapStream()` sends progress events per-track

**File:** `slideshow/builder.py` — `ProgressEmitter.emit()`

Progress events are emitted for *every single track* during resolve, download, and render phases. For a 16-track recap, that's ~48+ SSE events. For larger sets, this floods the network.

**Recommendation:** Throttle progress events to max 1 per 500ms, or emit at coarser milestones (e.g., every 25% of a phase).

---

### P-6: Frontend re-renders on every SSE progress update

**File:** `dashboard/src/lib/useRecap.ts`

Each SSE event triggers four separate `useState` setters (`setProgress`, `setProgressStage`, `setProgressDetail`, `setProgressEta`), causing four React re-renders per event.

**Recommendation:** Use a single state object or `useReducer` to batch updates:
```typescript
const [progress, setProgress] = useState<ProgressState>({
  pct: 0, stage: "", detail: "", eta: null,
});
// Single setter = single re-render per event
```

---

## 3. UX & Dashboard Improvements

### UX-1: No feedback when the dashboard build is missing

**File:** `dashboard_server.py` — `serve_welcome_page()`

The welcome page is well-designed but static. It doesn't auto-detect when `npm run build` has completed.

**Recommendation:** Add a polling mechanism or WebSocket notification that auto-refreshes the page when the build appears.

---

### UX-2: No error recovery for failed SSE stream

**File:** `dashboard/src/lib/api.ts` — `generateRecapStream()`

If the SSE stream disconnects mid-generation (network hiccup, server restart), the frontend throws a generic "Stream ended without a complete or error event" error. The user loses all progress information and must restart.

**Recommendation:**
- Add retry logic with exponential backoff
- Show a "Reconnecting..." state in the UI
- Consider making the generation endpoint resumable (server tracks generation state by session ID)

---

### UX-3: Progress ETA can be wildly inaccurate

**File:** `slideshow/builder.py` — `ProgressEmitter.emit()`

ETA is computed as `elapsed / current * (total - current)`, which assumes linear progress. But cover art downloads (network I/O) are much slower than rendering (CPU), so the ETA jumps dramatically between phases.

**Recommendation:** Use a weighted or exponential moving average that accounts for per-stage historical timing. Or show per-stage ETAs instead of a single global one.

---

### UX-4: No download button for the generated video

**File:** `dashboard/src/options/pocket/PocketDJ.tsx` (and other UI tabs)

When `export_video=True`, the server returns `video_path` in the summary, but the frontend doesn't expose a download link.

**Recommendation:** Add a "Download MP4" button when `summary.video_path` is present, linking to a new `/api/videos/<recap_id>/recap.mp4` endpoint.

---

### UX-5: No pagination or virtualization for large candidate lists

**File:** `dashboard/src/options/pocket/PocketDJ.tsx`

When `days=30` or more, the candidate list can be hundreds of items. All are rendered in the DOM at once.

**Recommendation:** Implement virtual scrolling (e.g., `@tanstack/react-virtual`) or pagination to keep the DOM size manageable.

---

### UX-6: Missing dark/light theme toggle

The dashboard is dark-themed only. For accessibility and user preference, a theme toggle would be valuable.

---

### UX-7: No keyboard shortcuts

Power users would benefit from keyboard shortcuts for common actions: select all, deselect all, generate, toggle cover slide, etc.

---

## 4. Architecture & Code Quality

### A-1: HTTP server is single-threaded for request handling

**File:** `dashboard_server.py` — `HTTPServer`

Python's `HTTPServer` handles one request at a time. If a generation request is in progress (taking 30-60 seconds), all other requests (static files, candidate fetch, art uploads) are blocked.

**Recommendation:** Use `ThreadingHTTPServer` instead:
```python
from http.server import ThreadingHTTPServer
httpd = ThreadingHTTPServer(server_address, DashboardHandler)
```
This is already partially addressed by the SSE endpoint spawning a background thread, but the main request handler is still single-threaded.

---

### A-2: No structured logging

**File:** `logsetup.py`, `dashboard_server.py`

Logging uses `print()` in the server and basic `logging` in the pipeline. There's no structured logging (JSON format), log levels in the server, or request logging.

**Recommendation:**
- Add request logging to the server (method, path, status, duration)
- Use structured JSON logging for easier debugging
- Add `logging.info()` calls for key events (generation started/completed, upload received, etc.)

---

### A-3: `ProgressEmitter` uses `__import__("threading")` dynamically

**File:** `slideshow/builder.py`

```python
self._lock = __import__("threading").Lock()
```

This is unusual and unnecessary — `threading` is already imported at the top of `dashboard_server.py` and could be imported normally in `builder.py`.

**Recommendation:** Replace with a standard `import threading` at the top of the file.

---

### A-4: No API versioning

All endpoints are unversioned (`/api/generate`, `/api/candidates`, etc.). If the API contract changes, older frontend builds will break.

**Recommendation:** Consider `/api/v1/...` prefixing, especially if the server will be accessed by multiple client versions.

---

### A-5: Tight coupling between `dashboard_server.py` and business logic

The server handler directly imports and calls `build_recap_slideshow()`, `ProgressEmitter`, `db`, etc. This makes it hard to test the server independently or swap out the generation backend.

**Recommendation:** Introduce a thin service layer that the handler delegates to. This would also make unit testing the endpoints much easier.

---

## 5. Reliability & Robustness

### R-1: No graceful shutdown for the HTTP server

**File:** `dashboard_server.py` — `main()`

On `KeyboardInterrupt`, the server exits immediately. Any in-progress generation is abandoned mid-flight, potentially leaving corrupted output files.

**Recommendation:**
- Add a shutdown flag that stops accepting new requests but lets in-progress generations complete
- Clean up temp files on shutdown
- Use signal handlers for `SIGTERM` on Linux/macOS

---

### R-2: Thread safety of `db.connect()` in background thread

**File:** `dashboard_server.py` — `handle_post_generate_stream()` → `run_generate()`

SQLite connections are not thread-safe by default. The `run_generate()` thread creates its own `db.connect()` which is correct, but the `result_holder` dict is shared between threads with no synchronization beyond the `queue.Queue`.

**Risk:** Low in practice (Python's GIL protects dict mutations), but worth noting for future changes.

---

### R-3: No retry logic for Spotify/Last.fm API calls

**File:** `spotify_client.py`, `webutil.py`, `ingest/`

All external API calls have `retries=0` or no retry logic. A transient network failure means the track is skipped entirely.

**Recommendation:** Add exponential backoff retry for 429 and 5xx errors (with a reasonable max retries to avoid long hangs).

---

### R-4: `output/` directory can grow unbounded

Every generation creates a new `recap-*` folder with PNG slides (potentially large files). There's no cleanup policy.

**Recommendation:**
- Add a `--cleanup` flag or automatic rotation that keeps only the N most recent recaps
- Or add a "clean up old recaps" button in the dashboard

---

### R-5: No validation that selected tracks have valid `track_key`

**File:** `slideshow/builder.py` — `build_recap_slideshow()`

The `tracks` parameter comes from the frontend JSON payload. If a track is missing `track_key`, `normalize(artist)`, or other expected fields, the code will crash with a `KeyError`.

**Recommendation:** Validate the incoming track objects against an expected schema before passing them to the builder.

---

## Summary of Priority Actions

| Priority | ID | Issue | Effort |
|----------|-----|-------|--------|
| **P0** | C-1 | No authentication on dashboard server | Low |
| **P0** | C-2 | Arbitrary file upload via override/OCR endpoints | Medium |
| **P1** | H-1 | Path traversal edge cases in override handler | Low |
| **P1** | H-2 | CORS allows all origins | Low |
| **P1** | H-4 | SSRF via unvalidated `album_art_url` | Low |
| **P1** | M-2 | SSE connection held open indefinitely | Low |
| **P2** | A-1 | Single-threaded HTTP server | Low |
| **P2** | P-4 | Video export creates bloated MP4s | Medium |
| **P2** | UX-4 | No download button for generated video | Low |
| **P2** | R-4 | Output directory grows unbounded | Low |
| **P3** | P-1 | Cover art resolution not batched | Medium |
| **P3** | P-2 | No rendered slide cache | Medium |
| **P3** | UX-2 | No SSE error recovery | Medium |
| **P3** | A-2 | No structured logging | Medium |

---

*End of audit. Awaiting approval to implement fixes.*
