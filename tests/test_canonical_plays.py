from datetime import datetime, timezone

import db


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


def test_cross_source_pair_within_window_collapses_to_spotify(conn):
    _spotify(conn, "Carti", "Location", 1000)
    _lastfm(conn, "carti", "location", 1050)  # +50s, normalized-equal
    rows = db.canonical_plays(conn, window_seconds=120)
    assert len(rows) == 1
    assert rows[0]["source"] == "spotify"


def test_lastfm_first_then_spotify_still_collapses_to_spotify(conn):
    # Same pair, but the Last.fm row is logged with the EARLIER timestamp, so it is
    # iterated first. The later Spotify row must still win (replace it in-place).
    _lastfm(conn, "carti", "location", 1000)
    _spotify(conn, "Carti", "Location", 1050)  # +50s, normalized-equal
    rows = db.canonical_plays(conn, window_seconds=120)
    assert len(rows) == 1
    assert rows[0]["source"] == "spotify"


def test_cross_source_pair_outside_window_kept_separate(conn):
    _spotify(conn, "Carti", "Location", 1000)
    _lastfm(conn, "Carti", "Location", 1000 + 200)
    rows = db.canonical_plays(conn, window_seconds=120)
    assert len(rows) == 2


def test_same_source_repeat_preserved(conn):
    _lastfm(conn, "Carti", "Location", 1000)
    _lastfm(conn, "Carti", "Location", 1000 + 3600)
    rows = db.canonical_plays(conn, window_seconds=120)
    assert len(rows) == 2


def test_different_songs_same_second_both_kept(conn):
    _spotify(conn, "Carti", "Location", 1000)
    _lastfm(conn, "Yeat", "Money", 1000)
    rows = db.canonical_plays(conn, window_seconds=120)
    assert len(rows) == 2


def test_since_unix_keeps_boundary_twin_dedup(conn):
    # A Last.fm twin just before the window must still let the in-window Spotify
    # row win (the look-back buffer makes this dedup correct).
    X = 100_000
    _lastfm(conn, "carti", "location", X - 50)   # buffer (within window_seconds)
    _spotify(conn, "Carti", "Location", X + 10)  # in-window, same track
    rows = db.canonical_plays(conn, window_seconds=120, since_unix=X)
    assert len(rows) == 1
    assert rows[0]["source"] == "spotify"
    assert rows[0]["played_at_unix"] == X + 10


def test_since_unix_excludes_pre_window_rows(conn):
    X = 100_000
    _lastfm(conn, "A", "old", X - 500)   # well before the window
    _lastfm(conn, "B", "new", X + 5)
    rows = db.canonical_plays(conn, since_unix=X)
    assert {(r["artist"], r["name"]) for r in rows} == {("B", "new")}
