import sqlite3
from datetime import datetime, timezone

import db


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    return c


def _cols(conn, table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def test_migrate_fresh_creates_v2_and_artist_genres():
    conn = _conn()
    db.migrate(conn)
    assert "source" in _cols(conn, "plays")
    assert "played_at_unix" in _cols(conn, "plays")
    assert _cols(conn, "artist_genres")  # table exists


def test_migrate_is_idempotent():
    conn = _conn()
    db.migrate(conn)
    db.migrate(conn)  # must not raise
    assert "source" in _cols(conn, "plays")


def test_migrate_rebuilds_old_schema_and_backfills():
    conn = _conn()
    # Build the OLD plays schema (no source / played_at_unix) and a row.
    conn.executescript(
        """
        CREATE TABLE plays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id TEXT NOT NULL, name TEXT NOT NULL, artist TEXT NOT NULL,
            artist_id TEXT, artist_genre TEXT, album_art_url TEXT,
            popularity INTEGER, played_at TEXT NOT NULL,
            UNIQUE(track_id, played_at)
        );
        """
    )
    conn.execute(
        "INSERT INTO plays (track_id,name,artist,played_at) VALUES (?,?,?,?)",
        ("t1", "Song", "Artist", "2026-06-23T10:00:00+00:00"),
    )
    db.migrate(conn)
    row = conn.execute("SELECT source, played_at_unix FROM plays").fetchone()
    expected = int(datetime(2026, 6, 23, 10, 0, 0, tzinfo=timezone.utc).timestamp())
    assert row["source"] == "spotify"
    assert row["played_at_unix"] == expected


def test_insert_play_sets_source_and_unix():
    conn = _conn()
    db.migrate(conn)
    db.insert_play(
        conn, track_id="t", name="n", artist="a", artist_id="ai",
        artist_genre="g", album_art_url="u", popularity=None,
        played_at="2026-06-23T10:00:00+00:00",
    )
    row = conn.execute("SELECT source, played_at_unix FROM plays").fetchone()
    expected = int(datetime(2026, 6, 23, 10, 0, 0, tzinfo=timezone.utc).timestamp())
    assert row["source"] == "spotify"
    assert row["played_at_unix"] == expected
