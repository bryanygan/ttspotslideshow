import json
import sqlite3
from urllib.parse import urlparse
import pytest
import dashboard_server
import db


class FakeWfile:

    def __init__(self):
        self.content = b""

    def write(self, data):
        self.content += data


class DummyHandler(dashboard_server.DashboardHandler):

    def __init__(self):
        self.headers = {}
        self.wfile = FakeWfile()
        self.response = None
        self.response_headers = []

    def send_response(self, code, message=None):
        self.response = code

    def send_header(self, keyword, value):
        self.response_headers.append((keyword, value))

    def end_headers(self):
        pass


def test_get_candidates_endpoint(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.migrate(conn)
    # Insert a play
    db.insert_lastfm_play(
        conn,
        track_id="track1",
        name="Song A",
        artist="Artist A",
        album_art_url="http://art",
        played_at="2026-06-25T00:00:00Z",
        played_at_unix=1782350000,
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


def test_static_file_serving():
    handler = DummyHandler()
    parsed = urlparse("http://localhost:8000/")
    handler.handle_static_files(parsed)
    assert handler.response == 200
    assert b"html" in handler.wfile.content.lower()
