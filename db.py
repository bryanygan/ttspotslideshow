"""SQLite layer: schema, connection, and the handful of queries the logger needs.

Two tables:
  plays   -> one row per play event (the source of truth for everything later).
  artists -> a cache of artist_id -> genres, so we don't refetch genres for the
             same artist on every run (Spotify removed the batch artist endpoint,
             so each lookup is a separate API call -- caching matters).
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, Optional

from config import DB_PATH, ensure_dirs
from text_norm import normalize

CREATE_PLAYS = """
CREATE TABLE IF NOT EXISTS plays (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id       TEXT    NOT NULL DEFAULT '',
    name           TEXT    NOT NULL,
    artist         TEXT    NOT NULL,
    artist_id      TEXT,
    artist_genre   TEXT,
    album_art_url  TEXT,
    popularity     INTEGER,
    played_at      TEXT    NOT NULL,
    source         TEXT    NOT NULL DEFAULT 'spotify',
    played_at_unix INTEGER,
    UNIQUE(source, artist, track_id, name, played_at)
);
"""

CREATE_ARTIST_GENRES = """
CREATE TABLE IF NOT EXISTS artist_genres (
    artist_key        TEXT PRIMARY KEY,
    display_name      TEXT,
    spotify_artist_id TEXT,
    raw_genres        TEXT,
    lastfm_tags       TEXT,
    primary_bucket    TEXT NOT NULL,
    genre_source      TEXT NOT NULL,
    fetched_at        TEXT
);
"""

CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_plays_played_at ON plays(played_at);
CREATE INDEX IF NOT EXISTS idx_plays_unix ON plays(played_at_unix);
"""

# Legacy: keep artists table for backward compat (existing tests may reference it)
CREATE_ARTISTS = """
CREATE TABLE IF NOT EXISTS artists (
    artist_id  TEXT PRIMARY KEY,
    name       TEXT,
    genres     TEXT,   -- comma-separated list, '' if the artist has none
    fetched_at TEXT
);
"""


def _iso_to_unix(iso: str) -> int:
    """ISO-8601 timestamp (may end in 'Z') -> epoch seconds."""
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def migrate(conn: sqlite3.Connection) -> None:
    """Bring a DB up to the current schema. Idempotent and safe to re-run."""
    info = conn.execute("PRAGMA table_info(plays)").fetchall()
    cols = [r[1] for r in info]
    if not info:
        conn.execute(CREATE_PLAYS)
    elif "source" not in cols:
        # Old schema: rebuild plays with the new columns + UNIQUE, backfilling.
        conn.execute("ALTER TABLE plays RENAME TO plays_old")
        conn.execute(CREATE_PLAYS)
        old_rows = conn.execute(
            "SELECT track_id, name, artist, artist_id, artist_genre, "
            "album_art_url, popularity, played_at FROM plays_old"
        ).fetchall()
        for r in old_rows:
            conn.execute(
                "INSERT OR IGNORE INTO plays "
                "(track_id, name, artist, artist_id, artist_genre, album_art_url, "
                " popularity, played_at, source, played_at_unix) "
                "VALUES (?,?,?,?,?,?,?,?, 'spotify', ?)",
                (r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7],
                 _iso_to_unix(r[7])),
            )
        conn.execute("DROP TABLE plays_old")
    conn.execute(CREATE_ARTIST_GENRES)
    conn.execute(CREATE_ARTISTS)
    conn.executescript(CREATE_INDEXES)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open a connection with row access by column name. Commits on success."""
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create/upgrade tables. Safe to run anytime."""
    with connect() as conn:
        migrate(conn)


def latest_played_at() -> Optional[str]:
    """Most recent played_at we've already logged (ISO string), or None if empty.

    Used to fetch only newer plays from Spotify on each run.
    """
    with connect() as conn:
        row = conn.execute("SELECT MAX(played_at) AS m FROM plays").fetchone()
        return row["m"] if row and row["m"] else None


def insert_play(
    conn: sqlite3.Connection,
    *,
    track_id: str,
    name: str,
    artist: str,
    artist_id: Optional[str],
    artist_genre: Optional[str],
    album_art_url: Optional[str],
    popularity: Optional[int],
    played_at: str,
) -> bool:
    """Insert one play. Returns True if a new row was added, False if duplicate."""
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO plays
            (track_id, name, artist, artist_id, artist_genre,
             album_art_url, popularity, played_at, source, played_at_unix)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'spotify', ?)
        """,
        (track_id, name, artist, artist_id, artist_genre,
         album_art_url, popularity, played_at, _iso_to_unix(played_at)),
    )
    return cur.rowcount > 0


def get_cached_genres(conn: sqlite3.Connection, artist_id: str) -> Optional[str]:
    """Return cached comma-separated genres for an artist, or None if not cached.

    Note: a cached artist with no genres is stored as '' (empty string), which is
    distinct from None ("never looked up").
    """
    row = conn.execute(
        "SELECT genres FROM artists WHERE artist_id = ?", (artist_id,)
    ).fetchone()
    return row["genres"] if row is not None else None


def cache_artist(
    conn: sqlite3.Connection,
    *,
    artist_id: str,
    name: str,
    genres: str,
    fetched_at: str,
) -> None:
    """Store/refresh an artist's genres so future runs skip the API call."""
    conn.execute(
        """
        INSERT INTO artists (artist_id, name, genres, fetched_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(artist_id) DO UPDATE SET
            name = excluded.name,
            genres = excluded.genres,
            fetched_at = excluded.fetched_at
        """,
        (artist_id, name, genres, fetched_at),
    )


def play_count() -> int:
    """Total number of logged plays (handy for a quick sanity check)."""
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) AS c FROM plays").fetchone()["c"]


def insert_lastfm_play(
    conn: sqlite3.Connection,
    *,
    track_id: str,
    name: str,
    artist: str,
    album_art_url: str,
    played_at: str,
    played_at_unix: int,
) -> bool:
    """Insert one Last.fm scrobble. Returns True if a new row was added."""
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO plays
            (track_id, name, artist, artist_id, artist_genre, album_art_url,
             popularity, played_at, source, played_at_unix)
        VALUES (?, ?, ?, NULL, NULL, ?, NULL, ?, 'lastfm', ?)
        """,
        (track_id, name, artist, album_art_url, played_at, played_at_unix),
    )
    return cur.rowcount > 0


def play_count_by_source(conn: sqlite3.Connection) -> dict:
    """Return {source: count} over the plays table."""
    rows = conn.execute(
        "SELECT source, COUNT(*) AS c FROM plays GROUP BY source"
    ).fetchall()
    return {r["source"]: r["c"] for r in rows}


def canonical_plays(conn: sqlite3.Connection, window_seconds: int = 120) -> list:
    """Return plays with cross-source duplicates collapsed (Spotify preferred)."""
    rows = conn.execute(
        "SELECT * FROM plays WHERE played_at_unix IS NOT NULL "
        "ORDER BY played_at_unix ASC"
    ).fetchall()

    result: list = []
    recent: list[dict] = []  # kept rows still inside the window
    for row in rows:
        unix = row["played_at_unix"]
        key = (normalize(row["artist"]), normalize(row["name"]))
        recent = [r for r in recent if unix - r["unix"] <= window_seconds]

        twin = next(
            (r for r in recent if r["key"] == key and r["source"] != row["source"]),
            None,
        )
        if twin is not None:
            # Cross-source duplicate. Prefer the Spotify row.
            if row["source"] == "spotify" and twin["source"] == "lastfm":
                result[twin["index"]] = row
                twin["source"] = "spotify"
            continue

        result.append(row)
        recent.append(
            {"unix": unix, "key": key, "source": row["source"],
             "index": len(result) - 1}
        )
    return result
