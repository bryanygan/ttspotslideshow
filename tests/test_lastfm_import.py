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


def test_latest_lastfm_played_at_unix():
    conn = _conn()
    db.migrate(conn)
    # empty
    assert db.latest_lastfm_played_at_unix(conn) is None
    # Spotify play (should not count for lastfm)
    db.insert_play(
        conn, track_id="s1", name="TrackS", artist="ArtistS",
        artist_id="a1", artist_genre="pop", album_art_url="",
        popularity=80, played_at="2026-06-24T00:00:00Z"
    )
    assert db.latest_lastfm_played_at_unix(conn) is None
    # Lastfm play
    db.insert_lastfm_play(
        conn, track_id="l1", name="TrackL", artist="ArtistL",
        album_art_url="", played_at="2026-06-24T00:00:00Z",
        played_at_unix=1782260000
    )
    assert db.latest_lastfm_played_at_unix(conn) == 1782260000


def test_import_recent_from_api_paging_and_mapping():
    conn = _conn()
    db.migrate(conn)

    # Let's mock the fetch to return page 1 then page 2.
    pages = [
        # page 1
        {
            "recenttracks": {
                "track": [
                    {
                        "artist": {"#text": "Artist A"},
                        "name": "Track A",
                        "mbid": "mbidA",
                        "image": [
                            {"size": "extralarge", "#text": "https://img.jpg"}
                        ],
                        "date": {"uts": "1782260100"}
                    },
                    {
                        "artist": {"#text": "Artist B"},
                        "name": "Track B",
                        "mbid": "",
                        "image": [],
                        "@attr": {"nowplaying": "true"}  # will be skipped
                    }
                ],
                "@attr": {
                    "totalPages": "2",
                    "page": "1"
                }
            }
        },
        # page 2
        {
            "recenttracks": {
                "track": [
                    {
                        "artist": {"#text": "Artist C"},
                        "name": "Track C",
                        "mbid": "mbidC",
                        "image": [],
                        "date": {"uts": "1782260000"}
                    }
                ],
                "@attr": {
                    "totalPages": "2",
                    "page": "2"
                }
            }
        }
    ]

    import json
    urls_called = []
    def fetch(url):
        urls_called.append(url)
        p = pages[len(urls_called) - 1]
        return json.dumps(p)

    from ingest.lastfm_import import import_recent_from_api
    added = import_recent_from_api(
        conn, api_key="KEY", username="User",
        since_unix=1782250000, fetch=fetch
    )

    assert added == 2
    assert len(urls_called) == 2
    assert "page=1" in urls_called[0]
    assert "page=2" in urls_called[1]
    assert "from=1782250000" in urls_called[0]

    rows = conn.execute("SELECT * FROM plays ORDER BY played_at_unix ASC").fetchall()
    assert len(rows) == 2
    assert rows[0]["name"] == "Track C"
    assert rows[0]["track_id"] == "mbidC"
    assert rows[1]["name"] == "Track A"
    assert rows[1]["track_id"] == "mbidA"
    assert rows[1]["album_art_url"] == "https://img.jpg"
