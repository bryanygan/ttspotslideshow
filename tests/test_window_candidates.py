import sqlite3

import db


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db.migrate(c)
    return c


def _iso(u):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(u, timezone.utc).isoformat()


def _lastfm(conn, artist, name, unix, art=""):
    db.insert_lastfm_play(
        conn, track_id="", name=name, artist=artist, album_art_url=art,
        played_at=_iso(unix), played_at_unix=unix,
    )


def test_aggregates_counts_and_window_filter():
    conn = _conn()
    _lastfm(conn, "Carti", "Location", 1000)
    _lastfm(conn, "Carti", "Location", 1500)   # same track, in window -> count 2
    _lastfm(conn, "Yeat", "Money", 500)        # before window -> excluded
    cands = db.window_track_candidates(conn, start_unix=900)
    by_key = {c["track_key"]: c for c in cands}
    assert set(by_key) == {"carti\tlocation"}
    assert by_key["carti\tlocation"]["play_count"] == 2
    assert by_key["carti\tlocation"]["last_played_unix"] == 1500


def test_joins_primary_bucket_and_defaults_unknown():
    conn = _conn()
    db.upsert_artist_genre(
        conn, artist_key="carti", display_name="Carti", spotify_artist_id="",
        raw_genres="rage", lastfm_tags="", primary_bucket="rage",
        genre_source="spotify", fetched_at="2026-06-24T00:00:00Z",
    )
    _lastfm(conn, "Carti", "Location", 1000)
    _lastfm(conn, "NoGenre", "Track", 1000)
    cands = {c["track_key"]: c for c in db.window_track_candidates(conn, 0)}
    assert cands["carti\tlocation"]["primary_bucket"] == "rage"
    assert cands["nogenre\ttrack"]["primary_bucket"] == "unknown"
