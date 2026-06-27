import sqlite3

import db
from ingest.enrich_popularity import enrich_all_popularity


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db.migrate(c)
    return c


def _seed(monkeypatch, tracks):
    """Make canonical_plays return the given (artist, name) rows."""
    monkeypatch.setattr(
        db, "canonical_plays",
        lambda c, *a, **k: [{"artist": ar, "name": nm} for ar, nm in tracks],
    )


def test_enriches_missing_and_counts(monkeypatch):
    conn = _conn()
    _seed(monkeypatch, [("Artist A", "Song A"), ("Artist B", "Song B")])

    def fake_resolve(artist, title, **k):
        if artist == "Artist A":
            return {"listeners": 1000, "popularity": 50, "source": "lastfm"}
        return {"listeners": None, "popularity": None, "source": "none"}

    monkeypatch.setattr(
        "ingest.enrich_popularity.resolve_popularity", fake_resolve
    )
    summary = enrich_all_popularity(
        conn, lastfm_api_key="K", listenbrainz_token="T", sleep=lambda s: None,
    )
    assert summary["processed"] == 2
    assert summary["lastfm"] == 1
    assert summary["none"] == 1
    assert db.get_track_popularity(conn, "artist a\tsong a")["popularity"] == 50
    # 'none' rows are still cached (so we don't refetch them every run).
    assert db.get_track_popularity(conn, "artist b\tsong b")["source"] == "none"


def test_resumable_skips_cached(monkeypatch):
    conn = _conn()
    _seed(monkeypatch, [("Artist A", "Song A")])
    db.upsert_track_popularity(
        conn, track_key="artist a\tsong a", listeners=1, popularity=1,
        source="lastfm", fetched_at="t",
    )
    calls = []
    monkeypatch.setattr(
        "ingest.enrich_popularity.resolve_popularity",
        lambda *a, **k: calls.append(1) or {"listeners": 1, "popularity": 1, "source": "lastfm"},
    )
    summary = enrich_all_popularity(
        conn, lastfm_api_key="K", listenbrainz_token="T", sleep=lambda s: None,
    )
    assert summary["processed"] == 0  # already cached, nothing fetched
    assert calls == []


def test_refresh_reprocesses_all(monkeypatch):
    conn = _conn()
    _seed(monkeypatch, [("Artist A", "Song A")])
    db.upsert_track_popularity(
        conn, track_key="artist a\tsong a", listeners=1, popularity=1,
        source="lastfm", fetched_at="t",
    )
    monkeypatch.setattr(
        "ingest.enrich_popularity.resolve_popularity",
        lambda *a, **k: {"listeners": 9999, "popularity": 88, "source": "lastfm"},
    )
    summary = enrich_all_popularity(
        conn, lastfm_api_key="K", listenbrainz_token="T", sleep=lambda s: None,
        refresh=True,
    )
    assert summary["processed"] == 1
    assert db.get_track_popularity(conn, "artist a\tsong a")["popularity"] == 88
