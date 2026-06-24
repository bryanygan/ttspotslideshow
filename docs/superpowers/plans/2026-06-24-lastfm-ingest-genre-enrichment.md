# Last.fm Ingest + Genre Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Load the full Last.fm scrobble history into SQLite (deduplicated against the Spotify logger) and enrich every artist with a genre bucket, exposed via one CLI.

**Architecture:** New `ingest/` package (XML import, Last.fm API client, genre mapping, enrichment) plus extensions to the existing `db.py` (schema migration, `source`/`played_at_unix`, cross-source `canonical_plays`, `artist_genres` table) and `config.py`. Pure helpers are offline-testable; network clients are injected.

**Tech Stack:** Python 3.12, stdlib (`sqlite3`, `xml.etree`, `urllib`, `datetime`), `spotipy` (already present), pytest. No new runtime dependencies.

## Global Constraints

- Python 3.12; use the existing `.venv`. Run python as `.\.venv\Scripts\python.exe`.
- **No new runtime dependencies.** Last.fm API via stdlib `urllib`; XML via stdlib `xml.etree`; Spotify via existing `spotipy`.
- `plays.source TEXT NOT NULL DEFAULT 'spotify'`; `plays.played_at_unix INTEGER` (epoch seconds).
- Within-source dedup: `UNIQUE(source, artist, track_id, name, played_at)`.
- Last.fm rows: `source='lastfm'`, `track_id` = track MBID or `''`.
- Cross-source canonical dedup: same `normalize(artist)`+`normalize(title)`, **different sources**, `|Δ played_at_unix| ≤ window` (default **120s**) → keep one, **prefer the Spotify row**.
- Genre buckets (exact strings): `rage, trap, drill, plugg, boom-bap, melodic-rap, hip-hop, pop, r&b, rock, electronic, indie, country, latin, other, unknown`.
- `bucket_for`: first genre that maps wins; `'other'` if non-empty but unmapped; `'unknown'` if empty.
- Genre flow per artist: Spotify primary → Last.fm `getTopTags` fallback → `'none'`. Resumable (skip already-cached artists).
- `artist_genres` keyed by **normalized artist name** (`text_norm.normalize`). The Phase 1 `artists` table is left untouched.
- `.env` keys: `LAST_FM_API_KEY`, `LAST_FM_SHARED_SECRET`, optional `LASTFM_EXPORT_PATH`.
- All commit messages end with: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

### Task 1: Text normalization (`text_norm.py`)

**Files:**
- Create: `text_norm.py`
- Test: `tests/test_text_norm.py`

**Interfaces:**
- Produces: `normalize(text: str) -> str` — lowercase, strip, collapse internal whitespace, trim a trailing remaster/version suffix (`" - ... remaster"` / `" - ... version"`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_text_norm.py`:
```python
from text_norm import normalize


def test_lowercases_and_strips():
    assert normalize("  Playboi CARTI ") == "playboi carti"


def test_collapses_internal_whitespace():
    assert normalize("Lil   Uzi\tVert") == "lil uzi vert"


def test_trims_remaster_suffix():
    assert normalize("Bohemian Rhapsody - 2011 Remaster") == "bohemian rhapsody"
    assert normalize("Song - Single Version") == "song"


def test_does_not_merge_distinct_titles():
    assert normalize("Location") != normalize("Locations")


def test_empty_safe():
    assert normalize("") == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_text_norm.py -v`
Expected: FAIL with "No module named 'text_norm'".

- [ ] **Step 3: Implement `text_norm.py`**

```python
"""Shared text normalization for dedup keys and artist matching.

Deliberately conservative: collapses case/whitespace and strips a trailing
remaster/version suffix, but never alters the core title/artist enough to merge
genuinely different songs.
"""

import re

_WS = re.compile(r"\s+")
# Trailing " - <something> remaster" or " - <something> version" (case-insensitive).
_SUFFIX = re.compile(r"\s*-\s*[^-]*\b(remaster(?:ed)?|version)\b.*$", re.IGNORECASE)


def normalize(text: str) -> str:
    """Lowercase, strip, collapse whitespace, and drop a trailing remaster/version tag."""
    if not text:
        return ""
    text = _SUFFIX.sub("", text)
    text = _WS.sub(" ", text).strip().lower()
    return text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_text_norm.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add text_norm.py tests/test_text_norm.py
git commit -m "feat(ingest): shared text normalization helper

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Genre bucket mapping (`ingest/genre_map.py`)

**Files:**
- Create: `ingest/__init__.py` (empty)
- Create: `ingest/genre_map.py`
- Test: `tests/test_genre_map.py`

**Interfaces:**
- Produces:
  - `BUCKETS: tuple[str, ...]`
  - `GENRE_TO_BUCKET: dict[str, str]`
  - `bucket_for(genres: list[str]) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_genre_map.py`:
```python
from ingest.genre_map import BUCKETS, bucket_for


def test_first_mapped_genre_wins():
    assert bucket_for(["rage", "atl hip hop"]) == "rage"


def test_skips_unmapped_then_matches():
    assert bucket_for(["canadian hip hop", "rap"]) == "hip-hop"


def test_subgenre_mapping():
    assert bucket_for(["pluggnb"]) == "plugg"
    assert bucket_for(["uk drill"]) == "drill"
    assert bucket_for(["contemporary r&b"]) == "r&b"


def test_other_when_nonempty_but_unmapped():
    assert bucket_for(["polka", "yodeling"]) == "other"


def test_unknown_when_empty():
    assert bucket_for([]) == "unknown"


def test_all_mapped_values_are_valid_buckets():
    from ingest.genre_map import GENRE_TO_BUCKET
    assert set(GENRE_TO_BUCKET.values()) <= set(BUCKETS)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_genre_map.py -v`
Expected: FAIL with "No module named 'ingest.genre_map'".

- [ ] **Step 3: Implement `ingest/genre_map.py`**

```python
"""Map Spotify/Last.fm micro-genres into a curated hybrid bucket set.

Buckets split hip-hop into meaningful subgenres (the bulk of the catalog) while
keeping broad buckets for everything else, so "across different genres" yields
real variety. The map is a starting set, extend it as new genres appear.
"""

BUCKETS: tuple[str, ...] = (
    "rage", "trap", "drill", "plugg", "boom-bap", "melodic-rap", "hip-hop",
    "pop", "r&b", "rock", "electronic", "indie", "country", "latin",
    "other", "unknown",
)

GENRE_TO_BUCKET: dict[str, str] = {
    # rage
    "rage": "rage",
    # plugg
    "plugg": "plugg", "pluggnb": "plugg",
    # drill
    "drill": "drill", "uk drill": "drill", "chicago drill": "drill",
    "brooklyn drill": "drill", "bronx drill": "drill",
    # melodic / emo / cloud
    "melodic rap": "melodic-rap", "emo rap": "melodic-rap",
    "cloud rap": "melodic-rap", "sad rap": "melodic-rap",
    # trap
    "trap": "trap", "dark trap": "trap", "atl trap": "trap",
    "atl hip hop": "trap", "southern hip hop": "trap", "gangster rap": "trap",
    # boom bap / old school
    "boom bap": "boom-bap", "old school hip hop": "boom-bap",
    "east coast hip hop": "boom-bap", "golden age hip hop": "boom-bap",
    "hardcore hip hop": "boom-bap", "conscious hip hop": "boom-bap",
    # generic rap
    "rap": "hip-hop", "hip hop": "hip-hop", "hip-hop": "hip-hop",
    "pop rap": "hip-hop", "underground hip hop": "hip-hop",
    "west coast hip hop": "hip-hop",
    # r&b
    "r&b": "r&b", "contemporary r&b": "r&b", "alternative r&b": "r&b",
    "neo soul": "r&b", "soul": "r&b",
    # pop
    "pop": "pop", "dance pop": "pop", "electropop": "pop", "art pop": "pop",
    "indie pop": "pop",
    # rock
    "rock": "rock", "alternative rock": "rock", "classic rock": "rock",
    "hard rock": "rock", "punk": "rock", "metal": "rock", "grunge": "rock",
    # electronic
    "edm": "electronic", "electronic": "electronic", "house": "electronic",
    "dubstep": "electronic", "techno": "electronic", "future bass": "electronic",
    "hyperpop": "electronic",
    # indie
    "indie": "indie", "indie rock": "indie", "bedroom pop": "indie",
    "indietronica": "indie",
    # country
    "country": "country", "country rap": "country", "contemporary country": "country",
    # latin
    "latin": "latin", "reggaeton": "latin", "latin trap": "latin",
    "trap latino": "latin", "rap latina": "latin",
}


def bucket_for(genres: list[str]) -> str:
    """Return the bucket of the first genre that maps; 'other'/'unknown' otherwise."""
    for genre in genres:
        bucket = GENRE_TO_BUCKET.get(genre.strip().lower())
        if bucket:
            return bucket
    return "other" if genres else "unknown"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_genre_map.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add ingest/__init__.py ingest/genre_map.py tests/test_genre_map.py
git commit -m "feat(ingest): curated micro-genre to bucket mapping

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Schema migration + source-aware plays (`db.py`)

**Files:**
- Modify: `db.py` (replace schema constants + `init_db`; modify `insert_play`; add `migrate`, `_iso_to_unix`)
- Test: `tests/test_db_migrate.py`

**Interfaces:**
- Produces:
  - `migrate(conn: sqlite3.Connection) -> None` — idempotent; ensures `plays` has `source`+`played_at_unix` (rebuilds the old-schema table, backfilling `source='spotify'` and `played_at_unix`), creates `artist_genres`, creates indexes.
  - `_iso_to_unix(iso: str) -> int` — ISO-8601 (may end in `Z`) → epoch seconds.
  - `insert_play(conn, *, track_id, name, artist, artist_id, artist_genre, album_art_url, popularity, played_at) -> bool` — UNCHANGED signature; now also sets `source='spotify'` and computes `played_at_unix`.
- Consumes: existing `connect()` context manager (unchanged).

**Note:** `db.py` currently defines `SCHEMA`, `connect`, `init_db`, `insert_play`, and other logger helpers. Keep `connect` and the existing genre-cache helpers (`get_cached_genres`, `cache_artist`, `play_count`) as-is. Replace the `SCHEMA` constant and `init_db`, and modify `insert_play` as shown.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_db_migrate.py`:
```python
import sqlite3
from datetime import datetime, timezone

import db


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    return c


def _cols(conn, table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def test_migrate_fresh_creates_v2_and_artist_genres():
    conn = _conn()
    db.migrate(conn)
    assert "source" in _cols(conn, "plays")
    assert "played_at_unix" in _cols(conn, "plays")
    assert _cols(conn, "artist_genres")  # table exists


def test_migrate_is_idempotent():
    conn = _conn()
    db.migrate(conn)
    db.migrate(conn)  # must not raise
    assert "source" in _cols(conn, "plays")


def test_migrate_rebuilds_old_schema_and_backfills():
    conn = _conn()
    # Build the OLD plays schema (no source / played_at_unix) and a row.
    conn.executescript(
        """
        CREATE TABLE plays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id TEXT NOT NULL, name TEXT NOT NULL, artist TEXT NOT NULL,
            artist_id TEXT, artist_genre TEXT, album_art_url TEXT,
            popularity INTEGER, played_at TEXT NOT NULL,
            UNIQUE(track_id, played_at)
        );
        """
    )
    conn.execute(
        "INSERT INTO plays (track_id,name,artist,played_at) VALUES (?,?,?,?)",
        ("t1", "Song", "Artist", "2026-06-23T10:00:00+00:00"),
    )
    db.migrate(conn)
    row = conn.execute("SELECT source, played_at_unix FROM plays").fetchone()
    expected = int(datetime(2026, 6, 23, 10, 0, 0, tzinfo=timezone.utc).timestamp())
    assert row["source"] == "spotify"
    assert row["played_at_unix"] == expected


def test_insert_play_sets_source_and_unix():
    conn = _conn()
    db.migrate(conn)
    db.insert_play(
        conn, track_id="t", name="n", artist="a", artist_id="ai",
        artist_genre="g", album_art_url="u", popularity=None,
        played_at="2026-06-23T10:00:00+00:00",
    )
    row = conn.execute("SELECT source, played_at_unix FROM plays").fetchone()
    expected = int(datetime(2026, 6, 23, 10, 0, 0, tzinfo=timezone.utc).timestamp())
    assert row["source"] == "spotify"
    assert row["played_at_unix"] == expected
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_db_migrate.py -v`
Expected: FAIL (`migrate` not defined / wrong columns).

- [ ] **Step 3: Edit `db.py`**

Replace the `SCHEMA = """..."""` constant with these constants:
```python
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
```

Add these imports near the top of `db.py` (alongside the existing imports):
```python
from datetime import datetime, timezone
```

Add the migration + helper:
```python
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
    conn.executescript(CREATE_INDEXES)
```

Replace `init_db` body with a call to migrate:
```python
def init_db() -> None:
    """Create/upgrade tables. Safe to run anytime."""
    with connect() as conn:
        migrate(conn)
```

Modify `insert_play` to set `source` and `played_at_unix`. Replace its INSERT with:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_db_migrate.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Run the existing suite to confirm no regressions**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all prior tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add db.py tests/test_db_migrate.py
git commit -m "feat(db): schema migration with source + played_at_unix

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Last.fm XML import (`ingest/lastfm_import.py` + db insert)

**Files:**
- Modify: `db.py` (add `insert_lastfm_play`, `play_count_by_source`)
- Create: `ingest/lastfm_import.py`
- Test: `tests/test_lastfm_import.py`

**Interfaces:**
- Consumes: `db.migrate`, `text_norm` (not directly here), `render.art.is_placeholder`.
- Produces:
  - `db.insert_lastfm_play(conn, *, track_id, name, artist, album_art_url, played_at, played_at_unix) -> bool` (`source='lastfm'`, INSERT OR IGNORE).
  - `db.play_count_by_source(conn) -> dict[str, int]`.
  - `ingest.lastfm_import.iter_scrobbles(xml_path) -> Iterator[dict]` yielding `{track_id, name, artist, album_art_url, played_at, played_at_unix}` (skips `nowplaying`/missing-`uts`/malformed).
  - `ingest.lastfm_import.import_scrobbles(conn, xml_path) -> tuple[int, int]` returning `(imported, skipped)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_lastfm_import.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_lastfm_import.py -v`
Expected: FAIL with "No module named 'ingest.lastfm_import'".

- [ ] **Step 3: Add db helpers to `db.py`**

```python
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
```

- [ ] **Step 4: Implement `ingest/lastfm_import.py`**

```python
"""Stream-parse a Last.fm scrobble export into the plays table."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
import xml.etree.ElementTree as ET

import db
from render.art import is_placeholder


def _text(elem, tag: str) -> str:
    child = elem.find(tag)
    return (child.text or "").strip() if child is not None else ""


def iter_scrobbles(xml_path) -> Iterator[dict]:
    """Yield one dict per real, dated scrobble. Skips now-playing/malformed."""
    for _, elem in ET.iterparse(str(xml_path), events=("end",)):
        if elem.tag != "track":
            continue
        try:
            if elem.get("nowplaying") == "true":
                continue
            date_el = elem.find("date")
            if date_el is None or not date_el.get("uts"):
                continue
            artist = _text(elem, "artist")
            name = _text(elem, "name")
            if not artist or not name:
                continue

            uts = int(date_el.get("uts"))
            track_mbid = _text(elem, "mbid")
            art_url = ""
            for img in elem.findall("image"):
                if img.get("size") == "extralarge":
                    art_url = (img.text or "").strip()
                    break
            if is_placeholder(art_url):
                art_url = ""

            yield {
                "track_id": track_mbid,
                "name": name,
                "artist": artist,
                "album_art_url": art_url,
                "played_at": datetime.fromtimestamp(uts, timezone.utc).isoformat(),
                "played_at_unix": uts,
            }
        finally:
            elem.clear()


def import_scrobbles(conn, xml_path) -> tuple[int, int]:
    """Import all scrobbles from xml_path. Returns (imported, skipped)."""
    # Count total <track> elements to derive skipped = total - imported_candidates.
    imported = 0
    candidates = 0
    for row in iter_scrobbles(xml_path):
        candidates += 1
        if db.insert_lastfm_play(conn, **row):
            imported += 1
    total_tracks = _count_tracks(xml_path)
    skipped = total_tracks - candidates
    return imported, skipped


def _count_tracks(xml_path) -> int:
    n = 0
    for _, elem in ET.iterparse(str(xml_path), events=("end",)):
        if elem.tag == "track":
            n += 1
        elem.clear()
    return n
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_lastfm_import.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add db.py ingest/lastfm_import.py tests/test_lastfm_import.py
git commit -m "feat(ingest): stream-import Last.fm scrobbles into plays

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Cross-source canonical dedup (`db.canonical_plays`)

**Files:**
- Modify: `db.py` (add `canonical_plays`)
- Test: `tests/test_canonical_plays.py`

**Interfaces:**
- Consumes: `text_norm.normalize`; `plays` rows (both sources).
- Produces: `db.canonical_plays(conn, window_seconds: int = 120) -> list[sqlite3.Row]` — cross-source duplicates (same normalized artist+title, different source, within window) collapse to one row, preferring the Spotify row. Same-source repeats preserved.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_canonical_plays.py`:
```python
import sqlite3
from datetime import datetime, timezone

import db


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db.migrate(c)
    return c


def _iso(u):
    return datetime.fromtimestamp(u, timezone.utc).isoformat()


def _spotify(conn, artist, name, unix):
    db.insert_play(
        conn, track_id=f"sp-{name}-{unix}", name=name, artist=artist,
        artist_id="x", artist_genre=None, album_art_url="", popularity=None,
        played_at=_iso(unix),
    )


def _lastfm(conn, artist, name, unix):
    db.insert_lastfm_play(
        conn, track_id="", name=name, artist=artist, album_art_url="",
        played_at=_iso(unix), played_at_unix=unix,
    )


def test_cross_source_pair_within_window_collapses_to_spotify():
    conn = _conn()
    _spotify(conn, "Carti", "Location", 1000)
    _lastfm(conn, "carti", "location", 1050)  # +50s, normalized-equal
    rows = db.canonical_plays(conn, window_seconds=120)
    assert len(rows) == 1
    assert rows[0]["source"] == "spotify"


def test_cross_source_pair_outside_window_kept_separate():
    conn = _conn()
    _spotify(conn, "Carti", "Location", 1000)
    _lastfm(conn, "Carti", "Location", 1000 + 200)
    rows = db.canonical_plays(conn, window_seconds=120)
    assert len(rows) == 2


def test_same_source_repeat_preserved():
    conn = _conn()
    _lastfm(conn, "Carti", "Location", 1000)
    _lastfm(conn, "Carti", "Location", 1000 + 3600)
    rows = db.canonical_plays(conn, window_seconds=120)
    assert len(rows) == 2


def test_different_songs_same_second_both_kept():
    conn = _conn()
    _spotify(conn, "Carti", "Location", 1000)
    _lastfm(conn, "Yeat", "Money", 1000)
    rows = db.canonical_plays(conn, window_seconds=120)
    assert len(rows) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_canonical_plays.py -v`
Expected: FAIL (`canonical_plays` not defined).

- [ ] **Step 3: Add `canonical_plays` to `db.py`**

Add `from text_norm import normalize` to the imports, then:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_canonical_plays.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_canonical_plays.py
git commit -m "feat(db): cross-source canonical play dedup

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Last.fm API client (`ingest/lastfm_client.py`)

**Files:**
- Create: `ingest/lastfm_client.py`
- Test: `tests/test_lastfm_client.py`

**Interfaces:**
- Produces: `get_top_tags(artist: str, api_key: str, fetch=None, min_weight: int = 10) -> list[str]` — calls `artist.getTopTags` (JSON), returns lowercased tag names with weight ≥ `min_weight`. `fetch` is an injectable `(url: str) -> str` returning response text (default = real `urllib`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_lastfm_client.py`:
```python
import json

from ingest.lastfm_client import get_top_tags

FAKE = json.dumps({
    "toptags": {"tag": [
        {"name": "Hip-Hop", "count": 100},
        {"name": "rage", "count": 40},
        {"name": "noise", "count": 2},
    ]}
})


def test_returns_lowercased_tags_above_threshold():
    captured = {}

    def fetch(url):
        captured["url"] = url
        return FAKE

    tags = get_top_tags("2hollis", "KEY", fetch=fetch, min_weight=10)
    assert tags == ["hip-hop", "rage"]  # 'noise' (2) dropped
    assert "artist.gettoptags" in captured["url"].lower()
    assert "api_key=KEY" in captured["url"]


def test_handles_missing_tags_gracefully():
    tags = get_top_tags("X", "KEY", fetch=lambda url: json.dumps({"toptags": {}}))
    assert tags == []


def test_handles_error_payload():
    err = json.dumps({"error": 6, "message": "not found"})
    tags = get_top_tags("X", "KEY", fetch=lambda url: err)
    assert tags == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_lastfm_client.py -v`
Expected: FAIL with "No module named 'ingest.lastfm_client'".

- [ ] **Step 3: Implement `ingest/lastfm_client.py`**

```python
"""Minimal Last.fm API client (stdlib only) for genre-tag fallback."""

import json
import urllib.parse
import urllib.request
from typing import Callable, Optional

_BASE = "https://ws.audioscrobbler.com/2.0/"


def _default_fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=15) as resp:
        return resp.read().decode("utf-8")


def get_top_tags(
    artist: str,
    api_key: str,
    fetch: Optional[Callable[[str], str]] = None,
    min_weight: int = 10,
) -> list[str]:
    """Return lowercased Last.fm top tags for an artist with weight >= min_weight."""
    params = urllib.parse.urlencode({
        "method": "artist.gettoptags",
        "artist": artist,
        "api_key": api_key,
        "format": "json",
    })
    url = f"{_BASE}?{params}"
    fetcher = fetch or _default_fetch
    try:
        payload = json.loads(fetcher(url))
    except Exception:
        return []
    if "error" in payload:
        return []
    tags = payload.get("toptags", {}).get("tag", [])
    return [
        t["name"].strip().lower()
        for t in tags
        if int(t.get("count", 0)) >= min_weight and t.get("name")
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_lastfm_client.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add ingest/lastfm_client.py tests/test_lastfm_client.py
git commit -m "feat(ingest): stdlib Last.fm getTopTags client

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Genre enrichment (`ingest/genres.py` + db helpers)

**Files:**
- Modify: `db.py` (add `distinct_artist_names`, `upsert_artist_genre`, `get_artist_genre`, `bucket_distribution`)
- Create: `ingest/genres.py`
- Test: `tests/test_genres.py`

**Interfaces:**
- Consumes: `text_norm.normalize`, `ingest.genre_map.bucket_for`, `ingest.lastfm_client.get_top_tags`, the db helpers below, and a Spotify client exposing `.search(q, type, limit)` (spotipy-compatible).
- Produces:
  - `db.distinct_artist_names(conn) -> list[str]`
  - `db.upsert_artist_genre(conn, *, artist_key, display_name, spotify_artist_id, raw_genres, lastfm_tags, primary_bucket, genre_source, fetched_at) -> None`
  - `db.get_artist_genre(conn, artist_key) -> Optional[sqlite3.Row]`
  - `db.bucket_distribution(conn) -> dict[str, int]`
  - `ingest.genres.resolve_artist_genre(name, spotify_client, lastfm_api_key, fetch=None) -> dict` with keys `display_name, spotify_artist_id, raw_genres (list), lastfm_tags (list), primary_bucket, genre_source`.
  - `ingest.genres.enrich_all(conn, spotify_client, lastfm_api_key, fetch=None, sleep=None) -> dict` summary `{spotify, lastfm, none, skipped}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_genres.py`:
```python
import sqlite3

import db
from ingest.genres import resolve_artist_genre, enrich_all


class FakeSpotify:
    """Minimal spotipy-compatible stub."""
    def __init__(self, mapping):
        self.mapping = mapping  # normalized name -> (id, [genres]) or None

    def search(self, q, type="artist", limit=1):
        hit = self.mapping.get(q.strip().lower())
        if not hit:
            return {"artists": {"items": []}}
        spotify_id, genres = hit
        return {"artists": {"items": [
            {"id": spotify_id, "name": q, "genres": genres}
        ]}}


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db.migrate(c)
    return c


def test_resolve_uses_spotify_when_genres_present():
    sp = FakeSpotify({"2hollis": ("id1", ["rage", "atl hip hop"])})
    out = resolve_artist_genre("2hollis", sp, "KEY")
    assert out["genre_source"] == "spotify"
    assert out["primary_bucket"] == "rage"
    assert out["spotify_artist_id"] == "id1"


def test_resolve_falls_back_to_lastfm_when_spotify_empty():
    sp = FakeSpotify({"someartist": ("id2", [])})  # match but no genres
    out = resolve_artist_genre(
        "SomeArtist", sp, "KEY",
        fetch=lambda url: '{"toptags": {"tag": [{"name": "drill", "count": 80}]}}',
    )
    assert out["genre_source"] == "lastfm"
    assert out["primary_bucket"] == "drill"


def test_resolve_unknown_when_nothing():
    sp = FakeSpotify({})  # no Spotify hit
    out = resolve_artist_genre(
        "Ghost", sp, "KEY", fetch=lambda url: '{"toptags": {}}'
    )
    assert out["genre_source"] == "none"
    assert out["primary_bucket"] == "unknown"


def test_resolve_rejects_name_mismatch():
    # Spotify returns a hit whose name doesn't match the query -> ignore it.
    class Wrong:
        def search(self, q, type="artist", limit=1):
            return {"artists": {"items": [
                {"id": "z", "name": "Totally Different", "genres": ["rock"]}
            ]}}
    out = resolve_artist_genre(
        "MyArtist", Wrong(), "KEY", fetch=lambda url: '{"toptags": {}}'
    )
    assert out["genre_source"] == "none"


def test_enrich_all_caches_and_is_resumable():
    conn = _conn()
    db.insert_lastfm_play(
        conn, track_id="", name="S", artist="2hollis",
        album_art_url="", played_at="2023-11-14T00:00:00+00:00",
        played_at_unix=1700000000,
    )
    sp = FakeSpotify({"2hollis": ("id1", ["rage"])})
    summary = enrich_all(conn, sp, "KEY", sleep=lambda s: None)
    assert summary["spotify"] == 1
    row = db.get_artist_genre(conn, "2hollis")
    assert row["primary_bucket"] == "rage"
    # Second run skips the already-cached artist.
    summary2 = enrich_all(conn, sp, "KEY", sleep=lambda s: None)
    assert summary2["skipped"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_genres.py -v`
Expected: FAIL with "No module named 'ingest.genres'".

- [ ] **Step 3: Add db helpers to `db.py`**

```python
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
```

- [ ] **Step 4: Implement `ingest/genres.py`**

```python
"""Resolve each artist's genre bucket: Spotify primary, Last.fm fallback."""

from datetime import datetime, timezone

import db
from text_norm import normalize
from ingest.genre_map import bucket_for
from ingest.lastfm_client import get_top_tags


def resolve_artist_genre(name, spotify_client, lastfm_api_key, fetch=None) -> dict:
    """Resolve one artist to a genre bucket. Spotify first, then Last.fm, then none."""
    result = {
        "display_name": name,
        "spotify_artist_id": "",
        "raw_genres": [],
        "lastfm_tags": [],
        "primary_bucket": "unknown",
        "genre_source": "none",
    }

    # 1. Spotify primary (accept top hit only if the name matches).
    try:
        items = spotify_client.search(q=name, type="artist", limit=1)["artists"]["items"]
    except Exception:
        items = []
    if items and normalize(items[0].get("name", "")) == normalize(name):
        result["spotify_artist_id"] = items[0].get("id", "")
        genres = items[0].get("genres", []) or []
        result["raw_genres"] = genres
        if genres:
            result["primary_bucket"] = bucket_for(genres)
            result["genre_source"] = "spotify"
            return result

    # 2. Last.fm fallback.
    tags = get_top_tags(name, lastfm_api_key, fetch=fetch)
    if tags:
        result["lastfm_tags"] = tags
        result["primary_bucket"] = bucket_for(tags)
        result["genre_source"] = "lastfm"
        return result

    # 3. Nothing.
    return result


def enrich_all(conn, spotify_client, lastfm_api_key, fetch=None, sleep=None) -> dict:
    """Enrich every not-yet-cached artist. Returns a per-source summary."""
    summary = {"spotify": 0, "lastfm": 0, "none": 0, "skipped": 0}
    for name in db.distinct_artist_names(conn):
        key = normalize(name)
        if db.get_artist_genre(conn, key) is not None:
            summary["skipped"] += 1
            continue

        resolved = resolve_artist_genre(name, spotify_client, lastfm_api_key, fetch=fetch)
        db.upsert_artist_genre(
            conn,
            artist_key=key,
            display_name=resolved["display_name"],
            spotify_artist_id=resolved["spotify_artist_id"],
            raw_genres=",".join(resolved["raw_genres"]),
            lastfm_tags=",".join(resolved["lastfm_tags"]),
            primary_bucket=resolved["primary_bucket"],
            genre_source=resolved["genre_source"],
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
        summary[resolved["genre_source"]] += 1
        if resolved["genre_source"] == "lastfm" and sleep is not None:
            sleep(0.25)  # be polite to the Last.fm API
    return summary
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_genres.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
git add db.py ingest/genres.py tests/test_genres.py
git commit -m "feat(ingest): artist genre enrichment with Spotify+Last.fm

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: Config + CLI orchestration (`config.py`, `ingest/enrich_cli.py`)

**Files:**
- Modify: `config.py` (add Last.fm keys + export-path resolver)
- Create: `ingest/enrich_cli.py`
- Test: `tests/test_enrich_cli.py`

**Interfaces:**
- Consumes: `db.migrate`, `ingest.lastfm_import.import_scrobbles`, `ingest.genres.enrich_all`, `db.canonical_plays`, `db.play_count_by_source`, `db.bucket_distribution`, `config`.
- Produces:
  - `config.LASTFM_API_KEY`, `config.LASTFM_SHARED_SECRET`, `config.resolve_export_path() -> Path` (env override, else newest `data/scrobbles-*.xml`).
  - `ingest.enrich_cli.run_ingest(conn, xml_path, spotify_client, lastfm_api_key, fetch=None, sleep=None) -> dict` (testable orchestration returning a summary dict).
  - `ingest.enrich_cli.main() -> None` (wires real Spotify client + config).

- [ ] **Step 1: Write the failing test**

Create `tests/test_enrich_cli.py`:
```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_enrich_cli.py -v`
Expected: FAIL with "No module named 'ingest.enrich_cli'".

- [ ] **Step 3: Extend `config.py`**

Add near the other env reads:
```python
LASTFM_API_KEY = os.getenv("LAST_FM_API_KEY")
LASTFM_SHARED_SECRET = os.getenv("LAST_FM_SHARED_SECRET")
LASTFM_EXPORT_PATH = os.getenv("LASTFM_EXPORT_PATH")
```

Add this resolver function:
```python
def resolve_export_path() -> Path:
    """Path to the Last.fm export: env override, else newest data/scrobbles-*.xml."""
    if LASTFM_EXPORT_PATH:
        return Path(LASTFM_EXPORT_PATH)
    matches = sorted(DATA_DIR.glob("scrobbles-*.xml"))
    if not matches:
        raise SystemExit(
            "No Last.fm export found. Put it at data/scrobbles-*.xml or set "
            "LASTFM_EXPORT_PATH in .env."
        )
    return matches[-1]
```

- [ ] **Step 4: Implement `ingest/enrich_cli.py`**

```python
"""CLI: migrate + import Last.fm history + enrich genres, then print a summary.

Run: python -m ingest.enrich_cli
"""

import config
import db
from ingest.lastfm_import import import_scrobbles
from ingest.genres import enrich_all
from spotify_client import get_client


def run_ingest(conn, xml_path, spotify_client, lastfm_api_key, fetch=None, sleep=None) -> dict:
    """Migrate, import, and enrich against an open connection. Returns a summary."""
    db.migrate(conn)
    imported, skipped = import_scrobbles(conn, xml_path)
    enriched = enrich_all(conn, spotify_client, lastfm_api_key, fetch=fetch, sleep=sleep)
    return {
        "imported": imported,
        "skipped": skipped,
        "by_source": db.play_count_by_source(conn),
        "enriched": enriched,
        "buckets": db.bucket_distribution(conn),
        "canonical_plays": len(db.canonical_plays(conn)),
    }


def main() -> None:
    config.assert_credentials()
    xml_path = config.resolve_export_path()
    if not config.LASTFM_API_KEY:
        print("Warning: LAST_FM_API_KEY not set — genre fallback disabled.")

    import time
    with db.connect() as conn:
        summary = run_ingest(
            conn, xml_path, get_client(), config.LASTFM_API_KEY,
            sleep=time.sleep,
        )

    print(f"Imported {summary['imported']} scrobbles "
          f"(skipped {summary['skipped']}).")
    print(f"Plays by source: {summary['by_source']}")
    print(f"Artists enriched: {summary['enriched']}")
    print(f"Canonical (deduped) plays: {summary['canonical_plays']}")
    print("Bucket distribution:")
    for bucket, count in summary["buckets"].items():
        print(f"  {bucket:<12} {count}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_enrich_cli.py -v`
Expected: PASS (1 passed).

- [ ] **Step 6: Run the full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all tests PASS.

- [ ] **Step 7: Manual gate (real data, requires network + Spotify auth)**

Run: `.\.venv\Scripts\python.exe -m ingest.enrich_cli`
Expected: prints imported counts, plays-by-source, artists-enriched-by-source, canonical play count, and a bucket distribution. Eyeball for sanity (e.g. rap buckets dominate, counts are plausible). This is the human checkpoint.

- [ ] **Step 8: Commit**

```bash
git add config.py ingest/enrich_cli.py tests/test_enrich_cli.py
git commit -m "feat(ingest): enrich CLI orchestration + export-path config

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- §4 modules: `text_norm` (T1), `genre_map` (T2), `lastfm_import` (T4), `lastfm_client` (T6), `genres` (T7), `enrich_cli` (T8); `db.py`/`config.py` extensions across T3–T8. ✓
- §5 schema: `source`+`played_at_unix`, rebuild-migration + backfill, `UNIQUE(source,artist,track_id,name,played_at)`, `artist_genres` keyed by normalized name → T3. ✓
- §6 import + within-source dedup → T4; cross-source `canonical_plays` (±120s, prefer Spotify) → T5; normalization → T1. ✓
- §7 buckets + `bucket_for` first-match → T2; Spotify→Last.fm→none resumable flow → T7. ✓
- §8 error handling: malformed/nowplaying skipped (T4), placeholder art blanked (T4), Spotify/Last.fm errors caught (T6/T7), idempotent re-runs (T3/T4/T7), migration safe (T3). ✓
- §9 testing: every listed test area has a task (T1–T8) + manual gate (T8 Step 7). ✓
- §10 CLI summary → T8. ✓
- §11 no new runtime deps (stdlib urllib/xml, existing spotipy) → T6/T4. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases" — every code step is complete. ✓

**Type consistency:**
- `normalize` (T1) used in T2-adjacent? No — used in T5 `canonical_plays`, T7 `resolve_artist_genre`/`enrich_all`. Consistent signature. ✓
- `bucket_for` (T2) consumed in T7. ✓
- `db.insert_lastfm_play`/`play_count_by_source` (T4), `canonical_plays` (T5), `distinct_artist_names`/`upsert_artist_genre`/`get_artist_genre`/`bucket_distribution` (T7) — all consumed in T5/T7/T8 with matching signatures. ✓
- `get_top_tags(artist, api_key, fetch, min_weight)` (T6) consumed by `resolve_artist_genre` via `get_top_tags(name, lastfm_api_key, fetch=fetch)` (T7). ✓
- `resolve_artist_genre`/`enrich_all` (T7) consumed by `run_ingest` (T8). ✓
- `config.resolve_export_path`/`LASTFM_API_KEY` (T8) used in `main` (T8). ✓

No gaps found.
