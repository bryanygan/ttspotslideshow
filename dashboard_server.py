import json
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import config
import db
from slideshow.builder import build_recap_slideshow


class DashboardHandler(BaseHTTPRequestHandler):

    def end_headers(self):
        # Inject CORS headers on every response
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/candidates":
            self.handle_get_candidates(parsed)
        else:
            self.handle_static_files(parsed)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/generate":
            self.handle_post_generate()
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
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        # Fetch Spotify popularity in bulk
        track_ids = [c["track_id"] for c in candidates if c.get("track_id")]
        popularities = {}
        if track_ids:
            try:
                from spotify_client import get_client

                sp = get_client()
                # Batch in chunks of 50
                for i in range(0, len(track_ids), 50):
                    chunk = track_ids[i : i + 50]
                    tracks_data = sp.tracks(chunk)
                    for t in tracks_data.get("tracks", []):
                        if t:
                            popularities[t["id"]] = t.get("popularity", 50)
            except Exception:
                pass

        # Decorate candidates with popularity and last_featured details
        for c in candidates:
            tid = c.get("track_id")
            c["popularity"] = popularities.get(tid, 50)
            c["last_featured"] = featured.get(c["track_key"], None)

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

        if not tracks:
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
                summary = build_recap_slideshow(conn, out_root, tracks)
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(
            json.dumps({"status": "success", "summary": summary}).encode(
                "utf-8"
            )
        )

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


def main():
    port = 8000
    server_address = ("", port)
    httpd = HTTPServer(server_address, DashboardHandler)
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
