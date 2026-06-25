import sqlite3

import db
from slideshow.window import resolve_window


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db.migrate(c)
    return c


def _iso(u):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(u, timezone.utc).isoformat()


def _play(conn, name, unix):
    db.insert_lastfm_play(
        conn, track_id="", name=name, artist="A" + name, album_art_url="",
        played_at=_iso(unix), played_at_unix=unix,
    )


NOW = 1_000_000_000
DAY = 86400


def test_returns_first_window_meeting_target():
    conn = _conn()
    # 3 distinct tracks within the last 2 days.
    for i in range(3):
        _play(conn, f"t{i}", NOW - DAY)
    cands, days = resolve_window(conn, target=3, floor=2, now_unix=NOW)
    assert days == 2
    assert len(cands) == 3


def test_widens_when_recent_window_is_thin():
    conn = _conn()
    _play(conn, "recent", NOW - DAY)            # 1 in last 2 days
    for i in range(4):
        _play(conn, f"old{i}", NOW - 5 * DAY)   # 4 more within 7 days
    cands, days = resolve_window(conn, target=4, floor=2, now_unix=NOW)
    assert days == 7            # 2 and 4 day windows are too thin; 7 reaches target
    assert len(cands) == 5


def test_returns_largest_when_never_reaches_target():
    conn = _conn()
    for i in range(2):
        _play(conn, f"t{i}", NOW - DAY)
    cands, days = resolve_window(conn, target=16, floor=12, now_unix=NOW)
    assert days == 30           # widened all the way
    assert len(cands) == 2
