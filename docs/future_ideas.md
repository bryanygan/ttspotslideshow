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

---

## 🔜 Proposed (Ranked by Priority)

| Rank | Idea | Impact | Effort | Est. Time |
|------|------|--------|--------|-----------|
| 1 | Audio snippet sync for MP4 videos | High | Medium | 2–3 hrs |
| 2 | Semi-automated TikTok uploading (Playwright) | High | High | 4–6 hrs |
| 3 | ThreadingHTTPServer for dashboard | Medium | Low | 15 min |
| 4 | Retry logic for scheduled Spotify logging | Medium | Low | 30 min |
| 5 | Cross-platform OCR fallback (Tesseract) | Medium | Medium | 1–2 hrs |
| 6 | Bulk art override upload | Low | Low | 30 min |
| 7 | Telegram/Discord OCR bot | Medium | Medium | 2–3 hrs |
| 8 | Replace deprecated popularity field | Medium | Medium | 1–2 hrs |
| 9 | Caption preview in dashboard Create tab | Low | Low | 20 min |
| 10 | Rate limiting on dashboard API | Medium | Low | 30 min |

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

### 3. ThreadingHTTPServer for Dashboard
* Swap `http.server.HTTPServer` for `ThreadingHTTPServer` in `dashboard_server.py` (one-line change).
* Currently the server handles one request at a time — during slide generation (10-30s), other requests queue.
* **Quick win**: Fixes dashboard responsiveness during long generation runs.

### 4. Retry Logic for Scheduled Logging
* Add exponential backoff retry to `logger.py` and `run_bidaily.py` for Spotify API rate limits (429).
* Currently a 429 silently loses a 3-hour window of plays.
* **Quick win**: Prevents data gaps in your listening history.

### 5. Cross-Platform OCR Fallback
* The `run_windows_ocr()` function uses Windows.Media.Ocr via PowerShell — non-portable to Linux/macOS.
* Add a Tesseract (`pytesseract`) fallback or Google Vision API option.
* **Why**: Broadens compatibility if you ever move the pipeline to a different machine.

### 6. Bulk Art Override Upload
* Currently you upload cover art per-track from the dashboard.
* Add a bulk mode: select multiple tracks → upload one image → applies to all (useful for compilation albums where Spotify splits covers).

### 7. Telegram / Discord Integration (Remote Control)
* Connect a simple Discord or Telegram bot to the OCR pipeline.
* Screenshot your queue on your phone → send to bot → bot runs `ocr.py` on your PC → replies with rendered PNG slides.
* **Benefit**: Generate slides on-the-go without opening the dashboard.

### 8. Replace Deprecated Spotify Popularity Field
* Spotify removed `track.popularity` in Feb 2026. Currently defaulting to 50.
* Track a *personal* popularity metric based on play-count percentile across your history so the "underrated score" becomes meaningful again.
* **Impact**: Restores the "Underrated" sort as a useful signal.

### 9. Caption Preview in Dashboard Create Tab
* Show the auto-generated caption + hashtags in the Create tab before generating, so the user can edit or approve it.
* Copy-to-clipboard button for easy pasting into TikTok.

### 10. Rate Limiting on Dashboard API
* The server accepts any request with CORS `*`. If exposed publicly via Cloudflare Tunnel without Cloudflare Access, it's open to abuse.
* Add a simple per-IP rate limiter (e.g., `slowapi` or manual token bucket).
