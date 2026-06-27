import json
import sys
import time
import threading
import queue
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
from render.art import find_override_art

import config
import db
from slideshow.builder import build_recap_slideshow, ProgressEmitter


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


class DashboardHandler(BaseHTTPRequestHandler):

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
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

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
        elif parsed.path == "/api/art-test/save":
            self.handle_post_art_test_save()
        elif parsed.path == "/api/ocr":
            self.handle_post_ocr()
        elif parsed.path == "/api/playlist/parse":
            self.handle_post_playlist_parse()
        elif parsed.path == "/api/playlist/save":
            self.handle_post_playlist_save()
        else:
            self.send_error(404, "Not Found")

    def handle_get_candidates(self, parsed):
        query = parse_qs(parsed.query)
        try:
            days = int(query.get("days", [7])[0])
        except (ValueError, TypeError):
            days = 7

        now_unix = int(time.time())
        start_unix = now_unix - days * 86400

        try:
            with db.connect() as conn:
                candidates = db.window_track_candidates(conn, start_unix)
                featured = db.featured_history(conn)
                recent_featured = db.recent_featured_history(conn, last_n_days=14)
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        # Collect track IDs that don't have cached popularity in the DB.
        # Filter to make sure we only query Spotify for valid 22-character alphanumeric Spotify track IDs,
        # ignoring Last.fm UUIDs (which contain hyphens and are 36 characters long).
        uncached_candidates = [
            c for c in candidates
            if c.get("track_id")
            and len(c["track_id"]) == 22
            and c["track_id"].isalnum()
            and c.get("popularity") is None
        ]
        track_ids_to_fetch = [c["track_id"] for c in uncached_candidates]

        # Initialize popularities dict with already cached database values
        popularities = {c["track_id"]: c["popularity"] for c in candidates if c.get("track_id") and c.get("popularity") is not None}

        if track_ids_to_fetch:
            try:
                from spotify_client import get_client

                sp = get_client()
                fetched_popularities = {}
                # Batch in chunks of 50
                for i in range(0, len(track_ids_to_fetch), 50):
                    chunk = track_ids_to_fetch[i : i + 50]
                    tracks_data = sp.tracks(chunk)
                    for t in tracks_data.get("tracks", []):
                        if t:
                            fetched_popularities[t["id"]] = t.get("popularity", 50)

                # Write newly fetched popularities to the DB so they are cached!
                if fetched_popularities:
                    try:
                        with db.connect() as conn:
                            for tid, pop in fetched_popularities.items():
                                conn.execute("UPDATE plays SET popularity = ? WHERE track_id = ?", (pop, tid))
                            # Merge them into the local dictionary
                            popularities.update(fetched_popularities)
                    except Exception as db_err:
                        print(f"Failed to cache popularities to DB: {db_err}", file=sys.stderr)
            except Exception as sp_err:
                print(f"Failed to fetch popularities from Spotify: {sp_err}", file=sys.stderr)

        # Decorate candidates with popularity, last_featured, and overrides details
        for c in candidates:
            tid = c.get("track_id")
            # If still None (e.g. no track_id or API failed), default to 50
            c["popularity"] = popularities.get(tid) if popularities.get(tid) is not None else 50
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

        try:
            with db.connect() as conn:
                out_root = Path("output") / "slides"
                summary = build_recap_slideshow(
                    conn, out_root, tracks,
                    cover_title=cover_title, cover_subtitle=cover_subtitle,
                    cover_theme=cover_theme, watermark=watermark,
                    cover_pool=cover_pool, playlist_id=playlist_id,
                    export_video=export_video, layout=layout,
                    cover_only=cover_only, cover_columns=cover_columns
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
                        cover_only=cover_only, cover_columns=cover_columns
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
        except Exception:
            pass

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
        try:
            payload = json.loads(body)
            artist = payload.get("artist")
            title = payload.get("title")
            album_art_url = payload.get("album_art_url")
        except Exception as e:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"Invalid JSON payload: {e}"}).encode("utf-8"))
            return

        if not artist or not title:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Missing artist or title"}).encode("utf-8"))
            return

        if not album_art_url:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Missing album_art_url"}).encode("utf-8"))
            return

        try:
            with db.connect() as conn:
                db.update_track_art(conn, artist, title, album_art_url)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success"}).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

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
    f = open(log_file, "a", encoding="utf-8")
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
