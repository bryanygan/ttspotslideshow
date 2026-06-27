# Global Popularity Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore a meaningful global-popularity number per track (Last.fm primary, ListenBrainz fallback) so the dashboard's "Underrated" sort works again after Spotify removed `track.popularity`.

**Architecture:** A new per-track cache table `track_popularity` (mirroring `artist_genres`) stores a log-normalized 0–100 score. A `ingest/popularity.py` module fetches raw listener counts (Last.fm `track.getInfo`, falling back to ListenBrainz metadata-lookup → popularity API) and normalizes them. A resumable `ingest/enrich_popularity.py` CLI fills the cache and is wired into `run_bidaily.py`. The dashboard drops its dead Spotify popularity call and reads the cache instead.

**Tech Stack:** Python 3 (stdlib `http.server`, `urllib`, `sqlite3`, `math`, `pytest`). Network is injected via a `fetch` callable for offline tests (the repo's `webutil.fetch_text` pattern). No frontend changes.

## Global Constraints

- Popularity score is an integer **0–100**, log-normalized from raw listener counts; reference ceiling `POPULARITY_CEIL = 5_000_000`.
- Cache table `track_popularity` is keyed by `track_key = normalize(artist) + "\t" + normalize(title)` (tab-separated), matching `text_norm.normalize` and `db.window_track_candidates`.
- `source` is always one of `'lastfm' | 'listenbrainz' | 'none'`.
- **Unmatched (`'none'`) tracks read as neutral 50**, never as obscure. The 50 default is applied at the dashboard read path, not stored.
- Network is always injectable via a `fetch`/`sleep` callable; tests never hit the real network.
- Run Python tests with the repo venv: `.venv\Scripts\python.exe -m pytest <path> -v` (PowerShell) — the system Python lacks `spotipy`.
- Enrichment is **resumable**: by default only fetch track_keys with no cache row; `--refresh` re-fetches all.
- Popularity failures must never block slideshow generation in the bi-daily run.

---

### Task 1: `track_popularity` schema + DB helpers

**Files:**
- Modify: `db.py` (add `CREATE_TRACK_POPULARITY` constant, call it in `migrate`, add three helpers near `upsert_artist_genre`/`get_artist_genre` ~line 327–365)
- Test: `tests/test_track_popularity_db.py` (create)

**Interfaces:**
- Consumes: `db.migrate`, `db.canonical_plays`, `text_norm.normalize`.
- Produces:
  - `db.upsert_track_popularity(conn, *, track_key, listeners, popularity, source, fetched_at)` → None
  - `db.get_track_popularity(conn, track_key)` → `sqlite3.Row | None`
  - `db.track_keys_missing_popularity(conn)` → `list[str]` (canonical track_keys with no `track_popularity` row)

- [ ] **Step 1: Write the failing test**

Create `tests/test_track_popularity_db.py`:

```python
import sqlite3

import db


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db.migrate(c)
    return c


def test_upsert_and_get_roundtrip():
    conn = _conn()
    db.upsert_track_popularity(
        conn, track_key="artist a\tsong a", listeners=1234,
        popularity=42, source="lastfm", fetched_at="2026-06-27T00:00:00Z",
    )
    row = db.get_track_popularity(conn, "artist a\tsong a")
    assert row is not None
    assert row["listeners"] == 1234
    assert row["popularity"] == 42
    assert row["source"] == "lastfm"


def test_upsert_replaces_existing():
    conn = _conn()
    for pop in (10, 55):
        db.upsert_track_popularity(
            conn, track_key="k", listeners=pop * 10, popularity=pop,
            source="lastfm", fetched_at="t",
        )
    row = db.get_track_popularity(conn, "k")
    assert row["popularity"] == 55  # second write wins, no duplicate row


def test_get_missing_returns_none():
    conn = _conn()
    assert db.get_track_popularity(conn, "nope") is None


def test_track_keys_missing_popularity(monkeypatch):
    conn = _conn()
    # Two canonical tracks; cache one, expect the other reported missing.
    monkeypatch.setattr(
        db, "canonical_plays",
        lambda c: [
            {"artist": "Artist A", "name": "Song A"},
            {"artist": "Artist B", "name": "Song B"},
        ],
    )
    db.upsert_track_popularity(
        conn, track_key="artist a\tsong a", listeners=1, popularity=1,
        source="lastfm", fetched_at="t",
    )
    missing = db.track_keys_missing_popularity(conn)
    assert "artist b\tsong b" in missing
    assert "artist a\tsong a" not in missing
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_track_popularity_db.py -v`
Expected: FAILS with `AttributeError: module 'db' has no attribute 'upsert_track_popularity'`.

- [ ] **Step 3: Add the schema constant + migrate call**

In `db.py`, after `CREATE_ARTIST_GENRES` (ends ~line 48), add:

```python
CREATE_TRACK_POPULARITY = """
CREATE TABLE IF NOT EXISTS track_popularity (
    track_key   TEXT PRIMARY KEY,
    listeners   INTEGER,
    popularity  INTEGER,
    source      TEXT NOT NULL,
    fetched_at  TEXT
);
"""
```

In `migrate`, after the `conn.execute(CREATE_ARTIST_GENRES)` line (~line 105), add:

```python
    conn.execute(CREATE_TRACK_POPULARITY)
```

- [ ] **Step 4: Add the helpers**

In `db.py`, after `get_artist_genre` (~line 365), add:

```python
def upsert_track_popularity(
    conn: sqlite3.Connection,
    *,
    track_key: str,
    listeners: Optional[int],
    popularity: Optional[int],
    source: str,
    fetched_at: str,
) -> None:
    """Insert/replace one track's resolved popularity record."""
    conn.execute(
        """
        INSERT INTO track_popularity
            (track_key, listeners, popularity, source, fetched_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(track_key) DO UPDATE SET
            listeners=excluded.listeners,
            popularity=excluded.popularity,
            source=excluded.source,
            fetched_at=excluded.fetched_at
        """,
        (track_key, listeners, popularity, source, fetched_at),
    )


def get_track_popularity(conn: sqlite3.Connection, track_key: str):
    """Return the cached track_popularity row, or None."""
    return conn.execute(
        "SELECT * FROM track_popularity WHERE track_key = ?", (track_key,)
    ).fetchone()


def track_keys_missing_popularity(conn: sqlite3.Connection) -> list:
    """Canonical track_keys that have no cached popularity row yet."""
    cached = {
        r["track_key"]
        for r in conn.execute("SELECT track_key FROM track_popularity").fetchall()
    }
    seen = []
    out = []
    for r in canonical_plays(conn):
        track_key = normalize(r["artist"]) + "\t" + normalize(r["name"])
        if track_key in seen:
            continue
        seen.append(track_key)
        if track_key not in cached:
            out.append(track_key)
    return out
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_track_popularity_db.py -v`
Expected: all 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add db.py tests/test_track_popularity_db.py
git commit -m "feat: add track_popularity cache table and DB helpers"
```

---

### Task 2: Listener normalization

**Files:**
- Create: `ingest/popularity.py`
- Test: `tests/test_popularity_normalize.py` (create)

**Interfaces:**
- Produces: `ingest.popularity.normalize_listeners(listeners: int | None) -> int` (0–100); module constant `POPULARITY_CEIL = 5_000_000`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_popularity_normalize.py`:

```python
from ingest.popularity import normalize_listeners


def test_zero_and_none_are_zero():
    assert normalize_listeners(0) == 0
    assert normalize_listeners(None) == 0
    assert normalize_listeners(-5) == 0


def test_monotonic_and_bounded():
    small = normalize_listeners(300)
    mid = normalize_listeners(50_000)
    big = normalize_listeners(5_000_000)
    assert 0 < small < mid < big <= 100
    assert big == 100  # at the ceiling


def test_huge_clamps_to_100():
    assert normalize_listeners(50_000_000) == 100
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_popularity_normalize.py -v`
Expected: FAILS with `ModuleNotFoundError: No module named 'ingest.popularity'`.

- [ ] **Step 3: Implement the module skeleton + normalizer**

Create `ingest/popularity.py`:

```python
"""Resolve a track's global popularity: Last.fm primary, ListenBrainz fallback.

Raw listener counts are log-normalized into a 0-100 score so the dashboard's
"underrated" ratio (play_count / popularity) is meaningful again after Spotify
removed track.popularity.
"""

import json
import math
import urllib.parse
from datetime import datetime, timezone
from typing import Callable, Optional

from webutil import fetch_text

POPULARITY_CEIL = 5_000_000  # ~ a megahit's Last.fm listener count -> score 100

_LASTFM = "https://ws.audioscrobbler.com/2.0/"
_LB_LOOKUP = "https://api.listenbrainz.org/1/metadata/lookup/"
_LB_POPULARITY = "https://api.listenbrainz.org/1/popularity/recording"


def normalize_listeners(listeners: Optional[int]) -> int:
    """Log-scale a raw listener count into a 0-100 popularity score."""
    if not listeners or listeners < 0:
        return 0
    score = 100 * math.log10(listeners + 1) / math.log10(POPULARITY_CEIL + 1)
    return max(0, min(100, round(score)))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_popularity_normalize.py -v`
Expected: all 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add ingest/popularity.py tests/test_popularity_normalize.py
git commit -m "feat: add log-scale listener normalization"
```

---

### Task 3: Last.fm + ListenBrainz fetchers and `resolve_popularity`

**Files:**
- Modify: `ingest/popularity.py` (add three functions after `normalize_listeners`)
- Test: `tests/test_popularity_fetch.py` (create)

> **Pre-flight (do once before Step 3, not a code change):** the ListenBrainz
> endpoint shapes below are from memory. Verify them live before wiring:
> ```bash
> curl -s "https://api.listenbrainz.org/1/metadata/lookup/?artist_name=Radiohead&recording_name=Creep"
> curl -s -X POST "https://api.listenbrainz.org/1/popularity/recording" \
>   -H "Content-Type: application/json" \
>   -d '{"recording_mbids":["<mbid-from-above>"]}'
> ```
> Confirm the JSON field names used in Step 3 (`recording_mbid`,
> `total_user_count`). If they differ, adjust the parsing in
> `fetch_listenbrainz_listeners` to match the live response and update the test
> fixtures accordingly. The Last.fm shape (`track.listeners`) is stable.

**Interfaces:**
- Consumes: `normalize_listeners`, `webutil.fetch_text`.
- Produces:
  - `fetch_lastfm_listeners(artist, title, api_key, fetch=None) -> int | None`
  - `fetch_listenbrainz_listeners(artist, title, token, fetch=None) -> int | None`
  - `resolve_popularity(artist, title, *, lastfm_api_key, listenbrainz_token, fetch=None) -> dict` returning `{"listeners": int|None, "popularity": int|None, "source": str}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_popularity_fetch.py`:

```python
import json

from ingest import popularity
from ingest.popularity import (
    fetch_lastfm_listeners,
    fetch_listenbrainz_listeners,
    resolve_popularity,
)


def _lastfm_ok(listeners):
    return json.dumps({"track": {"name": "X", "listeners": str(listeners)}})


def test_lastfm_parses_listeners():
    out = fetch_lastfm_listeners("A", "B", "KEY", fetch=lambda url: _lastfm_ok(900))
    assert out == 900


def test_lastfm_error_payload_returns_none():
    out = fetch_lastfm_listeners(
        "A", "B", "KEY",
        fetch=lambda url: json.dumps({"error": 6, "message": "not found"}),
    )
    assert out is None


def test_lastfm_network_error_returns_none():
    def boom(url):
        raise RuntimeError("timeout")
    assert fetch_lastfm_listeners("A", "B", "KEY", fetch=boom) is None


def test_listenbrainz_two_hop(monkeypatch):
    def fake_fetch(url):
        if "metadata/lookup" in url:
            return json.dumps({"recording_mbid": "mbid-1"})
        raise AssertionError("popularity hop should use the POST helper")

    # The popularity POST is done via an internal helper we monkeypatch.
    monkeypatch.setattr(
        popularity, "_lb_popularity_for_mbid",
        lambda mbid, token, fetch=None: 4321 if mbid == "mbid-1" else None,
    )
    out = fetch_listenbrainz_listeners("A", "B", "TOKEN", fetch=fake_fetch)
    assert out == 4321


def test_listenbrainz_no_mbid_returns_none():
    out = fetch_listenbrainz_listeners(
        "A", "B", "TOKEN",
        fetch=lambda url: json.dumps({}),  # no recording_mbid
    )
    assert out is None


def test_resolve_prefers_lastfm(monkeypatch):
    monkeypatch.setattr(popularity, "fetch_lastfm_listeners", lambda *a, **k: 1000)
    monkeypatch.setattr(popularity, "fetch_listenbrainz_listeners", lambda *a, **k: 9)
    out = resolve_popularity("A", "B", lastfm_api_key="K", listenbrainz_token="T")
    assert out["source"] == "lastfm"
    assert out["listeners"] == 1000
    assert out["popularity"] == popularity.normalize_listeners(1000)


def test_resolve_falls_back_to_listenbrainz(monkeypatch):
    monkeypatch.setattr(popularity, "fetch_lastfm_listeners", lambda *a, **k: None)
    monkeypatch.setattr(popularity, "fetch_listenbrainz_listeners", lambda *a, **k: 500)
    out = resolve_popularity("A", "B", lastfm_api_key="K", listenbrainz_token="T")
    assert out["source"] == "listenbrainz"
    assert out["listeners"] == 500


def test_resolve_none_when_both_miss(monkeypatch):
    monkeypatch.setattr(popularity, "fetch_lastfm_listeners", lambda *a, **k: None)
    monkeypatch.setattr(popularity, "fetch_listenbrainz_listeners", lambda *a, **k: None)
    out = resolve_popularity("A", "B", lastfm_api_key="K", listenbrainz_token="T")
    assert out["source"] == "none"
    assert out["listeners"] is None
    assert out["popularity"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_popularity_fetch.py -v`
Expected: FAILS with `ImportError: cannot import name 'fetch_lastfm_listeners'`.

- [ ] **Step 3: Implement the fetchers + resolver**

In `ingest/popularity.py`, after `normalize_listeners`, add:

```python
def fetch_lastfm_listeners(artist, title, api_key, fetch=None) -> Optional[int]:
    """Last.fm track.getInfo -> global listener count, or None on miss/error."""
    if not api_key:
        return None
    params = urllib.parse.urlencode({
        "method": "track.getInfo",
        "artist": artist,
        "track": title,
        "api_key": api_key,
        "format": "json",
    })
    fetcher = fetch or fetch_text
    try:
        payload = json.loads(fetcher(f"{_LASTFM}?{params}"))
    except Exception:
        return None
    if not isinstance(payload, dict) or "error" in payload:
        return None
    track = payload.get("track") or {}
    try:
        return int(track.get("listeners"))
    except (TypeError, ValueError):
        return None


def _lb_popularity_for_mbid(mbid, token, fetch=None) -> Optional[int]:
    """POST a recording MBID to the ListenBrainz popularity API -> user count."""
    import urllib.request

    body = json.dumps({"recording_mbids": [mbid]}).encode("utf-8")
    req = urllib.request.Request(
        _LB_POPULARITY,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Token {token}",
        },
        method="POST",
    )
    try:
        if fetch is not None:
            payload = json.loads(fetch(req))
        else:
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    # API returns a list of {recording_mbid, total_listen_count, total_user_count}
    rows = payload if isinstance(payload, list) else payload.get("payload", [])
    for row in rows or []:
        if row.get("recording_mbid") == mbid:
            try:
                return int(row.get("total_user_count"))
            except (TypeError, ValueError):
                return None
    return None


def fetch_listenbrainz_listeners(artist, title, token, fetch=None) -> Optional[int]:
    """ListenBrainz fallback: artist+title -> MBID -> global user count."""
    if not token:
        return None
    params = urllib.parse.urlencode({
        "artist_name": artist,
        "recording_name": title,
    })
    fetcher = fetch or fetch_text
    try:
        payload = json.loads(fetcher(f"{_LB_LOOKUP}?{params}"))
    except Exception:
        return None
    mbid = (payload or {}).get("recording_mbid")
    if not mbid:
        return None
    return _lb_popularity_for_mbid(mbid, token, fetch=fetch)


def resolve_popularity(artist, title, *, lastfm_api_key, listenbrainz_token,
                       fetch=None) -> dict:
    """Try Last.fm, then ListenBrainz. Returns {listeners, popularity, source}."""
    listeners = fetch_lastfm_listeners(artist, title, lastfm_api_key, fetch=fetch)
    source = "lastfm"
    if listeners is None:
        listeners = fetch_listenbrainz_listeners(
            artist, title, listenbrainz_token, fetch=fetch
        )
        source = "listenbrainz"
    if listeners is None:
        return {"listeners": None, "popularity": None, "source": "none"}
    return {
        "listeners": listeners,
        "popularity": normalize_listeners(listeners),
        "source": source,
    }
```

> Note on the `fetch` seam: GET fetchers take a URL string (`fetch(url)`); the
> ListenBrainz POST helper passes a `urllib.request.Request` to `fetch` when
> injected (the test monkeypatches `_lb_popularity_for_mbid` directly, so it
> never exercises the real POST). This keeps GET tests simple while leaving the
> POST path verifiable by the pre-flight curl.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_popularity_fetch.py -v`
Expected: all 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add ingest/popularity.py tests/test_popularity_fetch.py
git commit -m "feat: add Last.fm + ListenBrainz popularity fetchers"
```

---

### Task 4: `enrich_all_popularity` + resumable CLI

**Files:**
- Create: `ingest/enrich_popularity.py`
- Modify: `config.py` (add `LISTENBRAINZ_TOKEN`)
- Test: `tests/test_enrich_popularity.py` (create)

**Interfaces:**
- Consumes: `db.track_keys_missing_popularity`, `db.upsert_track_popularity`, `db.canonical_plays`, `ingest.popularity.resolve_popularity`, `text_norm.normalize`.
- Produces: `ingest.enrich_popularity.enrich_all_popularity(conn, *, lastfm_api_key, listenbrainz_token, fetch=None, sleep=None, progress=None, refresh=False) -> dict` returning `{"lastfm": int, "listenbrainz": int, "none": int, "processed": int}`.

- [ ] **Step 1: Add the config var**

In `config.py`, after the Last.fm credentials block (~line 38), add:

```python
# --- ListenBrainz (popularity fallback) ---
LISTENBRAINZ_TOKEN = os.getenv("LISTENBRAINZ_TOKEN")
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_enrich_popularity.py`:

```python
import sqlite3

import db
from ingest.enrich_popularity import enrich_all_popularity


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db.migrate(c)
    return c


def _seed(monkeypatch, tracks):
    """Make canonical_plays return the given (artist, name) rows."""
    monkeypatch.setattr(
        db, "canonical_plays",
        lambda c, *a, **k: [{"artist": ar, "name": nm} for ar, nm in tracks],
    )


def test_enriches_missing_and_counts(monkeypatch):
    conn = _conn()
    _seed(monkeypatch, [("Artist A", "Song A"), ("Artist B", "Song B")])

    def fake_resolve(artist, title, **k):
        if artist == "Artist A":
            return {"listeners": 1000, "popularity": 50, "source": "lastfm"}
        return {"listeners": None, "popularity": None, "source": "none"}

    monkeypatch.setattr(
        "ingest.enrich_popularity.resolve_popularity", fake_resolve
    )
    summary = enrich_all_popularity(
        conn, lastfm_api_key="K", listenbrainz_token="T", sleep=lambda s: None,
    )
    assert summary["processed"] == 2
    assert summary["lastfm"] == 1
    assert summary["none"] == 1
    assert db.get_track_popularity(conn, "artist a\tsong a")["popularity"] == 50
    # 'none' rows are still cached (so we don't refetch them every run).
    assert db.get_track_popularity(conn, "artist b\tsong b")["source"] == "none"


def test_resumable_skips_cached(monkeypatch):
    conn = _conn()
    _seed(monkeypatch, [("Artist A", "Song A")])
    db.upsert_track_popularity(
        conn, track_key="artist a\tsong a", listeners=1, popularity=1,
        source="lastfm", fetched_at="t",
    )
    calls = []
    monkeypatch.setattr(
        "ingest.enrich_popularity.resolve_popularity",
        lambda *a, **k: calls.append(1) or {"listeners": 1, "popularity": 1, "source": "lastfm"},
    )
    summary = enrich_all_popularity(
        conn, lastfm_api_key="K", listenbrainz_token="T", sleep=lambda s: None,
    )
    assert summary["processed"] == 0  # already cached, nothing fetched
    assert calls == []


def test_refresh_reprocesses_all(monkeypatch):
    conn = _conn()
    _seed(monkeypatch, [("Artist A", "Song A")])
    db.upsert_track_popularity(
        conn, track_key="artist a\tsong a", listeners=1, popularity=1,
        source="lastfm", fetched_at="t",
    )
    monkeypatch.setattr(
        "ingest.enrich_popularity.resolve_popularity",
        lambda *a, **k: {"listeners": 9999, "popularity": 88, "source": "lastfm"},
    )
    summary = enrich_all_popularity(
        conn, lastfm_api_key="K", listenbrainz_token="T", sleep=lambda s: None,
        refresh=True,
    )
    assert summary["processed"] == 1
    assert db.get_track_popularity(conn, "artist a\tsong a")["popularity"] == 88
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enrich_popularity.py -v`
Expected: FAILS with `ModuleNotFoundError: No module named 'ingest.enrich_popularity'`.

- [ ] **Step 4: Implement the module + CLI**

Create `ingest/enrich_popularity.py`:

```python
"""CLI: fill the track_popularity cache (Last.fm primary, ListenBrainz fallback).

Resumable — by default only fetches tracks with no cached row. Use --refresh to
re-fetch all. Run: python -m ingest.enrich_popularity
"""

import logging
from datetime import datetime, timezone

import config
import db
from text_norm import normalize
from ingest.popularity import resolve_popularity
from logsetup import setup_logging

LOG = logging.getLogger("enrich_popularity")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _all_canonical_track_keys(conn) -> list:
    """Distinct canonical track_keys with their display artist/title."""
    seen = set()
    out = []
    for r in db.canonical_plays(conn):
        artist, title = r["artist"], r["name"]
        track_key = normalize(artist) + "\t" + normalize(title)
        if track_key in seen:
            continue
        seen.add(track_key)
        out.append((track_key, artist, title))
    return out


def enrich_all_popularity(conn, *, lastfm_api_key, listenbrainz_token,
                          fetch=None, sleep=None, progress=None,
                          refresh=False) -> dict:
    """Resolve + cache popularity for tracks. Resumable unless refresh=True."""
    targets = _all_canonical_track_keys(conn)
    if not refresh:
        missing = set(db.track_keys_missing_popularity(conn))
        targets = [t for t in targets if t[0] in missing]

    summary = {"lastfm": 0, "listenbrainz": 0, "none": 0, "processed": 0}
    total = len(targets)
    for i, (track_key, artist, title) in enumerate(targets):
        res = resolve_popularity(
            artist, title,
            lastfm_api_key=lastfm_api_key,
            listenbrainz_token=listenbrainz_token,
            fetch=fetch,
        )
        db.upsert_track_popularity(
            conn, track_key=track_key, listeners=res["listeners"],
            popularity=res["popularity"], source=res["source"],
            fetched_at=_now_iso(),
        )
        summary[res["source"]] += 1
        summary["processed"] += 1
        if progress:
            progress(i + 1, total)
        if sleep:
            sleep(0.25)  # be polite between network calls
    conn.commit()
    return summary


def build_parser():
    import argparse

    parser = argparse.ArgumentParser(
        description="Fill the track_popularity cache (Last.fm + ListenBrainz)."
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="re-fetch popularity for every track, not just uncached ones.",
    )
    return parser


def main() -> None:
    import time

    args = build_parser().parse_args()
    setup_logging("enrich_popularity")
    if not config.LASTFM_API_KEY:
        LOG.warning("LAST_FM_API_KEY not set — Last.fm popularity unavailable.")
    if not config.LISTENBRAINZ_TOKEN:
        LOG.warning("LISTENBRAINZ_TOKEN not set — ListenBrainz fallback disabled.")

    def progress(done, total):
        if done % 25 == 0 or done == total:
            LOG.info("  popularity: %d/%d", done, total)

    LOG.info("Enriching track popularity (%s, resumable)...",
             "refresh-all" if args.refresh else "missing-only")
    with db.connect() as conn:
        summary = enrich_all_popularity(
            conn,
            lastfm_api_key=config.LASTFM_API_KEY,
            listenbrainz_token=config.LISTENBRAINZ_TOKEN,
            sleep=time.sleep, progress=progress, refresh=args.refresh,
        )
    LOG.info("Done. processed=%d lastfm=%d listenbrainz=%d none=%d",
             summary["processed"], summary["lastfm"],
             summary["listenbrainz"], summary["none"])


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_enrich_popularity.py -v`
Expected: all 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add ingest/enrich_popularity.py config.py tests/test_enrich_popularity.py
git commit -m "feat: add resumable popularity enrichment CLI + LISTENBRAINZ_TOKEN config"
```

---

### Task 5: Dashboard reads the cache (drop the dead Spotify call)

**Files:**
- Modify: `dashboard_server.py:137-183` (replace the Spotify popularity block + decoration loop)
- Test: `tests/test_dashboard_server.py` (extend)

**Interfaces:**
- Consumes: `db.get_track_popularity` (Task 1).
- Produces: `/api/candidates` decorates each candidate with `popularity` from the `track_popularity` cache, defaulting to **50** when absent or `source='none'`/NULL.

- [ ] **Step 1: Write the failing test**

In `tests/test_dashboard_server.py`, add a test that a cached popularity is surfaced (and the unmatched default stays 50). Append:

```python
def test_get_candidates_uses_cached_popularity(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.migrate(conn)
    db.insert_lastfm_play(
        conn, track_id="track1", name="Song A", artist="Artist A",
        album_art_url="http://art", played_at="2026-06-25T00:00:00Z",
        played_at_unix=1782350000,
    )
    db.upsert_track_popularity(
        conn, track_key="artist a\tsong a", listeners=900, popularity=33,
        source="lastfm", fetched_at="t",
    )
    from contextlib import contextmanager
    @contextmanager
    def fake_connect():
        yield conn
    monkeypatch.setattr(db, "connect", fake_connect)

    handler = DummyHandler()
    parsed = urlparse("http://localhost:8000/api/candidates?days=7")
    handler.handle_get_candidates(parsed)

    res = json.loads(handler.wfile.content.decode("utf-8"))
    assert res["candidates"][0]["popularity"] == 33
```

> The existing `test_get_candidates_endpoint` already asserts the unmatched
> default is 50; keep it as the no-cache case.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_dashboard_server.py -v`
Expected: `test_get_candidates_uses_cached_popularity` FAILS (popularity comes back 50 — the old code ignores the cache).

- [ ] **Step 3: Replace the Spotify block + decoration**

In `dashboard_server.py`, replace the whole block from line 137 (`# Collect track IDs...`) through the decoration loop ending at line 193 (the override `if` block) — i.e. replace lines 137–193 — with:

```python
        # Popularity now comes from the track_popularity cache (Last.fm +
        # ListenBrainz), filled by ingest.enrich_popularity. Spotify removed
        # track.popularity (Feb 2026), so there's no live call here anymore.
        pop_cache = {}
        try:
            with db.connect() as conn:
                for c in candidates:
                    row = db.get_track_popularity(conn, c["track_key"])
                    if row is not None and row["popularity"] is not None:
                        pop_cache[c["track_key"]] = row["popularity"]
        except Exception as pop_err:
            print(f"Failed to read cached popularity: {pop_err}", file=sys.stderr)

        # Decorate candidates with popularity, last_featured, and overrides details
        for c in candidates:
            # Unmatched/uncached tracks read as neutral 50, never as obscure.
            c["popularity"] = pop_cache.get(c["track_key"], 50)
            c["last_featured"] = featured.get(c["track_key"], None)

            rf = recent_featured.get(c["track_key"])
            c["recently_featured"] = rf is not None
            c["times_featured"] = rf["times_featured"] if rf else 0

            # Check for manual cover art overrides
            override_path = find_override_art(c["artist"], c["title"])
            if override_path:
                c["album_art_url"] = f"/api/overrides/{override_path.name}"
```

> This removes the `uncached_candidates` / `track_ids_to_fetch` / `sp.tracks()`
> logic entirely. `window_track_candidates` may still set a `popularity` key from
> the play row; the loop above unconditionally overwrites it from the cache (or
> 50), so that stale value never reaches the client.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_dashboard_server.py -v`
Expected: both `test_get_candidates_endpoint` (default 50) and `test_get_candidates_uses_cached_popularity` (33) PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard_server.py tests/test_dashboard_server.py
git commit -m "feat: dashboard reads popularity from cache, drop dead Spotify call"
```

---

### Task 6: Wire popularity enrichment into the bi-daily run

**Files:**
- Modify: `run_bidaily.py` (`run_pipeline` signature + a new step; `main` argparse)
- Test: `tests/test_run_bidaily_popularity.py` (create)

**Interfaces:**
- Consumes: `ingest.enrich_popularity.enrich_all_popularity`, `config.LASTFM_API_KEY`, `config.LISTENBRAINZ_TOKEN`.
- Produces: `run_pipeline(..., skip_popularity: bool = False)` runs popularity enrichment after ingest and before the slideshow build, guarded so failure only logs a warning.

- [ ] **Step 1: Write the failing test**

Create `tests/test_run_bidaily_popularity.py`:

```python
import run_bidaily


def test_pipeline_runs_popularity_enrichment(monkeypatch):
    calls = {"enriched": False, "built": False}

    monkeypatch.setattr(run_bidaily.db, "init_db", lambda: None)

    # Stub a connect() context manager.
    from contextlib import contextmanager
    @contextmanager
    def fake_connect():
        yield object()
    monkeypatch.setattr(run_bidaily.db, "connect", fake_connect)

    monkeypatch.setattr(
        run_bidaily, "enrich_all_popularity",
        lambda *a, **k: calls.__setitem__("enriched", True) or {
            "processed": 0, "lastfm": 0, "listenbrainz": 0, "none": 0},
    )
    monkeypatch.setattr(
        run_bidaily, "build_slideshow",
        lambda conn, out_path: calls.__setitem__("built", True) or {"slide_count": 0},
    )
    monkeypatch.setattr(run_bidaily, "format_summary", lambda s: "ok")

    run_bidaily.run_pipeline(skip_spotify=True, skip_lastfm=True)
    assert calls["enriched"] is True
    assert calls["built"] is True


def test_skip_popularity_flag(monkeypatch):
    calls = {"enriched": False}
    monkeypatch.setattr(run_bidaily.db, "init_db", lambda: None)
    from contextlib import contextmanager
    @contextmanager
    def fake_connect():
        yield object()
    monkeypatch.setattr(run_bidaily.db, "connect", fake_connect)
    monkeypatch.setattr(
        run_bidaily, "enrich_all_popularity",
        lambda *a, **k: calls.__setitem__("enriched", True),
    )
    monkeypatch.setattr(run_bidaily, "build_slideshow", lambda conn, out_path: {"slide_count": 0})
    monkeypatch.setattr(run_bidaily, "format_summary", lambda s: "ok")

    run_bidaily.run_pipeline(skip_spotify=True, skip_lastfm=True, skip_popularity=True)
    assert calls["enriched"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_run_bidaily_popularity.py -v`
Expected: FAILS — `run_bidaily` has no `enrich_all_popularity` attribute / `run_pipeline` lacks `skip_popularity`.

- [ ] **Step 3: Add the import + pipeline step + flag**

In `run_bidaily.py`, add to the imports (after `from ingest.lastfm_import import import_recent_from_api`, ~line 19):

```python
from ingest.enrich_popularity import enrich_all_popularity
```

Change the `run_pipeline` signature (~line 27) to add the flag:

```python
def run_pipeline(
    skip_spotify: bool = False,
    skip_lastfm: bool = False,
    skip_popularity: bool = False,
    out_root: str = "output/slides",
) -> None:
```

Insert a new step between the Last.fm ingest block and `# 4. Build slideshow`
(before line 70):

```python
    # 3.5 Enrich global popularity (Last.fm primary, ListenBrainz fallback).
    if not skip_popularity:
        try:
            LOG.info("Enriching track popularity...")
            with db.connect() as conn:
                pop_summary = enrich_all_popularity(
                    conn,
                    lastfm_api_key=config.LASTFM_API_KEY,
                    listenbrainz_token=config.LISTENBRAINZ_TOKEN,
                )
            LOG.info(
                "Popularity: processed=%d lastfm=%d listenbrainz=%d none=%d",
                pop_summary["processed"], pop_summary["lastfm"],
                pop_summary["listenbrainz"], pop_summary["none"],
            )
        except Exception as e:
            LOG.warning("Popularity enrichment failed: %s", e)
```

In `main`, add the argparse flag (after the `--skip-lastfm` argument, ~line 91):

```python
    parser.add_argument(
        "--skip-popularity",
        action="store_true",
        help="skip global-popularity enrichment (Last.fm + ListenBrainz).",
    )
```

And pass it through in the `run_pipeline(...)` call inside `main` (~line 100):

```python
    run_pipeline(
        skip_spotify=args.skip_spotify,
        skip_lastfm=args.skip_lastfm,
        skip_popularity=args.skip_popularity,
        out_root=args.out_dir,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_run_bidaily_popularity.py -v`
Expected: both PASS.

- [ ] **Step 5: Full regression + commit**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all tests pass (previous suite + the new popularity tests).

```bash
git add run_bidaily.py tests/test_run_bidaily_popularity.py
git commit -m "feat: run popularity enrichment in the bi-daily pipeline"
```

---

## Self-Review

**Spec coverage:**
- §1 storage (`track_popularity` table + helpers) → Task 1. ✅
- §2 normalization → Task 2. ✅
- §3 fetch + fallback + resolve + unmatched-handling → Task 3 (resolve) & Task 5 (50 read default). ✅
- §4 enrichment CLI + bi-daily wiring → Task 4 (CLI) & Task 6 (wiring). ✅
- §5 dashboard read-path swap → Task 5. ✅
- §6 config `LISTENBRAINZ_TOKEN` → Task 4 Step 1. ✅
- §Testing items → covered across Tasks 1–6 test files. ✅

**Placeholder scan:** No TBD/TODO. The ListenBrainz endpoint verification is an explicit pre-flight curl step with a named fallback action, not a vague placeholder. Every code step shows full code. ✅

**Type consistency:** `resolve_popularity(...) -> {listeners, popularity, source}` is produced in Task 3 and consumed identically in Task 4's `enrich_all_popularity` and its tests. `db.get_track_popularity` row fields (`listeners`, `popularity`, `source`) match between Task 1 (schema), Task 4, and Task 5. `track_key` normalization (`normalize(artist) + "\t" + normalize(title)`) is identical in Tasks 1, 4, and the Task 5 test. `enrich_all_popularity` keyword signature (`lastfm_api_key`, `listenbrainz_token`, `fetch`, `sleep`, `progress`, `refresh`) matches between Task 4 def, Task 4 tests, and Task 6 call (which passes only the two keys, relying on defaults). ✅
