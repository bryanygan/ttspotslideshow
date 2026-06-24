"""Tests for enrichment robustness: incremental commits (resumable) + progress
and Spotify rate-limit (429) resilience (defer + stop-early + resume)."""

import sqlite3

import spotipy

import db
from ingest.genres import enrich_all, resolve_artist_genre
from tests.test_genres import FakeSpotify


class RateLimitedSpotify:
    """Stub that raises 429 for the first `fail_first` calls, then succeeds."""

    def __init__(self, fail_first=10 ** 9):
        self.calls = 0
        self.fail_first = fail_first

    def search(self, q, type="artist", limit=1):
        self.calls += 1
        if self.calls <= self.fail_first:
            raise spotipy.SpotifyException(429, -1, "rate limited")
        return {"artists": {"items": [{"id": "x", "name": q, "genres": ["rage"]}]}}


class BadRequestSpotify:
    def search(self, q, type="artist", limit=1):
        raise spotipy.SpotifyException(404, -1, "not found")


def _play(conn, artist, name, unix):
    db.insert_lastfm_play(
        conn, track_id="", name=name, artist=artist, album_art_url="",
        played_at="2023-11-14T00:00:00+00:00", played_at_unix=unix,
    )


def test_enrich_all_persists_without_outer_commit(tmp_path):
    """enrich_all must commit internally so progress survives an interruption."""
    db_path = tmp_path / "t.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    db.migrate(conn)
    _play(conn, "2hollis", "S", 1700000000)
    conn.commit()

    sp = FakeSpotify({"2hollis": ("id1", ["rage"])})
    enrich_all(conn, sp, "KEY", commit_every=1, sleep=lambda s: None)

    # A SEPARATE connection must see the row WITHOUT this test committing `conn`,
    # which proves enrich_all committed the work itself.
    other = sqlite3.connect(db_path)
    other.row_factory = sqlite3.Row
    row = other.execute(
        "SELECT primary_bucket FROM artist_genres WHERE artist_key = ?", ("2hollis",)
    ).fetchone()
    assert row is not None and row["primary_bucket"] == "rage"


def test_enrich_all_reports_progress():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.migrate(conn)
    for i in range(3):
        _play(conn, f"A{i}", f"S{i}", 1700000000 + i)

    calls = []
    sp = FakeSpotify({})  # no Spotify hits -> Last.fm fallback (empty) -> 'none'
    enrich_all(
        conn, sp, "KEY", fetch=lambda url: '{"toptags": {}}',
        sleep=lambda s: None, commit_every=1,
        progress=lambda done, total: calls.append((done, total)),
    )
    assert calls, "progress callback was never called"
    assert calls[-1] == (3, 3)  # final call reports completion


def test_resolve_defers_on_rate_limit():
    """A 429 must defer (transient) — NOT lock in a Last.fm result."""
    out = resolve_artist_genre(
        "Carti", RateLimitedSpotify(), "KEY",
        fetch=lambda u: '{"toptags": {"tag": [{"name": "trap", "count": 99}]}}',
    )
    assert out["transient"] is True
    assert out["genre_source"] == "none"  # did not fall back to Last.fm


def test_resolve_non_ratelimit_spotify_error_falls_to_lastfm():
    """A non-429 Spotify error is not transient -> Last.fm fallback applies."""
    out = resolve_artist_genre(
        "X", BadRequestSpotify(), "KEY",
        fetch=lambda u: '{"toptags": {"tag": [{"name": "drill", "count": 99}]}}',
    )
    assert out["transient"] is False
    assert out["genre_source"] == "lastfm"
    assert out["primary_bucket"] == "drill"


def test_enrich_all_stops_early_on_rate_limit_then_resumes():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.migrate(conn)
    for i in range(5):
        _play(conn, f"A{i}", f"S{i}", 1700000000 + i)

    # Persistent rate limit -> defer all, stop early, cache nothing.
    s1 = enrich_all(
        conn, RateLimitedSpotify(), "KEY", fetch=lambda u: '{"toptags": {}}',
        sleep=lambda s: None, max_consecutive_transient=3,
    )
    assert s1["stopped_early"] is True
    assert s1["deferred"] >= 3
    assert conn.execute("SELECT COUNT(*) FROM artist_genres").fetchone()[0] == 0

    # Limit cleared -> a re-run retries the deferred artists and enriches them.
    s2 = enrich_all(conn, RateLimitedSpotify(fail_first=0), "KEY", sleep=lambda s: None)
    assert s2["spotify"] == 5
    assert conn.execute("SELECT COUNT(*) FROM artist_genres").fetchone()[0] == 5
