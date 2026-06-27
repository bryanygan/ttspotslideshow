import json

from ingest import popularity
from ingest.popularity import (
    fetch_lastfm_listeners,
    fetch_listenbrainz_listeners,
    resolve_popularity,
)


def _lastfm_ok(listeners):
    return json.dumps({"track": {"name": "X", "listeners": str(listeners)}})


def test_lastfm_parses_listeners():
    out = fetch_lastfm_listeners("A", "B", "KEY", fetch=lambda url: _lastfm_ok(900))
    assert out == 900


def test_lastfm_error_payload_returns_none():
    out = fetch_lastfm_listeners(
        "A", "B", "KEY",
        fetch=lambda url: json.dumps({"error": 6, "message": "not found"}),
    )
    assert out is None


def test_lastfm_network_error_returns_none():
    def boom(url):
        raise RuntimeError("timeout")
    assert fetch_lastfm_listeners("A", "B", "KEY", fetch=boom) is None


def test_listenbrainz_two_hop(monkeypatch):
    def fake_fetch(url):
        if "metadata/lookup" in url:
            return json.dumps({"recording_mbid": "mbid-1"})
        raise AssertionError("popularity hop should use the POST helper")

    # The popularity POST is done via an internal helper we monkeypatch.
    monkeypatch.setattr(
        popularity, "_lb_popularity_for_mbid",
        lambda mbid, token, fetch=None: 4321 if mbid == "mbid-1" else None,
    )
    out = fetch_listenbrainz_listeners("A", "B", "TOKEN", fetch=fake_fetch)
    assert out == 4321


def test_listenbrainz_no_mbid_returns_none():
    out = fetch_listenbrainz_listeners(
        "A", "B", "TOKEN",
        fetch=lambda url: json.dumps({}),  # no recording_mbid
    )
    assert out is None


def test_resolve_prefers_lastfm(monkeypatch):
    monkeypatch.setattr(popularity, "fetch_lastfm_listeners", lambda *a, **k: 1000)
    monkeypatch.setattr(popularity, "fetch_listenbrainz_listeners", lambda *a, **k: 9)
    out = resolve_popularity("A", "B", lastfm_api_key="K", listenbrainz_token="T")
    assert out["source"] == "lastfm"
    assert out["listeners"] == 1000
    assert out["popularity"] == popularity.normalize_listeners(1000)


def test_resolve_falls_back_to_listenbrainz(monkeypatch):
    monkeypatch.setattr(popularity, "fetch_lastfm_listeners", lambda *a, **k: None)
    monkeypatch.setattr(popularity, "fetch_listenbrainz_listeners", lambda *a, **k: 500)
    out = resolve_popularity("A", "B", lastfm_api_key="K", listenbrainz_token="T")
    assert out["source"] == "listenbrainz"
    assert out["listeners"] == 500


def test_resolve_none_when_both_miss(monkeypatch):
    monkeypatch.setattr(popularity, "fetch_lastfm_listeners", lambda *a, **k: None)
    monkeypatch.setattr(popularity, "fetch_listenbrainz_listeners", lambda *a, **k: None)
    out = resolve_popularity("A", "B", lastfm_api_key="K", listenbrainz_token="T")
    assert out["source"] == "none"
    assert out["listeners"] is None
    assert out["popularity"] is None
