import sqlite3

import db


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db.migrate(c)
    return c


def test_migrate_creates_featured_table():
    conn = _conn()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(featured_tracks)").fetchall()]
    assert cols, "featured_tracks table missing"
    assert "last_featured_date" in cols and "times_featured" in cols


def test_record_and_read_back():
    conn = _conn()
    db.record_featured(conn, ["carti\tlocation", "yeat\tmoney"], "2026-06-24")
    hist = db.featured_history(conn)
    assert hist == {"carti\tlocation": "2026-06-24", "yeat\tmoney": "2026-06-24"}


def test_record_again_increments_and_updates_date():
    conn = _conn()
    db.record_featured(conn, ["carti\tlocation"], "2026-06-24")
    db.record_featured(conn, ["carti\tlocation"], "2026-06-26")
    row = conn.execute(
        "SELECT last_featured_date, times_featured FROM featured_tracks "
        "WHERE track_key = ?", ("carti\tlocation",)
    ).fetchone()
    assert row["last_featured_date"] == "2026-06-26"
    assert row["times_featured"] == 2
