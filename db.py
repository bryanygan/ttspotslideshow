"""SQLite layer: schema, connection, and all the queries the pipeline needs.

Tables:
  plays         -> one row per play event (the source of truth for everything later).
  artist_genres -> Phase-3 genre source for selection, keyed by normalized artist name.
  featured_tracks -> what the slideshow has posted, for the novelty/freshness signal.
  artists       -> Phase-1 logger's genre cache (artist_id -> genres). Spotify removed
                   the batch artist endpoint, so each lookup is a separate API call --
                   caching matters.
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

# Phase-1 logger's genre cache (artist_id -> genres). Still used by the logger via
# get_cached_genres/cache_artist; distinct from artist_genres (the Phase-3 selection
# source, keyed by normalized artist name).
CREATE_ARTISTS = """
CREATE TABLE IF NOT EXISTS artists (
    artist_id  TEXT PRIMARY KEY,
    name       TEXT,
    genres     TEXT,   -- comma-separated list, '' if the artist has none
    fetched_at TEXT
);
"""

CREATE_FEATURED = """
CREATE TABLE IF NOT EXISTS featured_tracks (
    track_key          TEXT PRIMARY KEY,
    last_featured_date TEXT NOT NULL,
    times_featured     INTEGER NOT NULL
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
    conn.execute(CREATE_FEATURED)
    conn.execute(
        "UPDATE featured_tracks SET last_featured_date = REPLACE(last_featured_date, 'recap-', '') "
        "WHERE last_featured_date LIKE 'recap-%'"
    )
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


def latest_played_at(source: Optional[str] = None) -> Optional[str]:
    """Most recent played_at we've logged (ISO string), or None if empty.

    Pass ``source='spotify'`` for the logger's "fetch since" cursor: the Last.fm
    import holds timestamps newer than the last Spotify play, so an unscoped MAX
    would push the cursor forward and silently skip real Spotify plays.
    """
    with connect() as conn:
        if source is not None:
            row = conn.execute(
                "SELECT MAX(played_at) AS m FROM plays WHERE source = ?",
                (source,),
            ).fetchone()
        else:
            row = conn.execute("SELECT MAX(played_at) AS m FROM plays").fetchone()
        return row["m"] if row and row["m"] else None


def latest_lastfm_played_at_unix(conn: sqlite3.Connection) -> Optional[int]:
    """Return the maximum played_at_unix for Last.fm plays, or None."""
    row = conn.execute(
        "SELECT MAX(played_at_unix) AS m FROM plays WHERE source = 'lastfm'"
    ).fetchone()
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


def canonical_plays(conn: sqlite3.Connection, window_seconds: int = 120,
                    since_unix: Optional[int] = None) -> list:
    """Return plays with cross-source duplicates collapsed (Spotify preferred).

    When ``since_unix`` is given, only plays at/after it are returned, and the
    query is pre-filtered to ``>= since_unix - window_seconds``. The small
    look-back keeps cross-source dedup correct at the boundary: a kept play >=
    since_unix can only have a twin within ``window_seconds`` before it, which the
    buffer includes. This avoids scanning the whole (large) table for a recent
    window — the bottleneck for slideshow selection.
    """
    if since_unix is not None:
        rows = conn.execute(
            "SELECT * FROM plays WHERE played_at_unix IS NOT NULL "
            "AND played_at_unix >= ? ORDER BY played_at_unix ASC",
            (since_unix - window_seconds,),
        ).fetchall()
    else:
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

    # The look-back buffer rows (before since_unix) only exist to make boundary
    # dedup correct; drop them so the contract is "canonical plays at/after since".
    if since_unix is not None:
        result = [r for r in result if r["played_at_unix"] >= since_unix]
    return result


def distinct_artist_names(conn: sqlite3.Connection) -> list:
    """Distinct non-empty artist display names across all plays."""
    rows = conn.execute(
        "SELECT DISTINCT artist FROM plays WHERE artist <> '' ORDER BY artist"
    ).fetchall()
    return [r["artist"] for r in rows]


def upsert_artist_genre(
    conn: sqlite3.Connection,
    *,
    artist_key: str,
    display_name: str,
    spotify_artist_id: str,
    raw_genres: str,
    lastfm_tags: str,
    primary_bucket: str,
    genre_source: str,
    fetched_at: str,
) -> None:
    """Insert/replace one artist's resolved genre record."""
    conn.execute(
        """
        INSERT INTO artist_genres
            (artist_key, display_name, spotify_artist_id, raw_genres,
             lastfm_tags, primary_bucket, genre_source, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(artist_key) DO UPDATE SET
            display_name=excluded.display_name,
            spotify_artist_id=excluded.spotify_artist_id,
            raw_genres=excluded.raw_genres,
            lastfm_tags=excluded.lastfm_tags,
            primary_bucket=excluded.primary_bucket,
            genre_source=excluded.genre_source,
            fetched_at=excluded.fetched_at
        """,
        (artist_key, display_name, spotify_artist_id, raw_genres,
         lastfm_tags, primary_bucket, genre_source, fetched_at),
    )


def get_artist_genre(conn: sqlite3.Connection, artist_key: str):
    """Return the cached artist_genres row, or None."""
    return conn.execute(
        "SELECT * FROM artist_genres WHERE artist_key = ?", (artist_key,)
    ).fetchone()


def bucket_distribution(conn: sqlite3.Connection) -> dict:
    """Return {primary_bucket: artist_count} from artist_genres."""
    rows = conn.execute(
        "SELECT primary_bucket, COUNT(*) AS c FROM artist_genres "
        "GROUP BY primary_bucket ORDER BY c DESC"
    ).fetchall()
    return {r["primary_bucket"]: r["c"] for r in rows}


def featured_history(conn: sqlite3.Connection) -> dict:
    """Return {track_key: last_featured_date} for every previously featured track."""
    rows = conn.execute(
        "SELECT track_key, last_featured_date FROM featured_tracks"
    ).fetchall()
    return {r["track_key"]: r["last_featured_date"] for r in rows}


def record_featured(conn: sqlite3.Connection, track_keys: list[str],
                    run_date: str) -> None:
    """Record that the given track_keys were featured on run_date (YYYY-MM-DD)."""
    for key in track_keys:
        conn.execute(
            """
            INSERT INTO featured_tracks (track_key, last_featured_date, times_featured)
            VALUES (?, ?, 1)
            ON CONFLICT(track_key) DO UPDATE SET
                last_featured_date = excluded.last_featured_date,
                times_featured = featured_tracks.times_featured + 1
            """,
            (key, run_date),
        )


def window_track_candidates(conn: sqlite3.Connection, start_unix: int) -> list:
    """Aggregate canonical plays since start_unix into unique candidate tracks."""
    genres = {
        r["artist_key"]: r["primary_bucket"]
        for r in conn.execute(
            "SELECT artist_key, primary_bucket FROM artist_genres"
        ).fetchall()
    }

    groups: dict = {}
    for r in canonical_plays(conn, since_unix=start_unix):
        unix = r["played_at_unix"]
        artist_key = normalize(r["artist"])
        track_key = artist_key + "\t" + normalize(r["name"])
        g = groups.get(track_key)
        if g is None:
            # First play seen for this track: it is the representative one so far.
            groups[track_key] = {
                "track_key": track_key,
                "play_count": 1,
                "track_id": r["track_id"],
                "title": r["name"],
                "artist": r["artist"],
                "album_art_url": r["album_art_url"],
                "last_played_unix": unix,
                "primary_bucket": genres.get(artist_key, "unknown"),
                "popularity": r["popularity"],
            }
            continue
        g["play_count"] += 1
        if unix >= g["last_played_unix"]:
            # Refresh representative fields from the most recent play.
            g["last_played_unix"] = unix
            g["track_id"] = r["track_id"]
            g["title"] = r["name"]
            g["artist"] = r["artist"]
            g["album_art_url"] = r["album_art_url"]
            g["popularity"] = r["popularity"]
    return list(groups.values())


def random_unique_tracks(conn: sqlite3.Connection, limit: int = 100) -> list:
    """Return a list of limit random unique tracks from the plays table."""
    rows = conn.execute(
        """
        SELECT name, artist, MAX(album_art_url) as album_art_url
        FROM plays
        GROUP BY artist, name
        ORDER BY RANDOM()
        LIMIT ?
        """,
        (limit,)
    ).fetchall()
    return [{"title": r[0], "artist": r[1], "album_art_url": r[2]} for r in rows]


def update_track_art(conn: sqlite3.Connection, artist: str, name: str, album_art_url: str) -> None:
    """Update the album_art_url for all occurrences of a track in the plays table."""
    conn.execute(
        "UPDATE plays SET album_art_url = ? WHERE artist = ? AND name = ?",
        (album_art_url, artist, name)
    )
