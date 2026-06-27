import sqlite3

import db


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db.migrate(c)
    return c


def test_upsert_and_get_roundtrip():
    conn = _conn()
    db.upsert_track_popularity(
        conn, track_key="artist a\tsong a", listeners=1234,
        popularity=42, source="lastfm", fetched_at="2026-06-27T00:00:00Z",
    )
    row = db.get_track_popularity(conn, "artist a\tsong a")
    assert row is not None
    assert row["listeners"] == 1234
    assert row["popularity"] == 42
    assert row["source"] == "lastfm"


def test_upsert_replaces_existing():
    conn = _conn()
    for pop in (10, 55):
        db.upsert_track_popularity(
            conn, track_key="k", listeners=pop * 10, popularity=pop,
            source="lastfm", fetched_at="t",
        )
    row = db.get_track_popularity(conn, "k")
    assert row["popularity"] == 55  # second write wins, no duplicate row


def test_get_missing_returns_none():
    conn = _conn()
    assert db.get_track_popularity(conn, "nope") is None


def test_track_keys_missing_popularity(monkeypatch):
    conn = _conn()
    # Two canonical tracks; cache one, expect the other reported missing.
    monkeypatch.setattr(
        db, "canonical_plays",
        lambda c: [
            {"artist": "Artist A", "name": "Song A"},
            {"artist": "Artist B", "name": "Song B"},
        ],
    )
    db.upsert_track_popularity(
        conn, track_key="artist a\tsong a", listeners=1, popularity=1,
        source="lastfm", fetched_at="t",
    )
    missing = db.track_keys_missing_popularity(conn)
    assert "artist b\tsong b" in missing
    assert "artist a\tsong a" not in missing
