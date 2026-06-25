import sqlite3
from datetime import datetime, timezone

import db


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db.migrate(c)
    return c


def _iso(u):
    return datetime.fromtimestamp(u, timezone.utc).isoformat()


def _spotify(conn, artist, name, unix):
    db.insert_play(
        conn, track_id=f"sp-{name}-{unix}", name=name, artist=artist,
        artist_id="x", artist_genre=None, album_art_url="", popularity=None,
        played_at=_iso(unix),
    )


def _lastfm(conn, artist, name, unix):
    db.insert_lastfm_play(
        conn, track_id="", name=name, artist=artist, album_art_url="",
        played_at=_iso(unix), played_at_unix=unix,
    )


def test_cross_source_pair_within_window_collapses_to_spotify():
    conn = _conn()
    _spotify(conn, "Carti", "Location", 1000)
    _lastfm(conn, "carti", "location", 1050)  # +50s, normalized-equal
    rows = db.canonical_plays(conn, window_seconds=120)
    assert len(rows) == 1
    assert rows[0]["source"] == "spotify"


def test_lastfm_first_then_spotify_still_collapses_to_spotify():
    # Same pair, but the Last.fm row is logged with the EARLIER timestamp, so it is
    # iterated first. The later Spotify row must still win (replace it in-place).
    conn = _conn()
    _lastfm(conn, "carti", "location", 1000)
    _spotify(conn, "Carti", "Location", 1050)  # +50s, normalized-equal
    rows = db.canonical_plays(conn, window_seconds=120)
    assert len(rows) == 1
    assert rows[0]["source"] == "spotify"


def test_cross_source_pair_outside_window_kept_separate():
    conn = _conn()
    _spotify(conn, "Carti", "Location", 1000)
    _lastfm(conn, "Carti", "Location", 1000 + 200)
    rows = db.canonical_plays(conn, window_seconds=120)
    assert len(rows) == 2


def test_same_source_repeat_preserved():
    conn = _conn()
    _lastfm(conn, "Carti", "Location", 1000)
    _lastfm(conn, "Carti", "Location", 1000 + 3600)
    rows = db.canonical_plays(conn, window_seconds=120)
    assert len(rows) == 2


def test_different_songs_same_second_both_kept():
    conn = _conn()
    _spotify(conn, "Carti", "Location", 1000)
    _lastfm(conn, "Yeat", "Money", 1000)
    rows = db.canonical_plays(conn, window_seconds=120)
    assert len(rows) == 2
