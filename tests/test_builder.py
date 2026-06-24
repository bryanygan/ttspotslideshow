import sqlite3
from datetime import datetime, timezone

from PIL import Image

import db
import render.art as rart
from slideshow.builder import build_slideshow


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db.migrate(c)
    return c


def _iso(u):
    return datetime.fromtimestamp(u, timezone.utc).isoformat()


NOW = 1_000_000_000
DAY = 86400


def test_build_writes_one_slide_and_records_featured(tmp_path, monkeypatch):
    conn = _conn()
    # 4 distinct tracks across 2 buckets, all within the last day.
    for i in range(4):
        db.insert_lastfm_play(
            conn, track_id="", name=f"Song{i}", artist=f"Artist{i}",
            album_art_url="https://lastfm/300.jpg",
            played_at=_iso(NOW - DAY), played_at_unix=NOW - DAY,
        )

    # iTunes lookup: no results -> falls back to album_art_url.
    fetch = lambda url: '{"results": []}'
    # Art download: write a real image instead of hitting the network.
    monkeypatch.setattr(
        rart, "_default_fetch",
        lambda url, dest: Image.new("RGB", (300, 300), (90, 90, 90)).save(dest),
    )

    summary = build_slideshow(
        conn, out_root=tmp_path / "out", target=4, floor=4,
        now_unix=NOW, today="2026-06-24", fetch=fetch, cache_dir=tmp_path / "art",
    )

    assert summary["slide_count"] == 1
    assert summary["track_count"] == 4
    slide = tmp_path / "out" / "2026-06-24" / "slide_1.png"
    assert slide.exists()
    assert Image.open(slide).size == (1080, 1920)
    # Featured history recorded the 4 tracks.
    assert len(db.featured_history(conn)) == 4


def test_build_with_no_plays_writes_nothing(tmp_path):
    conn = _conn()
    summary = build_slideshow(
        conn, out_root=tmp_path / "out", now_unix=NOW, today="2026-06-24",
        fetch=lambda url: '{"results": []}', cache_dir=tmp_path / "art",
    )
    assert summary["track_count"] == 0
    assert summary["slide_count"] == 0
    assert not (tmp_path / "out" / "2026-06-24").exists()
