import json
import sqlite3
from pathlib import Path
from urllib.parse import urlparse
import pytest
import dashboard_server
import db


class FakeWfile:

    def __init__(self):
        self.content = b""

    def write(self, data):
        self.content += data


class FakeRfile:

    def __init__(self, data: bytes):
        self.data = data

    def read(self, n):
        return self.data[:n]


class DummyHandler(dashboard_server.DashboardHandlerHelper):

    def __init__(self, body: bytes = b""):
        self.headers = {"Content-Length": str(len(body))}
        self.rfile = FakeRfile(body)
        self.wfile = FakeWfile()
        self.response = None
        self.response_headers = []

    def send_response(self, code, message=None):
        self.response = code

    def send_error(self, code, message=None):
        self.response = code

    def send_header(self, keyword, value):
        self.response_headers.append((keyword, value))

    def end_headers(self):
        pass


def test_get_candidates_endpoint(monkeypatch):
    import time
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.migrate(conn)
    # Insert a play
    now_unix = int(time.time())
    db.insert_lastfm_play(
        conn,
        track_id="track1",
        name="Song A",
        artist="Artist A",
        album_art_url="http://art",
        played_at="2026-06-25T00:00:00Z",
        played_at_unix=now_unix - 3 * 86400,
    )
    from contextlib import contextmanager
    @contextmanager
    def fake_connect():
        yield conn

    # Mock db.connect
    monkeypatch.setattr(db, "connect", fake_connect)

    handler = DummyHandler()
    parsed = urlparse("http://localhost:8000/api/candidates?days=7")
    handler.handle_get_candidates(parsed)

    assert handler.response == 200
    res = json.loads(handler.wfile.content.decode("utf-8"))
    assert "candidates" in res
    assert len(res["candidates"]) == 1
    assert res["candidates"][0]["title"] == "Song A"
    assert res["candidates"][0]["popularity"] == 50


def test_get_candidates_uses_cached_popularity(monkeypatch):
    import time
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.migrate(conn)
    now_unix = int(time.time())
    db.insert_lastfm_play(
        conn, track_id="track1", name="Song A", artist="Artist A",
        album_art_url="http://art", played_at="2026-06-25T00:00:00Z",
        played_at_unix=now_unix - 3 * 86400,
    )
    db.upsert_track_popularity(
        conn, track_key="artist a\tsong a", listeners=900, popularity=33,
        source="lastfm", fetched_at="t",
    )
    from contextlib import contextmanager
    @contextmanager
    def fake_connect():
        yield conn
    monkeypatch.setattr(db, "connect", fake_connect)

    handler = DummyHandler()
    parsed = urlparse("http://localhost:8000/api/candidates?days=7")
    handler.handle_get_candidates(parsed)

    res = json.loads(handler.wfile.content.decode("utf-8"))
    assert res["candidates"][0]["popularity"] == 33


def test_static_file_serving():
    handler = DummyHandler()
    parsed = urlparse("http://localhost:8000/")
    handler.handle_static_files(parsed)
    assert handler.response == 200
    assert b"html" in handler.wfile.content.lower()


def test_generate_returns_slide_urls(monkeypatch):
    # Stub the heavy render; assert the response exposes downloadable slide URLs.
    def fake_build(conn, out_root, tracks, **kw):
        return {
            "date": "2026-06-25", "track_count": 8, "slide_count": 2,
            "genre_spread": {}, "out_dir": str(Path("output") / "slides" / "recap-2026-06-25"),
        }
    import slideshow.builder
    monkeypatch.setattr(slideshow.builder, "build_recap_slideshow", fake_build)

    from contextlib import contextmanager
    @contextmanager
    def fake_connect():
        yield None
    monkeypatch.setattr(db, "connect", fake_connect)

    body = json.dumps({"tracks": [{"track_key": "a\tb"}]}).encode("utf-8")
    handler = DummyHandler(body=body)
    handler.handle_post_generate()

    assert handler.response == 200
    res = json.loads(handler.wfile.content.decode("utf-8"))
    assert res["slides"] == [
        "/api/slides/recap-2026-06-25/slide_1.png",
        "/api/slides/recap-2026-06-25/slide_2.png",
    ]


def test_get_slide_serves_png(monkeypatch, tmp_path):
    slides = tmp_path / "output" / "slides" / "recap-x"
    slides.mkdir(parents=True)
    (slides / "slide_1.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    monkeypatch.chdir(tmp_path)

    handler = DummyHandler()
    handler.handle_get_slide(urlparse("http://x/api/slides/recap-x/slide_1.png"))

    assert handler.response == 200
    assert handler.wfile.content == b"\x89PNG\r\n\x1a\nfake"


def test_get_slide_rejects_path_traversal(monkeypatch, tmp_path):
    (tmp_path / "output" / "slides").mkdir(parents=True)
    (tmp_path / "secret.txt").write_text("nope", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    handler = DummyHandler()
    handler.handle_get_slide(urlparse("http://x/api/slides/../../secret.txt"))

    assert handler.response == 403
