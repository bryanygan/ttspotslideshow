import pytest

from slideshow.playlist_parse import search_spotify_tracks, PlaylistParseError


class FakeSpotify:
    """Minimal spotipy-compatible stub for search()."""
    def __init__(self, items):
        self._items = items

    def search(self, q, type="track", limit=20):
        return {"tracks": {"items": self._items}}


def _track(name, artist, art="http://img/x.jpg", pop=42, tid="id1"):
    return {
        "id": tid,
        "name": name,
        "type": "track",
        "popularity": pop,
        "artists": [{"name": artist}],
        "album": {"images": [{"url": art}]},
    }


def test_search_shapes_candidates(monkeypatch):
    fake = FakeSpotify([_track("Sky", "2hollis", pop=37, tid="abc")])
    monkeypatch.setattr("spotify_client.get_client", lambda: fake)
    out = search_spotify_tracks("sky", conn=None)
    assert len(out) == 1
    c = out[0]
    assert c["title"] == "Sky"
    assert c["artist"] == "2hollis"
    assert c["album_art_url"] == "http://img/x.jpg"
    assert c["track_id"] == "abc"
    assert c["popularity"] == 37
    assert c["track_key"] == "2hollis\tsky"


def test_search_dedupes_and_skips_incomplete(monkeypatch):
    items = [
        _track("Sky", "2hollis", tid="a"),
        _track("Sky", "2hollis", tid="b"),   # same track_key -> deduped
        {"id": "c", "name": "", "type": "track", "artists": [{"name": "X"}]},  # no name
    ]
    monkeypatch.setattr("spotify_client.get_client", lambda: FakeSpotify(items))
    out = search_spotify_tracks("sky", conn=None)
    assert len(out) == 1


def test_search_empty_query_raises():
    with pytest.raises(PlaylistParseError):
        search_spotify_tracks("   ", conn=None)


def test_search_api_failure_raises(monkeypatch):
    class Boom:
        def search(self, *a, **k):
            raise RuntimeError("429")
    monkeypatch.setattr("spotify_client.get_client", lambda: Boom())
    with pytest.raises(PlaylistParseError):
        search_spotify_tracks("sky", conn=None)
