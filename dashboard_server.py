import json
import sys
import time
import threading
import queue
import re
import shutil
import logging
from collections import deque
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
from render.art import find_override_art

import config
import db


class RateLimiter:
    """Thread-safe per-IP token bucket.

    Each IP gets a bucket of ``capacity`` tokens that refills at ``refill_rate``
    tokens/second. One request costs one token; when a bucket is empty the
    request is rejected. This is a lightweight guard against accidental hammering
    or abuse when the server is exposed publicly (e.g. via a Cloudflare Tunnel)
    without an auth layer in front of it.
    """

    def __init__(self, capacity: int = 60, refill_rate: float = 1.0):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self._buckets: dict[str, tuple[float, float]] = {}  # ip -> (tokens, last_ts)
        self._lock = threading.Lock()

    def allow(self, ip: str) -> bool:
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(ip, (self.capacity, now))
            # Refill based on elapsed time, capped at capacity.
            tokens = min(self.capacity, tokens + (now - last) * self.refill_rate)
            if tokens < 1.0:
                self._buckets[ip] = (tokens, now)
                return False
            self._buckets[ip] = (tokens - 1.0, now)
            return True


# Shared limiter instance. ~60 req burst, refilling 1/sec — generous for normal
# dashboard use, but caps runaway/abusive clients.
RATE_LIMITER = RateLimiter(capacity=60, refill_rate=1.0)

# Only one on-demand logger refresh may run at a time (double-taps on the
# dashboard button, or a refresh overlapping the scheduled bi-daily run).
LOGGER_REFRESH_LOCK = threading.Lock()


# --- Bi-daily on-demand run state -----------------------------------------
# The dashboard can trigger the bi-daily pipeline and poll its status. Only one
# run at a time; INFO logs are captured into a ring buffer for the UI to show.
_BIDAILY_LOCK = threading.Lock()
_BIDAILY_STATE = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "ok": None,
    "error": None,
    "log": deque(maxlen=1),  # replaced per run
}


class _ListLogHandler(logging.Handler):
    """Capture formatted log records into a bounded deque for dashboard polling."""

    def __init__(self, sink):
        super().__init__()
        self.sink = sink

    def emit(self, record):
        try:
            self.sink.append(self.format(record))
        except Exception:
            pass


def _run_bidaily_pipeline(skip_spotify, skip_lastfm, skip_popularity):
    """Run the bi-daily pipeline in a worker thread, capturing logs + status."""
    from run_bidaily import run_pipeline

    log_lines = deque(maxlen=300)
    handler = _ListLogHandler(log_lines)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    )
    # Attach to the root logger only: run_bidaily's logger and the nested module
    # loggers (db, ingest, slideshow) all propagate to root, so this captures
    # every record exactly once (attaching to both would double each line).
    root = logging.getLogger()
    root.addHandler(handler)
    if root.level == logging.NOTSET or root.level > logging.INFO:
        root.setLevel(logging.INFO)

    with _BIDAILY_LOCK:
        _BIDAILY_STATE.update(
            running=True, started_at=time.time(), finished_at=None,
            ok=None, error=None, log=log_lines,
        )
    try:
        run_pipeline(
            skip_spotify=skip_spotify, skip_lastfm=skip_lastfm,
            skip_popularity=skip_popularity,
        )
        with _BIDAILY_LOCK:
            _BIDAILY_STATE.update(running=False, finished_at=time.time(), ok=True)
    except Exception as e:
        import traceback
        log_lines.append("ERROR: " + str(e))
        log_lines.append(traceback.format_exc())
        with _BIDAILY_LOCK:
            _BIDAILY_STATE.update(
                running=False, finished_at=time.time(), ok=False, error=str(e),
            )
    finally:
        root.removeHandler(handler)


_cached_handler_cls = None


def DashboardHandler(request, client_address, server):
    global _cached_handler_cls
    if _cached_handler_cls is None:
        dct = {k: v for k, v in DashboardHandlerHelper.__dict__.items() if not k.startswith('__')}
        _cached_handler_cls = type('DashboardHandler', (BaseHTTPRequestHandler,), dct)
    _cached_handler_cls(request, client_address, server)


class DashboardHandlerHelper:

    def _rate_limited(self) -> bool:
        """Return True (and send a 429) if this client is over its rate budget."""
        ip = self.client_address[0] if self.client_address else "unknown"
        if RATE_LIMITER.allow(ip):
            return False
        self.send_response(429)
        self.send_header("Content-Type", "application/json")
        self.send_header("Retry-After", "1")
        self.end_headers()
        self.wfile.write(json.dumps({"error": "Rate limit exceeded. Slow down."}).encode("utf-8"))
        return True

    def end_headers(self):
        # Inject CORS headers on every response
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Artist, X-Title")
        BaseHTTPRequestHandler.end_headers(self)

    def do_OPTIONS(self):
        print(f"[CORS OPTIONS] Preflight request received for path: {self.path}", flush=True)
        self.send_response(200)
        self.end_headers()

    def log_message(self, fmt, *args):
        # Suppress high-frequency polling endpoints from the access log so
        # dashboard.log doesn't fill with health/status pings.
        try:
            msg = fmt % args
        except Exception:
            msg = fmt
        if "/api/health" in msg or "/api/bidaily/status" in msg:
            return
        BaseHTTPRequestHandler.log_message(self, fmt, *args)

    def do_GET(self):
        if self._rate_limited():
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/candidates":
            self.handle_get_candidates(parsed)
        elif parsed.path.startswith("/api/slides/"):
            self.handle_get_slide(parsed)
        elif parsed.path.startswith("/api/overrides/"):
            self.handle_get_override(parsed)
        elif parsed.path == "/api/recap-history":
            self.handle_get_recap_history()
        elif parsed.path.startswith("/api/recap-history/"):
            self.handle_get_recap_slides(parsed)
        elif parsed.path == "/api/health":
            self.handle_get_health()
        elif parsed.path == "/api/bidaily/history":
            self.handle_get_bidaily_history()
        elif parsed.path == "/api/bidaily/status":
            self.handle_get_bidaily_status()
        elif parsed.path == "/api/art-proxy":
            self.handle_get_art_proxy(parsed)
        else:
            self.handle_static_files(parsed)

    def do_POST(self):
        if self._rate_limited():
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/generate":
            self.handle_post_generate()
        elif parsed.path == "/api/generate-stream":
            self.handle_post_generate_stream()
        elif parsed.path == "/api/overrides/upload":
            self.handle_post_override_upload()
        elif parsed.path in ("/api/art-test/save", "/api/track/confirm"):
            self.handle_post_art_test_save()
        elif parsed.path == "/api/ocr":
            self.handle_post_ocr()
        elif parsed.path == "/api/playlist/parse":
            self.handle_post_playlist_parse()
        elif parsed.path == "/api/playlist/save":
            self.handle_post_playlist_save()
        elif parsed.path == "/api/search/spotify":
            self.handle_post_spotify_search()
        elif parsed.path == "/api/logger/refresh":
            self.handle_post_logger_refresh()
        elif parsed.path == "/api/caption":
            self.handle_post_caption()
        elif parsed.path == "/api/bidaily/run":
            self.handle_post_bidaily_run()
        else:
            self.send_error(404, "Not Found")

    def handle_get_candidates(self, parsed):
        query = parse_qs(parsed.query)
        try:
            days = int(query.get("days", [7])[0])
        except (ValueError, TypeError):
            days = 7

        try:
            with db.connect() as conn:
                if days < 0:
                    limit = -days
                    print(f"[CANDIDATES] Fetching most recent {limit} plays", flush=True)
                    candidates = db.recent_track_candidates(conn, limit)
                else:
                    now_unix = int(time.time())
                    start_unix = now_unix - days * 86400
                    print(f"[CANDIDATES] Fetching window of {days} days (start_unix={start_unix})", flush=True)
                    candidates = db.window_track_candidates(conn, start_unix)
                featured = db.featured_history(conn)
                recent_featured = db.recent_featured_history(conn, last_n_days=14)
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        # Popularity now comes from the track_popularity cache (Last.fm +
        # ListenBrainz), filled by ingest.enrich_popularity. Spotify removed
        # track.popularity (Feb 2026), so there's no live call here anymore.
        pop_cache = {}
        try:
            with db.connect() as conn:
                for c in candidates:
                    row = db.get_track_popularity(conn, c["track_key"])
                    if row is not None and row["popularity"] is not None:
                        pop_cache[c["track_key"]] = row["popularity"]
        except Exception as pop_err:
            print(f"Failed to read cached popularity: {pop_err}", file=sys.stderr)

        # Decorate candidates with popularity, last_featured, and overrides details
        for c in candidates:
            # Unmatched/uncached tracks read as neutral 50, never as obscure.
            c["popularity"] = pop_cache.get(c["track_key"], 50)
            c["last_featured"] = featured.get(c["track_key"], None)

            rf = recent_featured.get(c["track_key"])
            c["recently_featured"] = rf is not None
            c["times_featured"] = rf["times_featured"] if rf else 0

            # Check for manual cover art overrides
            override_path = find_override_art(c["artist"], c["title"])
            if override_path:
                c["album_art_url"] = f"/api/overrides/{override_path.name}"

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"candidates": candidates}).encode("utf-8"))

    def handle_post_generate(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        try:
            payload = json.loads(body)
            tracks = payload.get("tracks", [])
            cover_title = payload.get("cover_title", None)
            cover_subtitle = payload.get("cover_subtitle", None)
            cover_theme = payload.get("cover_theme", None)
            watermark = payload.get("watermark", None)
            cover_pool = payload.get("cover_pool", None)
            playlist_id = payload.get("playlist_id", None)
            export_video = payload.get("export_video", False)
            layout = payload.get("layout", "2x2")
            cover_only = payload.get("cover_only", False)
            cover_columns = int(payload.get("cover_columns", 5))
            cover_rows = int(payload.get("cover_rows", 9))
            width = int(payload.get("width", 1080))
            height = int(payload.get("height", 1700))
        except Exception as e:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"error": f"Invalid JSON payload: {e}"}).encode(
                    "utf-8"
                )
            )
            return

        if not tracks and not cover_only:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {"error": "No tracks provided for generating recap."}
                ).encode("utf-8")
            )
            return

        from slideshow.builder import build_recap_slideshow
        try:
            with db.connect() as conn:
                out_root = Path("output") / "slides"
                summary = build_recap_slideshow(
                    conn, out_root, tracks,
                    cover_title=cover_title, cover_subtitle=cover_subtitle,
                    cover_theme=cover_theme, watermark=watermark,
                    cover_pool=cover_pool, playlist_id=playlist_id,
                    export_video=export_video, layout=layout,
                    cover_only=cover_only, cover_columns=cover_columns,
                    cover_rows=cover_rows,
                    width=width, height=height
                )
        except Exception as e:
            from slideshow.builder import MissingCoverError, UnconfirmedCoverError
            if isinstance(e, UnconfirmedCoverError):
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps({
                        "error": "unconfirmed_covers",
                        "unconfirmed_covers": e.unconfirmed_tracks
                    }).encode("utf-8")
                )
                return

            if isinstance(e, MissingCoverError):
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps({
                        "error": "Missing album cover art",
                        "missing_covers": e.missing_tracks
                    }).encode("utf-8")
                )
                return

            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        # Expose each rendered slide as a GET-able URL so the dashboard can show
        # the images (and the user can save them straight to their phone's Photos).
        recap_id = Path(summary["out_dir"]).name
        slides = [
            f"/api/slides/{recap_id}/slide_{i}.png"
            for i in range(1, summary["slide_count"] + 1)
        ]

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(
            json.dumps(
                {"status": "success", "summary": summary, "slides": slides}
            ).encode("utf-8")
        )

    def handle_post_generate_stream(self):
        """SSE-based streaming endpoint that emits real-time progress events
        during slideshow generation, then returns the final result."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        try:
            payload = json.loads(body)
            tracks = payload.get("tracks", [])
            cover_title = payload.get("cover_title", None)
            cover_subtitle = payload.get("cover_subtitle", None)
            cover_theme = payload.get("cover_theme", None)
            watermark = payload.get("watermark", None)
            cover_pool = payload.get("cover_pool", None)
            playlist_id = payload.get("playlist_id", None)
            export_video = payload.get("export_video", False)
            layout = payload.get("layout", "2x2")
            cover_only = payload.get("cover_only", False)
            cover_columns = int(payload.get("cover_columns", 5))
            cover_rows = int(payload.get("cover_rows", 9))
            width = int(payload.get("width", 1080))
            height = int(payload.get("height", 1700))
        except Exception as e:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"error": f"Invalid JSON payload: {e}"}).encode("utf-8")
            )
            return

        if not tracks and not cover_only:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"error": "No tracks provided for generating recap."}).encode("utf-8")
            )
            return

        from slideshow.builder import build_recap_slideshow, ProgressEmitter
        # Set up SSE response
        q = queue.Queue()
        result_holder = {"summary": None, "slides": None, "error": None}

        def progress_cb(event):
            q.put(("progress", event))

        emitter = ProgressEmitter(callback=progress_cb)

        def run_generate():
            try:
                with db.connect() as conn:
                    out_root = Path("output") / "slides"
                    summary = build_recap_slideshow(
                        conn, out_root, tracks,
                        cover_title=cover_title, cover_subtitle=cover_subtitle,
                        cover_theme=cover_theme, watermark=watermark,
                        cover_pool=cover_pool, playlist_id=playlist_id,
                        export_video=export_video,
                        progress=emitter, layout=layout,
                        cover_only=cover_only, cover_columns=cover_columns,
                        cover_rows=cover_rows,
                        width=width, height=height
                    )
                recap_id = Path(summary["out_dir"]).name
                slides = [
                    f"/api/slides/{recap_id}/slide_{i}.png"
                    for i in range(1, summary["slide_count"] + 1)
                ]
                result_holder["summary"] = summary
                result_holder["slides"] = slides
            except Exception as e:
                from slideshow.builder import MissingCoverError, UnconfirmedCoverError
                if isinstance(e, UnconfirmedCoverError):
                    result_holder["error"] = {
                        "type": "unconfirmed_covers",
                        "unconfirmed_covers": e.unconfirmed_tracks,
                    }
                elif isinstance(e, MissingCoverError):
                    result_holder["error"] = {
                        "type": "missing_covers",
                        "missing_covers": e.missing_tracks,
                    }
                else:
                    result_holder["error"] = {"type": "error", "message": str(e)}
            finally:
                q.put(("done", None))

        t = threading.Thread(target=run_generate, daemon=True)
        t.start()

        # Send SSE headers
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")  # disable nginx buffering
        self.end_headers()

        try:
            while True:
                try:
                    msg_type, msg_data = q.get(timeout=600)
                except queue.Empty:
                    final = {"event": "error", "type": "error",
                             "message": "Generation timed out after 10 minutes."}
                    self.wfile.write(f"data: {json.dumps(final)}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    break
                if msg_type == "progress":
                    event_data = f"data: {json.dumps(msg_data)}\n\n"
                    self.wfile.write(event_data.encode("utf-8"))
                    self.wfile.flush()
                elif msg_type == "done":
                    if result_holder["error"]:
                        err = result_holder["error"]
                        final = {"event": "error", **err}
                    else:
                        final = {"event": "complete", "summary": result_holder["summary"],
                                 "slides": result_holder["slides"]}
                    self.wfile.write(f"data: {json.dumps(final)}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    break
        except (BrokenPipeError, ConnectionResetError):
            pass  # client disconnected
        except Exception as e:
            print(f"SSE stream error: {e}", file=sys.stderr)

    def handle_get_slide(self, parsed):
        """Serve a rendered slide PNG from output/slides/<recap-id>/<file>."""
        rel = parsed.path[len("/api/slides/"):]
        slides_root = Path("output") / "slides"
        file_path = slides_root / rel

        # Same containment guard as static files: resolve, then verify the path
        # stays inside output/slides (blocks ../ traversal).
        try:
            file_path = file_path.resolve()
            root_resolved = slides_root.resolve()
            if not file_path.is_relative_to(root_resolved):
                self.send_error(403, "Forbidden")
                return
        except Exception:
            self.send_error(404, "Not Found")
            return

        if not file_path.exists() or file_path.is_dir():
            self.send_error(404, "Not Found")
            return

        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(file_path.stat().st_size))
        self.end_headers()
        with open(file_path, "rb") as f:
            self.wfile.write(f.read())

    def handle_get_override(self, parsed):
        """Serve a manual art override image from data/art_overrides/<file>."""
        rel = parsed.path[len("/api/overrides/"):]
        overrides_root = config.ART_OVERRIDES_DIR.resolve()
        file_path = (overrides_root / rel).resolve()

        if not file_path.is_relative_to(overrides_root) or not file_path.exists() or file_path.is_dir():
            self.send_error(404, "Not Found")
            return

        ext = file_path.suffix.lower()
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }
        mime = mime_types.get(ext, "image/jpeg")

        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(file_path.stat().st_size))
        self.end_headers()
        with open(file_path, "rb") as f:
            self.wfile.write(f.read())

    def handle_post_override_upload(self):
        """Accept raw binary image and save it as a manual art override."""
        artist_raw = self.headers.get("X-Artist", "")
        title_raw = self.headers.get("X-Title", "")

        artist = unquote(artist_raw)
        title = unquote(title_raw)

        if not artist or not title:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "X-Artist and X-Title headers are required"}).encode("utf-8"))
            return

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Empty file payload"}).encode("utf-8"))
            return

        file_data = self.rfile.read(content_length)

        # Detect extension from Content-Type
        content_type = self.headers.get("Content-Type", "").lower()
        ext = ".jpg"
        if "image/png" in content_type:
            ext = ".png"
        elif "image/webp" in content_type:
            ext = ".webp"
        elif "image/jpeg" in content_type:
            ext = ".jpg"

        # Sanitize filename (illegal Windows chars: \ / : * ? " < > |)
        safe_artist = "".join(c for c in artist if c not in r'\/:*?"<>|').strip()
        safe_title = "".join(c for c in title if c not in r'\/:*?"<>|').strip()

        filename = f"{safe_artist} - {safe_title}{ext}"
        dest = config.ART_OVERRIDES_DIR / filename

        try:
            config.ART_OVERRIDES_DIR.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                f.write(file_data)
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"Failed to save file: {e}"}).encode("utf-8"))
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(
            json.dumps({"status": "success", "filename": filename, "url": f"/api/overrides/{filename}"}).encode("utf-8")
        )

    def handle_post_ocr(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Empty file payload"}).encode("utf-8"))
            return

        file_data = self.rfile.read(content_length)

        # Save temporary file in output/ocr_temp
        temp_dir = Path("output") / "ocr_temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_file = temp_dir / "temp_screenshot.png"

        try:
            with open(temp_file, "wb") as f:
                f.write(file_data)
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"Failed to save temporary screenshot: {e}"}).encode("utf-8"))
            return

        # Run OCR
        try:
            from slideshow.ocr import run_ocr, parse_tracks_from_lines
            lines = run_ocr(temp_file)
            if not lines:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"tracks": []}).encode("utf-8"))
                return

            with db.connect() as conn:
                tracks = parse_tracks_from_lines(lines, conn=conn)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"tracks": tracks}).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        finally:
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)

    def _send_json(self, status, payload):
        """Write a JSON response with the given status code."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def _read_json_body(self):
        """Read and parse a JSON request body, or return None on failure."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length else ""
        try:
            return json.loads(body) if body else {}
        except Exception:
            return None

    def handle_post_playlist_parse(self):
        """Resolve a Spotify/Last.fm playlist link into selectable candidates."""
        payload = self._read_json_body()
        if payload is None:
            self._send_json(400, {"error": "Invalid JSON payload"})
            return

        url = (payload.get("url") or "").strip()
        if not url:
            self._send_json(400, {"error": "Missing 'url' (playlist link or ID)"})
            return

        try:
            from slideshow.playlist_parse import parse_playlist, PlaylistParseError
            with db.connect() as conn:
                result = parse_playlist(url, conn=conn, lastfm_api_key=config.LASTFM_API_KEY)
            self._send_json(200, result)
        except PlaylistParseError as e:
            self._send_json(400, {"error": str(e)})
        except Exception as e:
            self._send_json(500, {"error": str(e)})

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

    def handle_post_caption(self):
        """(Re)generate just the TikTok caption for a set of tracks (no render).

        Lets the dashboard re-roll the AI caption from a phone without rebuilding
        slides. Returns {"caption": str}. Falls back to the deterministic caption
        internally if the local model is unavailable, so this never errors on
        that account.
        """
        payload = self._read_json_body()
        if payload is None:
            self._send_json(400, {"error": "Invalid JSON payload"})
            return

        tracks = payload.get("tracks", [])
        cover_title = payload.get("cover_title") or None
        if not tracks:
            self._send_json(400, {"error": "No tracks provided for caption."})
            return

        try:
            from slideshow.caption import generate_caption
            caption = generate_caption(tracks, cover_title=cover_title)
            self._send_json(200, {"caption": caption})
        except Exception as e:
            self._send_json(500, {"error": str(e)})

    def handle_post_playlist_save(self):
        """Save selected tracks back to a new or existing Spotify playlist."""
        payload = self._read_json_body()
        if payload is None:
            self._send_json(400, {"error": "Invalid JSON payload"})
            return

        tracks = payload.get("tracks", [])
        name = payload.get("name")
        playlist_id = payload.get("playlist_id")
        if not tracks:
            self._send_json(400, {"error": "No tracks provided to save."})
            return

        try:
            from slideshow.playlist_sync import save_tracks_to_playlist
            with db.connect() as conn:
                result = save_tracks_to_playlist(
                    conn, tracks, name=name, playlist_id=playlist_id
                )
            self._send_json(200, {"status": "success", **result})
        except ValueError as e:
            self._send_json(400, {"error": str(e)})
        except Exception as e:
            self._send_json(500, {"error": str(e)})

    def handle_post_logger_refresh(self):
        """Pull the newest plays on demand (Spotify recently-played + Last.fm).

        Mirrors the ingest half of run_bidaily (no popularity enrichment, no
        slideshow build) so the dashboard's candidate list can be brought up to
        date with one tap. Each source fails independently — a Spotify 429
        doesn't block the Last.fm pull, and vice versa.
        """
        if not LOGGER_REFRESH_LOCK.acquire(blocking=False):
            self._send_json(409, {"error": "A refresh is already running. Give it a moment."})
            return

        try:
            db.init_db()
            spotify_added = 0
            lastfm_added = 0
            errors = []

            try:
                config.assert_credentials()
                from logger import log_recent_plays
                print("[LOGGER REFRESH] Fetching recently played from Spotify...", flush=True)
                spotify_added = log_recent_plays()
                print(f"[LOGGER REFRESH] Spotify added {spotify_added} play(s)", flush=True)
            except Exception as e:
                print(f"[LOGGER REFRESH] Spotify ingest failed: {e}", flush=True)
                errors.append(f"Spotify: {e}")

            try:
                if not config.LASTFM_API_KEY:
                    raise RuntimeError("LASTFM_API_KEY not configured")
                username = config.get_lastfm_user()
                if not username:
                    raise RuntimeError("Last.fm username not configured")
                from ingest.lastfm_import import import_recent_from_api
                print(f"[LOGGER REFRESH] Fetching recent scrobbles for '{username}' from Last.fm...", flush=True)
                with db.connect() as conn:
                    since_unix = db.latest_lastfm_played_at_unix(conn)
                    lastfm_added = import_recent_from_api(
                        conn,
                        api_key=config.LASTFM_API_KEY,
                        username=username,
                        since_unix=since_unix,
                    )
                print(f"[LOGGER REFRESH] Last.fm added {lastfm_added} play(s)", flush=True)
            except Exception as e:
                print(f"[LOGGER REFRESH] Last.fm ingest failed: {e}", flush=True)
                errors.append(f"Last.fm: {e}")

            if len(errors) == 2:
                # Both sources failed — surface it as an error, not a quiet 0.
                self._send_json(502, {"error": " · ".join(errors)})
                return

            self._send_json(200, {
                "status": "success",
                "spotify_added": spotify_added,
                "lastfm_added": lastfm_added,
                "total_plays": db.play_count(),
                "errors": errors,
            })
        finally:
            LOGGER_REFRESH_LOCK.release()

    def handle_static_files(self, parsed):
        dist_dir = Path("dashboard") / "dist"
        path = parsed.path.lstrip("/")
        if not path or path == "":
            file_path = dist_dir / "index.html"
        else:
            file_path = dist_dir / path

        # Security check: ensure the resolved path is within dist_dir. Use
        # is_relative_to (real path-segment containment) rather than a string
        # startswith(), which is bypassable on Windows (e.g. a sibling
        # "dashboard\\dist_evil" shares the prefix "dashboard\\dist").
        try:
            file_path = file_path.resolve()
            dist_resolved = dist_dir.resolve()
            if not file_path.is_relative_to(dist_resolved):
                self.send_error(403, "Forbidden")
                return
        except Exception:
            self.send_error(404, "Not Found")
            return

        if not file_path.exists() or file_path.is_dir():
            # If dashboard isn't built yet, serve a friendly welcome instruction page
            if not (dist_dir / "index.html").exists():
                self.serve_welcome_page()
                return
            self.send_error(404, "Not Found")
            return

        # Determine MIME type
        ext = file_path.suffix.lower()
        mime_types = {
            ".html": "text/html",
            ".js": "application/javascript",
            ".css": "text/css",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".svg": "image/svg+xml",
            ".json": "application/json",
            ".ico": "image/x-icon",
            ".woff": "font/woff",
            ".woff2": "font/woff2",
            ".map": "application/json",
        }
        mime = mime_types.get(ext, "application/octet-stream")

        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(file_path.stat().st_size))
        self.end_headers()
        with open(file_path, "rb") as f:
            self.wfile.write(f.read())

    def serve_welcome_page(self):
        html = """<!DOCTYPE html>
<html>
<head>
    <title>Weekly Recap Dashboard</title>
    <style>
        body {
            background-color: #0f1115;
            color: #f3f4f6;
            font-family: system-ui, -apple-system, sans-serif;
            text-align: center;
            padding: 50px;
        }
        .container {
            max-width: 600px;
            margin: 0 auto;
            background: #1e222b;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.5);
        }
        h1 { color: #aa3bff; margin-bottom: 20px; }
        p { line-height: 1.6; color: #9ca3af; }
        code { background: #0f1115; padding: 4px 8px; border-radius: 4px; font-family: monospace; color: #f3f4f6; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Weekly Recap Dashboard API</h1>
        <p>The backend server is running successfully!</p>
        <p>To view the dashboard UI, please build the React application by running:</p>
        <p><code>cd dashboard</code><br><code>npm run build</code></p>
        <p>Or run the React app in development mode:</p>
        <p><code>cd dashboard</code><br><code>npm run dev</code></p>
    </div>
</body>
</html>
"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def handle_post_art_test_save(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        print(f"[TRACK CONFIRM] Save request received: path={self.path}, body_len={content_length}", flush=True)
        try:
            payload = json.loads(body)
            artist = payload.get("artist")
            title = payload.get("title")
            album_art_url = payload.get("album_art_url")
            print(f"[TRACK CONFIRM] Payload: artist='{artist}', title='{title}', encoded_url='{album_art_url}'", flush=True)
        except Exception as e:
            print(f"[TRACK CONFIRM] [ERROR] Failed to parse JSON body: {e}", flush=True)
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"Invalid JSON payload: {e}"}).encode("utf-8"))
            return

        if not artist or not title:
            print(f"[TRACK CONFIRM] [ERROR] Missing artist or title", flush=True)
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Missing artist or title"}).encode("utf-8"))
            return

        if not album_art_url:
            print(f"[TRACK CONFIRM] [ERROR] Missing album_art_url", flush=True)
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Missing album_art_url"}).encode("utf-8"))
            return

        # Handle base64 decoded URLs to bypass adblockers
        is_encoded = payload.get("is_encoded") or (album_art_url and not album_art_url.startswith("http"))
        if is_encoded:
            import base64
            try:
                padded = album_art_url + "=" * ((4 - len(album_art_url) % 4) % 4)
                decoded_url = base64.b64decode(padded).decode("utf-8")
                print(f"[TRACK CONFIRM] Decoded base64 URL: '{decoded_url}'", flush=True)
                album_art_url = decoded_url
            except Exception as decode_err:
                print(f"[TRACK CONFIRM] [ERROR] Failed to decode base64: {decode_err}", flush=True)
                pass

        try:
            print(f"[TRACK CONFIRM] Updating db table 'plays': '{artist}' - '{title}' -> '{album_art_url}'", flush=True)
            with db.connect() as conn:
                db.update_track_art(conn, artist, title, album_art_url)
            print(f"[TRACK CONFIRM] [SUCCESS] DB update completed successfully", flush=True)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success"}).encode("utf-8"))
        except Exception as e:
            print(f"[TRACK CONFIRM] [ERROR] DB update failed: {e}", flush=True)
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    def handle_get_art_proxy(self, parsed):
        import base64
        import urllib.request
        query = parse_qs(parsed.query)
        encoded_url = query.get("url", [""])[0]
        print(f"[ART PROXY] Request received: url_len={len(encoded_url)}", flush=True)
        if not encoded_url:
            print(f"[ART PROXY] [ERROR] Missing url query param", flush=True)
            self.send_error(400, "Missing url parameter")
            return
        try:
            padded = encoded_url + "=" * ((4 - len(encoded_url) % 4) % 4)
            url = base64.b64decode(padded).decode("utf-8")
            print(f"[ART PROXY] Decoded target URL: '{url}'", flush=True)
            
            # Fetch the image from iTunes
            print(f"[ART PROXY] Proxying request to Apple CDN...", flush=True)
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                content_type = resp.headers.get("Content-Type", "image/jpeg")
                data = resp.read()
                print(f"[ART PROXY] Downloaded successfully: Content-Type='{content_type}', bytes={len(data)}", flush=True)
                
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
            print(f"[ART PROXY] [SUCCESS] Proxied image returned to client", flush=True)
        except Exception as e:
            print(f"[ART PROXY] [ERROR] Proxy fetch failed: {e}", flush=True)
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"Proxy failed: {e}"}).encode("utf-8"))

    def handle_get_recap_history(self):
        """List all past recap directories in output/slides/ that start with 'recap-'."""
        slides_root = Path("output") / "slides"
        entries = []
        if slides_root.exists():
            for d in sorted(slides_root.iterdir(), reverse=True):
                if d.is_dir() and d.name.startswith("recap-"):
                    recap_id = d.name
                    # Extract date from recap id (e.g. recap-2025-06-15 -> 2025-06-15)
                    date_part = recap_id.replace("recap-", "")
                    slide_count = len(list(d.glob("*.png")))
                    generated_at = d.stat().st_mtime
                    entries.append({
                        "recap_id": recap_id,
                        "date": date_part,
                        "slide_count": slide_count,
                        "generated_at": generated_at,
                    })

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"history": entries}).encode("utf-8"))

    def handle_get_recap_slides(self, parsed):
        """Return slide URLs for a specific recap: /api/recap-history/<recap_id>/slides."""
        parts = parsed.path.strip("/").split("/")
        # Expected: ["api", "recap-history", "<recap_id>", "slides"]
        if len(parts) != 4 or parts[-1] != "slides":
            self.send_error(404, "Not Found")
            return
        recap_id = parts[2]
        recap_dir = (Path("output") / "slides" / recap_id).resolve()
        slides_root = (Path("output") / "slides").resolve()

        if not recap_dir.is_relative_to(slides_root) or not recap_dir.is_dir():
            self.send_error(404, "Not Found")
            return

        slide_files = sorted(recap_dir.glob("*.png"))
        slides = [
            f"/api/slides/{recap_id}/{f.name}"
            for f in slide_files
        ]

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"recap_id": recap_id, "slides": slides}).encode("utf-8"))

    def handle_get_health(self):
        """Report backend subsystem health for the dashboard's status monitor.

        Always returns 200 (reachability itself signals the server is up). DB and
        disk are treated as critical; Ollama and bi-daily staleness are warnings.
        """
        checks = {}

        try:
            with db.connect() as conn:
                conn.execute("SELECT 1").fetchone()
            checks["db"] = {"ok": True}
        except Exception as e:
            checks["db"] = {"ok": False, "error": str(e)}

        try:
            import urllib.request
            from slideshow.llm_caption import OLLAMA_HOST, CAPTION_MODEL
            req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            names = [m.get("name", "") for m in data.get("models", [])]
            base = CAPTION_MODEL.split(":")[0]
            checks["ollama"] = {"ok": True, "model_available": any(base in n for n in names)}
        except Exception as e:
            checks["ollama"] = {"ok": False, "error": str(e)}

        try:
            _, _, free = shutil.disk_usage(".")
            checks["disk"] = {"ok": free > 500 * 1024 * 1024, "free_gb": round(free / 1e9, 1)}
        except Exception as e:
            checks["disk"] = {"ok": False, "error": str(e)}

        try:
            latest = _latest_bidaily_date()
            age_days = None
            if latest:
                from datetime import date
                age_days = (date.today() - date.fromisoformat(latest)).days
            checks["bidaily"] = {
                "ok": age_days is not None and age_days <= 3,
                "last_date": latest,
                "age_days": age_days,
                "running": _BIDAILY_STATE["running"],
            }
        except Exception as e:
            checks["bidaily"] = {"ok": False, "error": str(e)}

        critical_ok = checks["db"]["ok"] and checks["disk"]["ok"]
        warnings = [k for k in ("ollama", "bidaily") if not checks[k].get("ok")]
        self._send_json(200, {
            "status": "ok" if critical_ok else "degraded",
            "warnings": warnings,
            "checks": checks,
        })

    def handle_get_bidaily_history(self):
        """List dated (non-recap) bi-daily slide folders, newest first."""
        slides_root = Path("output") / "slides"
        entries = []
        if slides_root.exists():
            for d in sorted(slides_root.iterdir(), reverse=True):
                if not (d.is_dir() and re.match(r"^\d{4}-\d{2}-\d{2}$", d.name)):
                    continue
                slide_files = sorted(d.glob("slide_*.png"))
                if not slide_files:
                    continue
                caption = None
                cap = d / "caption.txt"
                if cap.exists():
                    try:
                        caption = cap.read_text(encoding="utf-8")
                    except OSError:
                        caption = None
                entries.append({
                    "date": d.name,
                    "slide_count": len(slide_files),
                    "generated_at": d.stat().st_mtime,
                    "caption": caption,
                    "slides": [f"/api/slides/{d.name}/{f.name}" for f in slide_files],
                })
        self._send_json(200, {"history": entries})

    def handle_get_bidaily_status(self):
        """Return the current/last bi-daily run status + captured log tail."""
        with _BIDAILY_LOCK:
            s = _BIDAILY_STATE
            self._send_json(200, {
                "running": s["running"],
                "started_at": s["started_at"],
                "finished_at": s["finished_at"],
                "ok": s["ok"],
                "error": s["error"],
                "log": list(s["log"]),
            })

    def handle_post_bidaily_run(self):
        """Trigger the bi-daily pipeline in the background (one at a time).

        Fast by default from the dashboard: skips the slow global-popularity
        enrichment unless the payload requests it. Still pulls newest plays and
        rebuilds today's slides.
        """
        payload = self._read_json_body()
        if payload is None:
            self._send_json(400, {"error": "Invalid JSON payload"})
            return
        with _BIDAILY_LOCK:
            if _BIDAILY_STATE["running"]:
                self._send_json(409, {"error": "A bi-daily run is already in progress."})
                return
        skip_spotify = bool(payload.get("skip_spotify", False))
        skip_lastfm = bool(payload.get("skip_lastfm", False))
        skip_popularity = bool(payload.get("skip_popularity", True))
        threading.Thread(
            target=_run_bidaily_pipeline,
            args=(skip_spotify, skip_lastfm, skip_popularity),
            daemon=True,
        ).start()
        self._send_json(202, {"status": "started"})


def _latest_bidaily_date():
    """Return the newest YYYY-MM-DD bi-daily slide folder name, or None."""
    slides_root = Path("output") / "slides"
    if not slides_root.exists():
        return None
    dates = [
        d.name for d in slides_root.iterdir()
        if d.is_dir() and re.match(r"^\d{4}-\d{2}-\d{2}$", d.name)
    ]
    return max(dates) if dates else None


def auto_git_pull():
    try:
        import subprocess
        print("Checking for updates (git pull)...")
        res = subprocess.run(
            ["git", "pull"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if res.returncode == 0:
            print(f"Git pull result: {res.stdout.strip()}")
        else:
            print(f"Git pull failed (code {res.returncode}): {res.stderr.strip()}")
    except Exception as e:
        print(f"Skipping auto-update: {e}")


def main():
    # Redirect stdout and stderr to data/logs/dashboard.log
    log_dir = Path("data") / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "dashboard.log"

    class Tee:
        def __init__(self, original, file_obj):
            self.original = original
            self.file_obj = file_obj

        def write(self, data):
            self.original.write(data)
            self.file_obj.write(data)
            self.original.flush()
            self.file_obj.flush()

        def flush(self):
            self.original.flush()
            self.file_obj.flush()

    # Open log file in append mode with UTF-8 encoding
    import atexit
    f = open(log_file, "a", encoding="utf-8")
    atexit.register(f.close)  # ensure handle is released on exit
    sys.stdout = Tee(sys.stdout, f)
    sys.stderr = Tee(sys.stderr, f)

    # Print a separator for new run
    print(f"\n--- Dashboard Server Starting: {time.strftime('%Y-%m-%d %H:%M:%S')} ---")

    auto_git_pull()
    port = 8000
    server_address = ("", port)
    httpd = ThreadingHTTPServer(server_address, DashboardHandler)
    print(
        f"Starting Weekly Recap Dashboard Server on http://localhost:{port}/..."
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
        sys.exit(0)


if __name__ == "__main__":
    main()
