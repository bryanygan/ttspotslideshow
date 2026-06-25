import sqlite3

from ingest.enrich_cli import run_ingest, build_parser, resolve_modes
from tests.test_genres import FakeSpotify  # reuse the stub


def _modes(*argv):
    return resolve_modes(build_parser().parse_args(list(argv)))


def test_resolve_modes_default():
    assert _modes() == (False, False)  # (skip_spotify, refresh)


def test_resolve_modes_lastfm_only():
    assert _modes("--lastfm-only") == (True, False)


def test_resolve_modes_refresh():
    assert _modes("--refresh") == (False, True)


def test_resolve_modes_lastfm_refresh():
    # Re-do Last.fm genres for non-Spotify rows without touching Spotify.
    assert _modes("--lastfm-refresh") == (True, True)

SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<scrobbles>
  <track>
    <artist>2hollis</artist><name>destroy me</name>
    <image size="extralarge">https://lastfm/i/u/300x300/cover1.jpg</image>
    <date uts="1700000000">x</date>
  </track>
</scrobbles>
"""


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    return c


def test_run_ingest_end_to_end_offline(tmp_path):
    xml = tmp_path / "scrobbles.xml"
    xml.write_text(SAMPLE_XML, encoding="utf-8")
    sp = FakeSpotify({"2hollis": ("id1", ["rage"])})

    summary = run_ingest(_conn(), xml, sp, "KEY", sleep=lambda s: None)

    assert summary["imported"] == 1
    assert summary["enriched"]["spotify"] == 1
    assert summary["canonical_plays"] == 1
    assert summary["buckets"].get("rage") == 1
