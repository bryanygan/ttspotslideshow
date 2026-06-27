# Future Ideas & TikTok Automation Suggestions

This document lists future ideas and automation features proposed to extend the Spotify TikTok Slideshow project.
Items are ranked by **Impact × Effort** (High/Medium/Low) and include completion-time estimates.

---

## ✅ Completed

### 1. Real-Time Generation Progress Bar with ETA
* **Status**: Done
* **What**: Replaced the fake client-side progress timer with SSE streaming from the server. The progress bar now shows real stage completion (resolving → downloading → rendering → collage) plus an estimated time remaining.
* **Impact**: High | **Effort**: Medium

### 2. Dynamic Smart Captions & Hashtag Generator
* **Status**: Done
* **What**: `slideshow/caption.py` auto-generates TikTok-ready captions from track metadata — genre-based hashtags (max 5, per TikTok limits), artist callouts, and music emojis. Output included in the API summary as `caption`.
* **Impact**: High | **Effort**: Low

### 3. Video Slide Compilations (MP4 Video Export)
* **Status**: Done
* **What**: `render/video_export.py` uses `imageio[ffmpeg]` to stitch rendered slide PNGs into a 1080×1920 MP4 video (3s per slide, 30fps). Optional via `export_video=True` parameter.
* **Impact**: High | **Effort**: Low
* **Note**: Audio snippet sync (Spotify preview URLs) is a future enhancement — current version is image-only.

### 4. Automated Spotify "Rotation" Playlist Syncer
* **Status**: Done
* **What**: `slideshow/playlist_sync.py` syncs selected tracks to a "Bryan's Bi-Daily Rotation" playlist on Spotify. Auto-creates the playlist on first run. Optional via `playlist_id` parameter.
* **Impact**: High | **Effort**: Low
* **Config**: Added `playlist-modify-public playlist-modify-private` to OAuth scopes.

### 5. Duplicate Prevention
* **Status**: Done
* **What**: Dashboard now shows a "Featured" badge on tracks that appeared in recent recaps (last 14 days), with a count of how many times. Added "No Repeats" smart preset that filters out recently-featured tracks.
* **Impact**: Medium | **Effort**: Low

### 6. Recap History Browser
* **Status**: Done
* **What**: New "History" tab in the bottom nav lists all past recap generations (date, slide count). Clicking one opens a slide gallery view. Powered by new `/api/recap-history` and `/api/recap-history/<id>/slides` endpoints.
* **Impact**: Medium | **Effort**: Low

### 7. ThreadingHTTPServer for Dashboard
* **Status**: Done (was already shipped — `dashboard_server.py` runs on
  `http.server.ThreadingHTTPServer`, so requests no longer queue during long
  slide generation).
* **Impact**: Medium | **Effort**: Low

### 8. Retry Logic for Scheduled Logging
* **Status**: Done
* **What**: `logger.py` now wraps Spotify calls (`current_user_recently_played`
  and per-artist genre lookups) in `with_retry()`, which retries 429s with
  exponential backoff and honours the server's `Retry-After` header. A transient
  rate limit no longer silently drops a window of plays.
* **Impact**: Medium | **Effort**: Low

### 9. Cross-Platform OCR Fallback (Tesseract)
* **Status**: Done
* **What**: `slideshow/ocr.py` adds `run_tesseract_ocr()` (pytesseract) and a
  `run_ocr()` dispatcher: Windows uses the native WinRT engine first and falls
  back to Tesseract; other platforms use Tesseract directly. `dashboard_server`
  and the OCR CLI now call `run_ocr()`. `pytesseract` added to requirements
  (optional; needs the Tesseract binary on PATH for non-Windows hosts).
* **Impact**: Medium | **Effort**: Medium

### 10. Telegram / Discord OCR Bot
* **Status**: Done (Discord, in the `zreatsbot` repo)
* **What**: New `/slides` slash command (`zreatsbot/bot/commands/slides.py`):
  attach a queue/playlist screenshot → the bot shells out to this repo's
  `bot_ocr_entry.py` (subprocess, to avoid the shared `db` module name clash) →
  OCR + render → replies with the PNG slides and the generated caption.
  Configured via `TTSPOT_REPO_PATH` / `TTSPOT_PYTHON` env vars; owner-gated.
* **Impact**: Medium | **Effort**: Medium

### 11. Rate Limiting on Dashboard API
* **Status**: Done
* **What**: `dashboard_server.py` adds a thread-safe per-IP token-bucket
  `RateLimiter` (60 burst, refilling 1/sec) checked at the top of every GET/POST;
  over-budget clients get a 429 with `Retry-After`. Guards the open-CORS server
  if it's ever exposed publicly.
* **Impact**: Medium | **Effort**: Low

### 13. Replace Deprecated Spotify Popularity Field
* **Status**: Done
* **What**: Spotify removed `track.popularity` (Feb 2026). Restored a global
  popularity signal from Last.fm `track.getInfo` listeners (primary) with a
  ListenBrainz metadata-lookup → popularity-API fallback, log-normalized to
  0–100 (`ingest/popularity.py`). Cached per-track in a new `track_popularity`
  table; filled by a resumable `python -m ingest.enrich_popularity` CLI wired
  into `run_bidaily.py`. The dashboard now reads the cache (dropping the dead
  Spotify call); unmatched tracks read as neutral 50. Restores the "Underrated"
  sort. Added `LISTENBRAINZ_TOKEN` to config/.env.
* **Impact**: Medium | **Effort**: Medium

### 12. Playlist Parsing and Generation
* **Status**: Done
* **What**: `slideshow/playlist_parse.py` resolves a Spotify playlist URL/ID (full
  pagination) or a Last.fm user loved/library URL into selectable candidates.
  New endpoints `POST /api/playlist/parse` and `POST /api/playlist/save`
  (save-back via `playlist_sync.save_tracks_to_playlist`). Dashboard gets a new
  **Playlist** view to paste a link, load tracks into picks, and save the current
  picks to a new Spotify playlist. Re-added the `playlist-modify-*` OAuth scopes
  (one-time re-auth required).
* **Impact**: High | **Effort**: Medium

---

## 🔜 Proposed (Ranked by Priority)

| Rank | Idea | Impact | Effort | Est. Time |
|------|------|--------|--------|-----------|
| 1 | Audio snippet sync for MP4 videos | High | Medium | 2–3 hrs |
| 2 | Semi-automated TikTok uploading (Playwright) | High | High | 4–6 hrs |
| 3 | Bulk art override upload | Low | Low | 30 min |
| 4 | Caption preview in dashboard Create tab | Low | Low | 20 min |

### 1. Audio Snippet Sync for MP4 Videos
* Extend `video_export.py` to download Spotify `preview_url` clips (30s each), trim to fit slide duration, and overlay audio onto each slide segment using `moviepy` or `ffmpeg`.
* Each card transitions as the next song preview starts.
* **Why first**: The video export infrastructure is already in place; audio is the missing piece for a truly engaging TikTok video.

### 2. Semi-Automated TikTok Uploading (Playwright)
* Since TikTok's official Content Posting API is restricted to business accounts, automate uploads via browser automation:
  1. Save TikTok session cookies once.
  2. Headless browser loads cookies, navigates to TikTok upload portal.
  3. Uploads generated images (or MP4) from `output/slides/<recap-id>/`.
  4. Auto-fills the generated caption + hashtags and hits **Post**.
* **Benefit**: Complete end-to-end automation from music capture to social media publication.

### 3. Bulk Art Override Upload
* Currently you upload cover art per-track from the dashboard.
* Add a bulk mode: select multiple tracks → upload one image → applies to all (useful for compilation albums where Spotify splits covers).

### 4. Caption Preview in Dashboard Create Tab
* Show the auto-generated caption + hashtags in the Create tab before generating, so the user can edit or approve it.
* Copy-to-clipboard button for easy pasting into TikTok.
