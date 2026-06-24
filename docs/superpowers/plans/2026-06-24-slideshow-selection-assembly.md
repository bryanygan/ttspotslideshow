# Slideshow Selection + Assembly Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the enriched listening DB into a dated folder of TikTok slides — pick recent, genre-varied, not-recently-featured tracks and render them through the Phase 2 card/collage engine.

**Architecture:** A `slideshow/` package (window → selector → art_resolve → builder → cli) plus `db.py` query/persistence helpers. The selector is a pure function; networked units (iTunes lookup, art download) use injectable fetch so everything tests offline.

**Tech Stack:** Python 3.12, stdlib (`sqlite3`, `urllib`, `json`, `datetime`), the existing `render` package, pytest. No new runtime dependencies.

## Global Constraints

- Python 3.12; use the existing `.venv`. Run python as `.\.venv\Scripts\python.exe`.
- **No new runtime dependencies** (stdlib `urllib`/`json` for iTunes; existing `render`).
- Window auto-widen steps: `(2, 4, 7, 14, 30)` days. Target **16**, floor **12**. Only whole 4-card slides are rendered.
- Selection composite score: `base = 0.6*norm(play_count) + 0.4*norm(recency)`, `score = base * novelty`. Weights `0.6/0.4`, novelty recovery `14` days — module-level constants.
- `novelty`: `1.0` if not in `featured` OR `days <= 0` (featured today, NOT suppressed → same-day re-run is deterministic); else `min(1.0, days / 14)` where `days = (run_date - last_featured_date).days`.
- `featured_tracks` is **date-based**: `track_key TEXT PK, last_featured_date TEXT ('YYYY-MM-DD'), times_featured INTEGER`.
- `track_key` = `normalize(artist) + '\t' + normalize(title)` (the literal TAB char).
- Album art: iTunes Search API `artworkUrl100` → rewrite `100x100`→`600x600`; fallback to the track's stored `album_art_url`; then `''`.
- Output: `output/slides/<YYYY-MM-DD>/slide_<n>.png` (1080×1920). Art caches in `data/album_art/`.
- Deterministic: every sort has an explicit tiebreak.
- All commit messages end with: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

### Task 1: Featured-tracks persistence (`db.py`)

**Files:**
- Modify: `db.py` (add `CREATE_FEATURED`, call it in `migrate`; add `record_featured`, `featured_history`)
- Test: `tests/test_featured.py`

**Interfaces:**
- Consumes: existing `migrate(conn)`, `connect()`.
- Produces:
  - `migrate` also creates `featured_tracks`.
  - `db.featured_history(conn) -> dict[str, str]` → `{track_key: last_featured_date}`.
  - `db.record_featured(conn, track_keys: list[str], run_date: str) -> None` — upsert each key (`last_featured_date=run_date`, increment `times_featured`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_featured.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_featured.py -v`
Expected: FAIL (`featured_tracks` missing / `record_featured` undefined).

- [ ] **Step 3: Edit `db.py`**

Add a constant alongside the other `CREATE_*` constants:
```python
CREATE_FEATURED = """
CREATE TABLE IF NOT EXISTS featured_tracks (
    track_key          TEXT PRIMARY KEY,
    last_featured_date TEXT NOT NULL,
    times_featured     INTEGER NOT NULL
);
"""
```

In `migrate`, after the `conn.execute(CREATE_ARTIST_GENRES)` line, add:
```python
    conn.execute(CREATE_FEATURED)
```

Add these functions:
```python
def featured_history(conn: sqlite3.Connection) -> dict:
    """Return {track_key: last_featured_date} for every previously featured track."""
    rows = conn.execute(
        "SELECT track_key, last_featured_date FROM featured_tracks"
    ).fetchall()
    return {r["track_key"]: r["last_featured_date"] for r in rows}


def record_featured(conn: sqlite3.Connection, track_keys, run_date: str) -> None:
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_featured.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Run full suite (migration touches shared code)**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all prior tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add db.py tests/test_featured.py
git commit -m "feat(db): featured_tracks table + record/history helpers

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Window candidate aggregation (`db.window_track_candidates`)

**Files:**
- Modify: `db.py` (add `window_track_candidates`)
- Test: `tests/test_window_candidates.py`

**Interfaces:**
- Consumes: `canonical_plays(conn)`, `artist_genres`, `text_norm.normalize`.
- Produces: `db.window_track_candidates(conn, start_unix: int) -> list[dict]`, each dict:
  `track_key, play_count, track_id, title, artist, album_art_url, last_played_unix, primary_bucket`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_window_candidates.py`:
```python
import sqlite3

import db


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db.migrate(c)
    return c


def _iso(u):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(u, timezone.utc).isoformat()


def _lastfm(conn, artist, name, unix, art=""):
    db.insert_lastfm_play(
        conn, track_id="", name=name, artist=artist, album_art_url=art,
        played_at=_iso(unix), played_at_unix=unix,
    )


def test_aggregates_counts_and_window_filter():
    conn = _conn()
    _lastfm(conn, "Carti", "Location", 1000)
    _lastfm(conn, "Carti", "Location", 1500)   # same track, in window -> count 2
    _lastfm(conn, "Yeat", "Money", 500)        # before window -> excluded
    cands = db.window_track_candidates(conn, start_unix=900)
    by_key = {c["track_key"]: c for c in cands}
    assert set(by_key) == {"carti\tlocation"}
    assert by_key["carti\tlocation"]["play_count"] == 2
    assert by_key["carti\tlocation"]["last_played_unix"] == 1500


def test_joins_primary_bucket_and_defaults_unknown():
    conn = _conn()
    db.upsert_artist_genre(
        conn, artist_key="carti", display_name="Carti", spotify_artist_id="",
        raw_genres="rage", lastfm_tags="", primary_bucket="rage",
        genre_source="spotify", fetched_at="2026-06-24T00:00:00Z",
    )
    _lastfm(conn, "Carti", "Location", 1000)
    _lastfm(conn, "NoGenre", "Track", 1000)
    cands = {c["track_key"]: c for c in db.window_track_candidates(conn, 0)}
    assert cands["carti\tlocation"]["primary_bucket"] == "rage"
    assert cands["nogenre\ttrack"]["primary_bucket"] == "unknown"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_window_candidates.py -v`
Expected: FAIL (`window_track_candidates` undefined).

- [ ] **Step 3: Add `window_track_candidates` to `db.py`**

```python
def window_track_candidates(conn: sqlite3.Connection, start_unix: int) -> list:
    """Aggregate canonical plays since start_unix into unique candidate tracks."""
    genres = {
        r["artist_key"]: r["primary_bucket"]
        for r in conn.execute(
            "SELECT artist_key, primary_bucket FROM artist_genres"
        ).fetchall()
    }

    groups: dict = {}
    for r in canonical_plays(conn):
        unix = r["played_at_unix"]
        if unix is None or unix < start_unix:
            continue
        artist_key = normalize(r["artist"])
        track_key = artist_key + "\t" + normalize(r["name"])
        g = groups.get(track_key)
        if g is None:
            groups[track_key] = g = {
                "track_key": track_key,
                "play_count": 0,
                "track_id": r["track_id"],
                "title": r["name"],
                "artist": r["artist"],
                "album_art_url": r["album_art_url"],
                "last_played_unix": unix,
                "primary_bucket": genres.get(artist_key, "unknown"),
            }
        g["play_count"] += 1
        if unix >= g["last_played_unix"]:
            # Refresh representative fields from the most recent play.
            g["last_played_unix"] = unix
            g["track_id"] = r["track_id"]
            g["title"] = r["name"]
            g["artist"] = r["artist"]
            g["album_art_url"] = r["album_art_url"]
    return list(groups.values())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_window_candidates.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_window_candidates.py
git commit -m "feat(db): window_track_candidates aggregation

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Window resolution with auto-widen (`slideshow/window.py`)

**Files:**
- Create: `slideshow/__init__.py` (empty)
- Create: `slideshow/window.py`
- Test: `tests/test_resolve_window.py`

**Interfaces:**
- Consumes: `db.window_track_candidates`.
- Produces: `resolve_window(conn, target=16, floor=12, steps=(2,4,7,14,30), now_unix=None) -> tuple[list, int]` returning `(candidates, days_used)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_resolve_window.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_resolve_window.py -v`
Expected: FAIL with "No module named 'slideshow.window'".

- [ ] **Step 3: Implement `slideshow/window.py`**

```python
"""Resolve the candidate track pool from a recent window, widening if thin."""

import time

import db

DAY_SECONDS = 86400


def resolve_window(conn, target=16, floor=12, steps=(2, 4, 7, 14, 30), now_unix=None):
    """Return (candidates, days_used). Try each window; stop at the first with
    >= target unique tracks, else return the largest (last step)."""
    if now_unix is None:
        now_unix = int(time.time())

    candidates: list = []
    days_used = steps[-1]
    for days in steps:
        start = now_unix - days * DAY_SECONDS
        candidates = db.window_track_candidates(conn, start)
        days_used = days
        if len(candidates) >= target:
            break
    return candidates, days_used
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_resolve_window.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add slideshow/__init__.py slideshow/window.py tests/test_resolve_window.py
git commit -m "feat(slideshow): window resolution with auto-widen

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Genre round-robin selection (`slideshow/selector.py`)

**Files:**
- Create: `slideshow/selector.py`
- Test: `tests/test_selector.py`

**Interfaces:**
- Consumes: candidate dicts (from Task 2), a `featured` map `{track_key: 'YYYY-MM-DD'}`.
- Produces: `select_tracks(candidates, featured, run_date, target=16, floor=12) -> list[dict]` — ordered selection (slide order). Module constants `WEIGHT_PLAY=0.6`, `WEIGHT_RECENCY=0.4`, `NOVELTY_DAYS=14`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_selector.py`:
```python
from slideshow.selector import select_tracks


def _cand(track_key, bucket, play_count, last_unix, title=None):
    return {
        "track_key": track_key,
        "primary_bucket": bucket,
        "play_count": play_count,
        "last_played_unix": last_unix,
        "title": title or track_key,
        "artist": "a",
        "track_id": "",
        "album_art_url": "",
    }


def test_round_robin_interleaves_genres():
    cands = [
        _cand("r1", "rage", 10, 100), _cand("r2", "rage", 9, 100),
        _cand("t1", "trap", 8, 100), _cand("p1", "pop", 7, 100),
    ]
    out = select_tracks(cands, {}, "2026-06-24", target=4, floor=4)
    # First pass takes one from each bucket before a second rage track.
    assert [c["primary_bucket"] for c in out][:3] == ["rage", "trap", "pop"]
    assert out[-1]["track_key"] == "r2"  # second rage track comes last


def test_recently_featured_is_suppressed_vs_unfeatured_peer():
    cands = [
        _cand("hot", "rage", 10, 100),   # higher plays but featured yesterday
        _cand("fresh", "rage", 8, 100),  # fewer plays, never featured
    ]
    featured = {"hot": "2026-06-23"}     # 1 day before run_date
    out = select_tracks(cands, featured, "2026-06-24", target=1, floor=1)
    assert out[0]["track_key"] == "fresh"


def test_featured_today_not_suppressed_same_day_determinism():
    cands = [_cand("hot", "rage", 10, 100), _cand("fresh", "rage", 8, 100)]
    featured = {"hot": "2026-06-24"}     # featured TODAY -> novelty 1.0
    out = select_tracks(cands, featured, "2026-06-24", target=1, floor=1)
    assert out[0]["track_key"] == "hot"  # plays win; today's feature isn't penalized


def test_recency_lifts_newer_play():
    cands = [
        _cand("old", "rage", 10, 100),
        _cand("new", "rage", 10, 999),   # equal plays, more recent
    ]
    out = select_tracks(cands, {}, "2026-06-24", target=1, floor=1)
    assert out[0]["track_key"] == "new"


def test_count_resolution_to_multiple_of_four():
    cands = [_cand(f"k{i}", "rage" if i % 2 else "trap", 5, 100 + i) for i in range(14)]
    out = select_tracks(cands, {}, "2026-06-24", target=16, floor=12)
    assert len(out) == 12  # 14 available -> largest multiple of 4 >= floor


def test_deterministic_repeat():
    cands = [_cand(f"k{i}", "rage", 5, 100 + i) for i in range(6)]
    a = select_tracks(cands, {}, "2026-06-24", target=16, floor=12)
    b = select_tracks(cands, {}, "2026-06-24", target=16, floor=12)
    assert [c["track_key"] for c in a] == [c["track_key"] for c in b]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_selector.py -v`
Expected: FAIL with "No module named 'slideshow.selector'".

- [ ] **Step 3: Implement `slideshow/selector.py`**

```python
"""Genre round-robin selection blending play count, recency, and novelty."""

from datetime import date

WEIGHT_PLAY = 0.6
WEIGHT_RECENCY = 0.4
NOVELTY_DAYS = 14


def _novelty(track_key, featured, run_date):
    last = featured.get(track_key)
    if last is None:
        return 1.0
    days = (date.fromisoformat(run_date) - date.fromisoformat(last)).days
    if days <= 0:           # featured today (or future) -> not suppressed
        return 1.0
    return min(1.0, days / NOVELTY_DAYS)


def select_tracks(candidates, featured, run_date, target=16, floor=12):
    """Return an ordered selection (slide order) via genre round-robin."""
    if not candidates:
        return []

    max_play = max(c["play_count"] for c in candidates) or 1
    lasts = [c["last_played_unix"] for c in candidates]
    min_last, max_last = min(lasts), max(lasts)
    span = (max_last - min_last) or 1

    scored = []
    for c in candidates:
        norm_play = c["play_count"] / max_play
        norm_rec = 1.0 if max_last == min_last else (c["last_played_unix"] - min_last) / span
        base = WEIGHT_PLAY * norm_play + WEIGHT_RECENCY * norm_rec
        score = base * _novelty(c["track_key"], featured, run_date)
        scored.append((score, c))

    buckets: dict = {}
    for score, c in scored:
        buckets.setdefault(c["primary_bucket"], []).append((score, c))
    for items in buckets.values():
        items.sort(key=lambda sc: (-sc[0], -sc[1]["last_played_unix"], sc[1]["title"]))

    bucket_order = sorted(
        buckets.keys(),
        key=lambda k: (-sum(c["play_count"] for _, c in buckets[k]), k),
    )

    picked = []
    indices = {k: 0 for k in bucket_order}
    progressed = True
    while progressed and len(picked) < target:
        progressed = False
        for k in bucket_order:
            i = indices[k]
            if i < len(buckets[k]):
                picked.append(buckets[k][i][1])
                indices[k] += 1
                progressed = True
                if len(picked) >= target:
                    break

    n = len(picked)
    if n >= target:
        final = target
    elif n >= 4:
        final = (n // 4) * 4    # 12 for 12-15, 8 for 8-11, 4 for 4-7
    else:
        final = n               # < 4: can't fill a slide; caller handles
    return picked[:final]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_selector.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add slideshow/selector.py tests/test_selector.py
git commit -m "feat(slideshow): genre round-robin selection with freshness blend

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Album-art resolution (`slideshow/art_resolve.py`)

**Files:**
- Create: `slideshow/art_resolve.py`
- Test: `tests/test_art_resolve.py`

**Interfaces:**
- Consumes: `text_norm.normalize`.
- Produces: `resolve_art_url(track, fetch=None, cache=None) -> str` — iTunes hi-res URL, else the track's `album_art_url`, else `''`. `fetch(url)->str` injectable; `cache` optional dict memoizing per `track_key`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_art_resolve.py`:
```python
import json

from slideshow.art_resolve import resolve_art_url

ITUNES_HIT = json.dumps({
    "results": [{"artworkUrl100": "https://is1.example/abc/100x100bb.jpg"}]
})


def _track(artist="2hollis", title="destroy me", art="https://lastfm/300.jpg"):
    return {"artist": artist, "title": title, "album_art_url": art}


def test_itunes_hit_rewritten_to_600():
    out = resolve_art_url(_track(), fetch=lambda url: ITUNES_HIT)
    assert out == "https://is1.example/abc/600x600bb.jpg"


def test_no_results_falls_back_to_lastfm():
    out = resolve_art_url(_track(), fetch=lambda url: json.dumps({"results": []}))
    assert out == "https://lastfm/300.jpg"


def test_error_falls_back_then_empty():
    def boom(url):
        raise OSError("network down")
    assert resolve_art_url(_track(), fetch=boom) == "https://lastfm/300.jpg"
    assert resolve_art_url(_track(art=""), fetch=boom) == ""


def test_cache_avoids_second_fetch():
    calls = []

    def fetch(url):
        calls.append(url)
        return ITUNES_HIT

    cache = {}
    resolve_art_url(_track(), fetch=fetch, cache=cache)
    resolve_art_url(_track(), fetch=fetch, cache=cache)
    assert len(calls) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_art_resolve.py -v`
Expected: FAIL with "No module named 'slideshow.art_resolve'".

- [ ] **Step 3: Implement `slideshow/art_resolve.py`**

```python
"""Resolve hi-res album art via the iTunes Search API, with Last.fm fallback."""

import json
import urllib.parse
import urllib.request
from typing import Callable, Optional

from text_norm import normalize

_ITUNES = "https://itunes.apple.com/search"


def _default_fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=15) as resp:
        return resp.read().decode("utf-8")


def resolve_art_url(track, fetch: Optional[Callable[[str], str]] = None,
                    cache: Optional[dict] = None) -> str:
    """Best album-art URL for a track: iTunes 600x600, else stored Last.fm, else ''."""
    key = normalize(track["artist"]) + "\t" + normalize(track["title"])
    if cache is not None and key in cache:
        return cache[key]

    fetcher = fetch or _default_fetch
    result = track.get("album_art_url") or ""
    params = urllib.parse.urlencode({
        "term": f"{track['artist']} {track['title']}",
        "entity": "song",
        "limit": 1,
    })
    try:
        payload = json.loads(fetcher(f"{_ITUNES}?{params}"))
        results = payload.get("results", [])
        artwork = results[0].get("artworkUrl100", "") if results else ""
        if artwork:
            result = artwork.replace("100x100", "600x600")
    except Exception:
        pass  # keep the Last.fm fallback already in `result`

    if cache is not None:
        cache[key] = result
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_art_resolve.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add slideshow/art_resolve.py tests/test_art_resolve.py
git commit -m "feat(slideshow): iTunes hi-res art resolution with fallback

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Build pipeline (`slideshow/builder.py`)

**Files:**
- Create: `slideshow/builder.py`
- Test: `tests/test_builder.py`

**Interfaces:**
- Consumes: `slideshow.window.resolve_window`, `slideshow.selector.select_tracks`, `slideshow.art_resolve.resolve_art_url`, `db.featured_history`, `db.record_featured`, `render.art.load_art`, `render.card.render_card`, `render.collage.collage`.
- Produces: `build_slideshow(conn, out_root, target=16, floor=12, now_unix=None, today=None, fetch=None, cache_dir=None) -> dict` summary `{date, days_used, track_count, slide_count, genre_spread, out_dir}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_builder.py` (offline — monkeypatches the art downloader):
```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_builder.py -v`
Expected: FAIL with "No module named 'slideshow.builder'".

- [ ] **Step 3: Implement `slideshow/builder.py`**

```python
"""Orchestrate selection -> art -> render -> collage -> dated slide folder."""

from datetime import date
from pathlib import Path

import db
from slideshow.window import resolve_window
from slideshow.selector import select_tracks
from slideshow.art_resolve import resolve_art_url
from render.art import load_art
from render.card import render_card
from render.collage import collage


def build_slideshow(conn, out_root, target=16, floor=12, now_unix=None,
                    today=None, fetch=None, cache_dir=None) -> dict:
    """Build the dated slide set. Returns a run summary."""
    run_date = today or date.today().isoformat()
    cache_dir = Path(cache_dir) if cache_dir else (Path("data") / "album_art")
    out_dir = Path(out_root) / run_date

    candidates, days_used = resolve_window(conn, target, floor, now_unix=now_unix)
    featured = db.featured_history(conn)
    tracks = select_tracks(candidates, featured, run_date, target, floor)

    # Only whole 4-card slides are rendered.
    rendered = tracks[: (len(tracks) // 4) * 4]

    summary = {
        "date": run_date,
        "days_used": days_used,
        "track_count": len(rendered),
        "slide_count": 0,
        "genre_spread": {},
        "out_dir": str(out_dir),
    }
    if not rendered:
        return summary

    art_cache: dict = {}
    cards = []
    for track in rendered:
        url = resolve_art_url(track, fetch=fetch, cache=art_cache)
        art_path = load_art(url, cache_dir)
        cards.append(render_card(track, art_path=art_path))

    out_dir.mkdir(parents=True, exist_ok=True)
    slide_count = 0
    for i in range(0, len(cards), 4):
        slide_count += 1
        collage(cards[i:i + 4]).save(out_dir / f"slide_{slide_count}.png")

    db.record_featured(conn, [t["track_key"] for t in rendered], run_date)

    spread: dict = {}
    for track in rendered:
        spread[track["primary_bucket"]] = spread.get(track["primary_bucket"], 0) + 1
    summary["slide_count"] = slide_count
    summary["genre_spread"] = spread
    return summary
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_builder.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add slideshow/builder.py tests/test_builder.py
git commit -m "feat(slideshow): build pipeline to dated slide folder

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: CLI (`slideshow/cli.py`)

**Files:**
- Create: `slideshow/cli.py`
- Test: `tests/test_slideshow_cli.py`

**Interfaces:**
- Consumes: `db.connect`, `slideshow.builder.build_slideshow`.
- Produces: `format_summary(summary) -> str` (pure, testable) and `main() -> None` (wires real connection + `output/slides`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_slideshow_cli.py`:
```python
from slideshow.cli import format_summary


def test_format_summary_full():
    s = {
        "date": "2026-06-24", "days_used": 2, "track_count": 16,
        "slide_count": 4, "genre_spread": {"rage": 6, "trap": 5, "pop": 5},
        "out_dir": "output/slides/2026-06-24",
    }
    text = format_summary(s)
    assert "4 slide" in text
    assert "output/slides/2026-06-24" in text
    assert "rage" in text


def test_format_summary_empty():
    s = {"date": "2026-06-24", "days_used": 30, "track_count": 0,
         "slide_count": 0, "genre_spread": {}, "out_dir": "x"}
    text = format_summary(s)
    assert "No" in text or "nothing" in text.lower()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_slideshow_cli.py -v`
Expected: FAIL with "No module named 'slideshow.cli'".

- [ ] **Step 3: Implement `slideshow/cli.py`**

```python
"""CLI: build the bi-daily slideshow into output/slides/<date>/.

Run: python -m slideshow.cli
"""

from pathlib import Path

import db
from slideshow.builder import build_slideshow


def format_summary(summary: dict) -> str:
    """Render a run summary as human-readable text."""
    if summary["track_count"] == 0:
        return (f"No tracks available to render (empty window or DB) — "
                f"nothing written. (widened to {summary['days_used']} days)")
    lines = [
        f"Wrote {summary['slide_count']} slide(s) -> {summary['out_dir']}",
        f"Window: last {summary['days_used']} days; "
        f"{summary['track_count']} tracks",
        "Genre spread: " + ", ".join(
            f"{b}={n}" for b, n in summary["genre_spread"].items()
        ),
    ]
    return "\n".join(lines)


def main() -> None:
    out_root = Path("output") / "slides"
    with db.connect() as conn:
        summary = build_slideshow(conn, out_root)
    print(format_summary(summary))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_slideshow_cli.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run the full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all tests PASS.

- [ ] **Step 6: Manual gate (real data, needs the enriched DB + network)**

Run: `.\.venv\Scripts\python.exe -m slideshow.cli`
Expected: prints the summary and writes `output/slides/<today>/slide_*.png`. Open the slides and review selection quality + visual polish. This is the human checkpoint.

- [ ] **Step 7: Commit**

```bash
git add slideshow/cli.py tests/test_slideshow_cli.py
git commit -m "feat(slideshow): bi-daily CLI entry point

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- §4 modules `window`/`selector`/`art_resolve`/`builder`/`cli` → Tasks 3/4/5/6/7; `db` additions → Tasks 1/2. ✓
- §5 window aggregation + auto-widen → Tasks 2/3. ✓
- §6 featured table + composite score (play/recency/novelty) + round-robin + count resolution + same-day novelty → Tasks 1/4. ✓
- §7 iTunes→Last.fm→'' art chain + memoization → Task 5. ✓
- §8 build pipeline + dated output + record_featured + CLI summary → Tasks 6/7. ✓
- §9 error handling: thin window (T3 widen + T4 count), no plays (T6 empty path), art fallback (T5), re-run determinism (T4 same-day novelty) → covered. ✓
- §10 testing: selector/window/art_resolve/builder/featured → Tasks 1–7. ✓
- §11 no new runtime deps (stdlib + render) → Tasks 5/6. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases" — every code step is complete. ✓

**Type consistency:**
- `featured_history -> dict[track_key, date]` / `record_featured(conn, keys, run_date)` (T1) consumed in selector tests + builder (T4/T6). ✓
- `window_track_candidates(conn, start_unix)` (T2) consumed by `resolve_window` (T3). ✓
- `resolve_window(...) -> (candidates, days_used)` (T3) consumed by builder (T6). ✓
- `select_tracks(candidates, featured, run_date, target, floor)` (T4) consumed by builder (T6) with matching arg order. ✓
- `resolve_art_url(track, fetch, cache)` (T5) consumed by builder (T6). ✓
- candidate dict keys (`track_key, play_count, last_played_unix, primary_bucket, title, artist, track_id, album_art_url`) consistent across T2/T4/T6. ✓
- `build_slideshow(...) -> summary dict` (T6) consumed by `format_summary` (T7) with matching keys. ✓

No gaps found.
