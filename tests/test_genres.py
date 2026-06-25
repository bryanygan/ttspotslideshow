import sqlite3

import db
from ingest.genres import resolve_artist_genre, enrich_all


class FakeSpotify:
    """Minimal spotipy-compatible stub."""
    def __init__(self, mapping):
        self.mapping = mapping  # normalized name -> (id, [genres]) or None

    def search(self, q, type="artist", limit=1):
        hit = self.mapping.get(q.strip().lower())
        if not hit:
            return {"artists": {"items": []}}
        spotify_id, genres = hit
        return {"artists": {"items": [
            {"id": spotify_id, "name": q, "genres": genres}
        ]}}


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db.migrate(c)
    return c


def test_resolve_uses_spotify_when_genres_present():
    sp = FakeSpotify({"2hollis": ("id1", ["rage", "atl hip hop"])})
    out = resolve_artist_genre("2hollis", sp, "KEY")
    assert out["genre_source"] == "spotify"
    assert out["primary_bucket"] == "rage"
    assert out["spotify_artist_id"] == "id1"


def test_resolve_falls_back_to_lastfm_when_spotify_empty():
    sp = FakeSpotify({"someartist": ("id2", [])})  # match but no genres
    out = resolve_artist_genre(
        "SomeArtist", sp, "KEY",
        fetch=lambda url: '{"toptags": {"tag": [{"name": "drill", "count": 80}]}}',
    )
    assert out["genre_source"] == "lastfm"
    assert out["primary_bucket"] == "drill"


def test_resolve_unknown_when_nothing():
    sp = FakeSpotify({})  # no Spotify hit
    out = resolve_artist_genre(
        "Ghost", sp, "KEY", fetch=lambda url: '{"toptags": {}}'
    )
    assert out["genre_source"] == "none"
    assert out["primary_bucket"] == "unknown"


def test_resolve_rejects_name_mismatch():
    # Spotify returns a hit whose name doesn't match the query -> ignore it.
    class Wrong:
        def search(self, q, type="artist", limit=1):
            return {"artists": {"items": [
                {"id": "z", "name": "Totally Different", "genres": ["rock"]}
            ]}}
    out = resolve_artist_genre(
        "MyArtist", Wrong(), "KEY", fetch=lambda url: '{"toptags": {}}'
    )
    assert out["genre_source"] == "none"


def test_resolve_filters_noise_only_tags_to_none():
    # An artist whose only Last.fm tags are locations/meta -> no real genre.
    sp = FakeSpotify({})  # no Spotify hit
    out = resolve_artist_genre(
        "RegionalGuy", sp, "KEY",
        fetch=lambda url: '{"toptags": {"tag": ['
                          '{"name": "detroit", "count": 100},'
                          '{"name": "american", "count": 50}]}}',
    )
    assert out["genre_source"] == "none"
    assert out["primary_bucket"] == "unknown"


def test_resolve_keeps_genre_tag_alongside_noise():
    sp = FakeSpotify({})
    out = resolve_artist_genre(
        "RegionalGuy", sp, "KEY",
        fetch=lambda url: '{"toptags": {"tag": ['
                          '{"name": "detroit", "count": 100},'
                          '{"name": "detroit rap", "count": 80}]}}',
    )
    assert out["genre_source"] == "lastfm"
    assert out["primary_bucket"] == "trap"


def test_lastfm_refresh_reprocesses_nonspotify_rows():
    conn = _conn()
    db.insert_lastfm_play(
        conn, track_id="", name="S", artist="Regional",
        album_art_url="", played_at="2023-11-14T00:00:00+00:00",
        played_at_unix=1700000000,
    )
    sp = FakeSpotify({})  # Spotify blocked / no hit -> Last.fm path
    fetch = lambda url: '{"toptags": {"tag": [{"name": "detroit rap", "count": 100}]}}'
    enrich_all(conn, sp, "KEY", fetch=fetch, skip_spotify=True, sleep=lambda s: None)
    assert db.get_artist_genre(conn, "regional")["genre_source"] == "lastfm"

    # A plain re-run skips it; a Last.fm refresh re-processes it.
    again = enrich_all(conn, sp, "KEY", fetch=fetch, skip_spotify=True,
                       sleep=lambda s: None)
    assert again["skipped"] == 1 and again["lastfm"] == 0

    refreshed = enrich_all(conn, sp, "KEY", fetch=fetch, skip_spotify=True,
                           refresh=True, sleep=lambda s: None)
    assert refreshed["skipped"] == 0 and refreshed["lastfm"] == 1


def test_enrich_all_caches_and_is_resumable():
    conn = _conn()
    db.insert_lastfm_play(
        conn, track_id="", name="S", artist="2hollis",
        album_art_url="", played_at="2023-11-14T00:00:00+00:00",
        played_at_unix=1700000000,
    )
    sp = FakeSpotify({"2hollis": ("id1", ["rage"])})
    summary = enrich_all(conn, sp, "KEY", sleep=lambda s: None)
    assert summary["spotify"] == 1
    row = db.get_artist_genre(conn, "2hollis")
    assert row["primary_bucket"] == "rage"
    # Second run skips the already-cached artist.
    summary2 = enrich_all(conn, sp, "KEY", sleep=lambda s: None)
    assert summary2["skipped"] == 1
