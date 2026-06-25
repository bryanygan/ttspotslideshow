from contextlib import contextmanager

import spotipy

import db
import logger


# --- pure helpers ---------------------------------------------------------

def test_iso_to_unix_ms():
    assert logger._iso_to_unix_ms("2023-11-14T22:13:20Z") == 1700000000 * 1000
    assert logger._iso_to_unix_ms("2023-11-14T22:13:20+00:00") == 1700000000000


def test_primary_image_url():
    track = {"album": {"images": [{"url": "big"}, {"url": "small"}]}}
    assert logger._primary_image_url(track) == "big"  # Spotify lists largest-first
    assert logger._primary_image_url({"album": {"images": []}}) is None
    assert logger._primary_image_url({}) is None


# --- genre resolution -----------------------------------------------------

class FakeArtistSpotify:
    """Stub exposing just .artist(), the call _resolve_genre makes."""

    def __init__(self, genres_by_id=None, raise_on=None):
        self.genres_by_id = genres_by_id or {}
        self.raise_on = raise_on or set()
        self.calls = 0

    def artist(self, artist_id):
        self.calls += 1
        if artist_id in self.raise_on:
            raise spotipy.SpotifyException(429, -1, "rate limited")
        return {"genres": self.genres_by_id.get(artist_id, [])}


def test_resolve_genre_unknown_without_artist_id(conn):
    assert logger._resolve_genre(FakeArtistSpotify(), conn, None, "X") == "unknown"


def test_resolve_genre_fetches_then_serves_from_cache(conn):
    sp = FakeArtistSpotify({"a1": ["rage", "trap"]})
    assert logger._resolve_genre(sp, conn, "a1", "Carti") == "rage"
    assert sp.calls == 1
    # Second lookup is cached -> no further API call (even one that would raise).
    sp_boom = FakeArtistSpotify(raise_on={"a1"})
    assert logger._resolve_genre(sp_boom, conn, "a1", "Carti") == "rage"
    assert sp_boom.calls == 0


def test_resolve_genre_handles_spotify_exception_and_caches_empty(conn):
    sp = FakeArtistSpotify(raise_on={"a1"})
    assert logger._resolve_genre(sp, conn, "a1", "Carti") == "unknown"
    # An empty-genre artist is cached as '' so we don't refetch it forever.
    assert db.get_cached_genres(conn, "a1") == ""


# --- end-to-end ingest (offline) -----------------------------------------

class FakeRecentSpotify(FakeArtistSpotify):
    def __init__(self, items, **kw):
        super().__init__(**kw)
        self.items = items

    def current_user_recently_played(self, limit=50, after=None):
        return {"items": self.items}


def test_latest_played_at_is_source_scoped(conn, monkeypatch):
    # The Last.fm import holds newer timestamps than the last Spotify play; the
    # logger's cursor must ignore them or it skips real Spotify plays.
    db.insert_play(
        conn, track_id="s1", name="S", artist="A", artist_id="a",
        artist_genre=None, album_art_url="", popularity=None,
        played_at="2026-06-20T00:00:00+00:00",
    )
    db.insert_lastfm_play(
        conn, track_id="", name="L", artist="B", album_art_url="",
        played_at="2026-06-25T00:00:00+00:00", played_at_unix=1782345600,
    )

    @contextmanager
    def fake_connect():
        yield conn
    monkeypatch.setattr(db, "connect", fake_connect)

    assert db.latest_played_at(source="spotify") == "2026-06-20T00:00:00+00:00"
    assert db.latest_played_at() == "2026-06-25T00:00:00+00:00"  # unscoped = newer


def test_log_recent_plays_inserts_and_is_idempotent(conn, monkeypatch):
    items = [{
        "track": {
            "id": "t1", "name": "Song",
            "album": {"images": [{"url": "art"}]},
            "artists": [{"id": "a1", "name": "Carti"}],
        },
        "played_at": "2023-11-14T22:13:20Z",
    }]
    sp = FakeRecentSpotify(items, genres_by_id={"a1": ["rage"]})

    monkeypatch.setattr(logger, "get_client", lambda: sp)
    monkeypatch.setattr(db, "init_db", lambda: None)
    monkeypatch.setattr(db, "latest_played_at", lambda source=None: None)

    @contextmanager
    def fake_connect():
        yield conn
    monkeypatch.setattr(db, "connect", fake_connect)

    assert logger.log_recent_plays() == 1
    assert logger.log_recent_plays() == 0  # same play -> deduped
    assert db.play_count_by_source(conn)["spotify"] == 1
    row = conn.execute("SELECT artist_genre FROM plays WHERE track_id='t1'").fetchone()
    assert row["artist_genre"] == "rage"
