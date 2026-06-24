"""Tests for enrichment robustness: incremental commits (resumable) + progress."""

import sqlite3

import db
from ingest.genres import enrich_all
from tests.test_genres import FakeSpotify


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
