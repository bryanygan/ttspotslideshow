import sqlite3

from ingest.enrich_cli import run_ingest
from tests.test_genres import FakeSpotify  # reuse the stub

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
