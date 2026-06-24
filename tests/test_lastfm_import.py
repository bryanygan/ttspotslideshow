import sqlite3

import db
from ingest.lastfm_import import iter_scrobbles, import_scrobbles

SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<scrobbles>
  <track nowplaying="true">
    <artist>NowPlaying Artist</artist><name>Live One</name>
    <image size="extralarge">https://x/300x300/abc.jpg</image>
  </track>
  <track>
    <artist mbid="a1">2hollis</artist><name>destroy me</name>
    <mbid>t1</mbid>
    <image size="extralarge">https://lastfm/i/u/300x300/cover1.jpg</image>
    <date uts="1700000000">24 Jun 2026, 02:41</date>
  </track>
  <track>
    <artist mbid="a2">Placeholder Art</artist><name>No Art</name>
    <image size="extralarge">https://lastfm/i/u/300x300/2a96cbd8b46e442fc41c2b86b821562f.png</image>
    <date uts="1700000100">24 Jun 2026, 02:43</date>
  </track>
  <track>
    <artist></artist><name></name>
  </track>
</scrobbles>
"""


def _write(tmp_path):
    p = tmp_path / "scrobbles.xml"
    p.write_text(SAMPLE_XML, encoding="utf-8")
    return p


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    return c


def test_iter_skips_nowplaying_and_malformed(tmp_path):
    rows = list(iter_scrobbles(_write(tmp_path)))
    # Only the two real, dated tracks survive.
    assert len(rows) == 2
    names = {r["name"] for r in rows}
    assert names == {"destroy me", "No Art"}


def test_iter_maps_fields_and_unix(tmp_path):
    rows = {r["name"]: r for r in iter_scrobbles(_write(tmp_path))}
    d = rows["destroy me"]
    assert d["artist"] == "2hollis"
    assert d["track_id"] == "t1"
    assert d["played_at_unix"] == 1700000000
    assert d["played_at"].startswith("2023-11-14T")  # 1700000000 UTC
    assert d["album_art_url"].endswith("cover1.jpg")


def test_iter_blanks_placeholder_art(tmp_path):
    rows = {r["name"]: r for r in iter_scrobbles(_write(tmp_path))}
    assert rows["No Art"]["album_art_url"] == ""


def test_import_inserts_and_is_idempotent(tmp_path):
    conn = _conn()
    db.migrate(conn)
    imported, skipped = import_scrobbles(conn, _write(tmp_path))
    assert imported == 2
    assert skipped == 2  # nowplaying + malformed
    again_imported, _ = import_scrobbles(conn, _write(tmp_path))
    assert again_imported == 0  # idempotent
    assert db.play_count_by_source(conn)["lastfm"] == 2
