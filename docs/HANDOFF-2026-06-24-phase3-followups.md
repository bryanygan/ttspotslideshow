# HANDOFF — Phase 3 follow-ups (2026-06-24)

> **You are a fresh agent picking up this project.** This document is self-contained:
> read it top to bottom before doing anything. It captures the full project state,
> history, conventions, and four work items to complete. The previous agent's
> conversation context has been cleared — this file is the source of truth.

---

## 0. TL;DR — what to do

Four work items, detailed in §6. Recommended order: **WI-1 (docs)** → **WI-3 (genre
coverage)** → **WI-2 (cleanup)** → **WI-4 (Phase 4 automation)**.

First, **get the full code into one place** (§5): the project has work split across an
already-merged branch plus two open PRs plus a local integration branch. Easiest path:
merge PRs #2 and #3 to `master`, then work from `master`.

There is a **background genre-enrichment process running** (§4.3) — don't fight it for
the DB; it finishes on its own.

---

## 1. What this project is

An automated pipeline that turns the owner's (Bryan's) music listening history into
**TikTok slideshow images** — Spotify-style "now playing" cards, 4 to a 1080×1920 slide,
posted every other day. Plus (future) a weekly recap picker.

Full original brief and roadmap: **`CLAUDE.md`** (read it — it has the product vision,
constraints, and the Phase 0–5 roadmap). Key facts from it:
- **Owner:** Bryan (GitHub `bryanygan`), beginner-friendly outputs preferred, stack
  React/TS/Tailwind for any web UI.
- **TikTok posting is manual** (no API automation) — we only generate image files.
- **Spotify Web API constraints (verified June 2026):** `track.popularity` was removed;
  the app owner must have Premium; editorial playlists & batch endpoints are gone. The
  app runs in Development Mode and is **subject to aggressive rate-limiting** (this bit us
  hard — see §4.4).

## 2. Tech & conventions

- **Python 3.12**, Windows 11. Virtualenv at `.venv`. **Always** run Python as
  `.\.venv\Scripts\python.exe` (PowerShell) or `./.venv/Scripts/python.exe` (bash).
- **No new runtime dependencies** unless truly needed. Current deps: `spotipy`,
  `python-dotenv`, `Pillow` (runtime); `pytest` (dev). Everything else is stdlib
  (`sqlite3`, `urllib`, `xml.etree`, `json`, `datetime`).
- **Tests:** `pytest`, all **offline** (network is dependency-injected via `fetch=`
  params or stub clients; album-art download is monkeypatched). Run the whole suite with
  `./.venv/Scripts/python.exe -m pytest -q`. As of this handoff the integration branch
  has **88 passing**.
- **Commit messages MUST end with this trailer** (the repo convention):
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  ```
- **`.env`** holds secrets (gitignored): `SPOTIPY_CLIENT_ID/SECRET`, `SPOTIPY_REDIRECT_URI`,
  `LAST_FM_API_KEY`, `LAST_FM_SHARED_SECRET`. The Spotify OAuth token is cached in
  `.spotify_cache` (Phase 0 auth is done). **Note the env var is `LAST_FM_API_KEY`
  (underscores) but the Python attribute is `config.LASTFM_API_KEY`** — intentional.
- **gitignored:** `.venv/`, `.env*`, `.spotify_cache`, `data/*.db`, `data/*.xml`,
  `data/*.log`, `output/`, `data/album_art/`, **`CLAUDE.md`** (local-only), and
  `.superpowers/` (the previous agent's scratch — ignore it).
- **Development workflow used so far** (the "superpowers" skills): brainstorm → spec →
  plan → subagent-driven TDD execution → review. Specs live in
  `docs/superpowers/specs/`, plans in `docs/superpowers/plans/`. You don't have to use
  this workflow for the small items, but the specs/plans are great context.

## 3. Architecture & file map

```
ttspotslideshow/
├── CLAUDE.md                  # product vision + roadmap (gitignored, local)
├── README.md                  # user-facing docs (STALE — see WI-1)
├── config.py                  # env + paths; assert_credentials(); resolve_export_path()
├── db.py                      # SQLite: schema/migrate + all queries (the data layer)
├── text_norm.py               # normalize() — shared artist/title normalization
├── spotify_client.py          # spotipy OAuth wrapper (get_client)
├── logger.py                  # Phase 1: log Spotify recently-played -> plays
├── ingest/                    # Phase 3A: Last.fm import + genre enrichment
│   ├── lastfm_import.py        #   stream-parse export XML -> plays (source='lastfm')
│   ├── lastfm_client.py        #   stdlib Last.fm getTopTags client
│   ├── genre_map.py            #   micro-genre -> hybrid bucket map + bucket_for()
│   ├── genres.py               #   resolve_artist_genre / enrich_all (Spotify→Last.fm)
│   └── enrich_cli.py           #   `python -m ingest.enrich_cli [--lastfm-only|--refresh]`
├── render/                    # Phase 2: the card/collage renderer (Pillow)
│   ├── colors.py               #   dominant color + gradient
│   ├── fonts.py                #   Montserrat loading + truncate_to_width
│   ├── art.py                  #   album-art download + cache (load_art, is_placeholder)
│   ├── card.py                 #   render_card(track) -> 540x960 PIL.Image
│   ├── collage.py              #   collage(cards) -> 1080x1920 slide
│   ├── render_demo.py          #   demo CLI
│   └── assets/fonts/           #   Montserrat .ttf (tracked)
├── slideshow/                 # Phase 3B: selection + assembly
│   ├── window.py               #   resolve_window (auto-widen 2→4→7→14→30 days)
│   ├── selector.py             #   genre round-robin + play/recency/novelty score
│   ├── art_resolve.py          #   iTunes hi-res art (600x600) + Last.fm fallback
│   ├── builder.py              #   build_slideshow: select→art→render→collage→files
│   └── cli.py                  #   `python -m slideshow.cli`
├── tests/                     # pytest (offline)
├── docs/superpowers/specs/    # design specs (read for deep context)
├── docs/superpowers/plans/    # implementation plans
├── data/                      # plays.db, the Last.fm export xml, album_art cache (gitignored)
└── output/slides/<date>/      # generated slides (gitignored)
```

### Data model (`db.py`, `plays.db`)
- **`plays`** — one row per play event. Columns: `track_id, name, artist, artist_id,
  artist_genre, album_art_url, popularity, played_at, source, played_at_unix`. `source`
  is `'spotify'` (logger) or `'lastfm'` (import). UNIQUE on
  `(source, artist, track_id, name, played_at)`.
- **`artist_genres`** — keyed by normalized artist name (`artist_key`). Columns:
  `artist_key, display_name, spotify_artist_id, raw_genres, lastfm_tags, primary_bucket,
  genre_source ('spotify'|'lastfm'|'none'), fetched_at`. THE genre source for selection.
- **`featured_tracks`** — `track_key, last_featured_date, times_featured`. Records what
  the slideshow has posted, so it isn't repeated for ~14 days (novelty).
- **`artists`** — legacy Phase-1 genre cache keyed by Spotify artist_id; not used by
  Phase 3, leave it alone.
- `db.migrate(conn)` is idempotent and rebuilds old-schema `plays`. `db.canonical_plays(conn,
  window_seconds=120)` collapses cross-source duplicates (same normalized artist+title,
  different source, within window, Spotify preferred).

### Genre buckets (`ingest/genre_map.py`)
Hybrid set: rap subgenres `rage, trap, drill, plugg, boom-bap, melodic-rap` + the generic
`hip-hop` + broad `pop, r&b, rock, electronic, indie, country, latin` + `other`/`unknown`.
`bucket_for(genres)` returns the first genre that maps; `'other'` if non-empty-unmapped;
`'unknown'` if empty.

## 4. Current state (as of 2026-06-24, ~23:30)

### 4.1 Phases complete
- **Phase 0** (Spotify auth) — done (token cached).
- **Phase 1** (logger) — built and merged. 50 Spotify plays banked in `plays.db`.
- **Phase 2** (renderer) — built, reviewed, **merged to master**.
- **Phase 3A** (Last.fm ingest + genre enrichment) — built, reviewed, **merged to master**
  (PR #1).
- **Phase 3B** (slideshow selection + assembly) — built, reviewed, **PR #2 OPEN**.
- **Enrichment hardening + `--lastfm-only`/`--refresh` modes** — built, reviewed,
  **PR #3 OPEN**.

### 4.2 Git branches / PRs
- `master` — Phase 2 + 3A merged; has the design specs/plans for 3B.
- **PR #2** `phase3b-slideshow` — the `slideshow/` package + `db.py` additions
  (`window_track_candidates`, `featured_tracks`). Reviewed, ready to merge.
- **PR #3** `harden-enrichment` — enrichment robustness (`ingest/genres.py`,
  `ingest/enrich_cli.py`, `spotify_client.py`, `tests/test_enrich_hardening.py`).
  Reviewed, ready to merge.
- `phase3-integration` (local only, not pushed) — **merges #2 + #3**; this is where the
  full code currently lives and where the slideshow + enrichment were run. 88 tests pass.
- The two PRs are **conflict-free** with each other (3B touches `slideshow/`+`db.py`;
  hardening touches `ingest/`+`spotify_client.py`). **Recommended: merge both PRs to
  master, delete `phase3-integration`, work from master.**

### 4.3 Data / DB state
`data/plays.db` (gitignored, lives only on this machine):
- **107,890 Last.fm plays + 50 Spotify plays** imported. Cross-source canonical dedup =
  **107,928**. 3,812 distinct artists.
- **Genre enrichment IS RUNNING** in the background as of this writing (Last.fm-only mode):
  ~900/3,812 done, climbing ~100/min, ETA ~30 more min. It commits every 50 and is
  resumable. It writes `data/enrich_lastfm.log`. **When you start, check if it finished:**
  ```
  ./.venv/Scripts/python.exe -c "import sqlite3;c=sqlite3.connect('data/plays.db');print(c.execute('SELECT COUNT(*) FROM artist_genres').fetchone()[0],'/ 3812')"
  ```
  If it's < 3812 and no `python -m ingest.enrich_cli` process is running, resume it:
  `./.venv/Scripts/python.exe -m ingest.enrich_cli --lastfm-only` (skips already-done).
- The Last.fm export file is at `data/scrobbles-Priinplup-1782268878.xml` (88 MB).

### 4.4 The Spotify rate-limit incident (IMPORTANT CONTEXT)
The first enrichment run hammered the Spotify API and triggered an **extended rate-limit /
abuse block (HTTP 429)** that persisted for hours. That is why:
- The enrichment was **hardened** (PR #3): `requests_timeout=10` + `retries=0` so a 429
  raises instantly instead of sleeping on a long `Retry-After`; commits every 50 artists
  (resumable); defers transient failures; stops early after 20 consecutive 429s.
- We switched to **`--lastfm-only`** to get genres now (Last.fm isn't blocked). Rows from
  Last.fm have `genre_source='lastfm'` (or `'none'`).
- **When Spotify's block lifts** (could be many hours / next day), run
  `./.venv/Scripts/python.exe -m ingest.enrich_cli --refresh` — it re-processes every
  artist whose `genre_source != 'spotify'` and upgrades them to Spotify genres (better
  subgenre granularity: `rage`/`plugg`/etc. instead of generic `hip-hop`). Spotify-sourced
  rows are left untouched; if still rate-limited it defers and you can re-run later.
- To check if Spotify is still blocked:
  ```
  ./.venv/Scripts/python.exe -c "from spotify_client import get_client; print(get_client().search(q='Drake',type='artist',limit=1)['artists']['items'][0]['genres'])"
  ```
  If it prints genres → unblocked (do the `--refresh`). If it raises 429 / "Max Retries
  reached" → still blocked.

### 4.5 Validated working slideshow
The slideshow was run on real data and produced **4 real slides** at
`output/slides/2026-06-24/` (sent to the user). Selection used the last-2-days window (16
tracks). With enrichment incomplete, all were `unknown` bucket; **re-run after enrichment
to get genre variety**: `./.venv/Scripts/python.exe -m slideshow.cli`. (Note: `slideshow.cli`
does NOT call `db.migrate` — if `featured_tracks` is missing, run
`./.venv/Scripts/python.exe -c "import db; db.init_db()"` once first.)

### 4.6 Genre-coverage observation (feeds WI-3)
At 900 artists: `lastfm` 591, `none` 309 (~34%). Buckets: unknown 309, hip-hop 234,
other 106, pop 68, electronic 51, rock 23, r&b 23, trap 20. So: variety exists, but (a)
~34% get no genre, and (b) rap subgenres are sparse because Last.fm tags are generic. Both
improve when Spotify `--refresh` runs, but WI-3 can also tune the Last.fm path.

---

## 5. FIRST STEP — consolidate the code

Before the work items, get all code on one branch. Recommended:
```bash
# from repo root, working tree clean
git checkout master
git merge --no-ff phase3b-slideshow      # PR #2
git merge --no-ff harden-enrichment      # PR #3
./.venv/Scripts/python.exe -m pytest -q  # expect ~88 passing
git push origin master                   # closes PRs #2 and #3
git branch -d phase3-integration phase3b-slideshow harden-enrichment
```
(Or merge the PRs via the GitHub UI / `gh pr merge 2 --merge && gh pr merge 3 --merge`,
then `git pull`.) Confirm with the user first if they want to review the PRs themselves.
If you'd rather not merge yet, just `git checkout phase3-integration` — it already has
everything — and do the work there.

---

## 6. THE FOUR WORK ITEMS

### WI-1 — Refresh the docs (README.md + CLAUDE.md roadmap)
**Why:** `README.md` documents only through Phase 2 / the Last.fm data source. It predates
the `ingest/` and `slideshow/` packages and the new CLIs.
**Do:**
- Update **`README.md`**: add the Phase 3 pipelines and the runnable commands:
  - `python -m ingest.enrich_cli` (+ `--lastfm-only`, `--refresh`) — import history +
    enrich genres. Explain the Spotify-rate-limit caveat and the Last.fm-now /
    Spotify-refresh-later strategy (§4.4).
  - `python -m slideshow.cli` — generate the dated TikTok slides. Explain selection
    (last-2-days auto-widen, genre round-robin, play/recency/novelty freshness, target
    16 / floor 12) and the iTunes hi-res art.
  - Update the project-layout tree and the data-flow description to include
    `plays`/`artist_genres`/`featured_tracks`, `text_norm`, and the two new packages.
  - Update the "what's next" / status section: Phases 1–3 done; Phase 4 (automation) and
    Phase 5 (recap dashboard) remain.
- Update **`CLAUDE.md` §5 roadmap** to mark Phases 1–3 complete and reflect the actual
  shape (note: `CLAUDE.md` is gitignored/local — edit it in place, it won't be committed,
  that's fine; it's the owner's local context doc).
**Verify:** the commands in the README actually run. Commit (README only; CLAUDE.md is
gitignored). No tests needed.

### WI-2 — Cleanup pass on deferred Minor findings
**Why:** Across the Phase 2 / 3A / 3B reviews, ~13 Minor findings were intentionally
deferred (none are correctness bugs). Tidy them now. Use TDD where a test is implied.
**The list (file → finding → fix):**
1. `ingest/fonts.py`? No — **`render/fonts.py`** `load_font`: raises a bare `KeyError` on an
   unknown weight. Add `if weight not in FONT_FILES: raise ValueError(...)` + a test.
2. `render/art.py` `load_art`: cached file is always named `.jpg` regardless of source
   format. Harmless (Pillow sniffs magic bytes). Optional: derive extension from URL.
3. `render/collage.py` `collage`: the `resize` fallback lacks an explicit `LANCZOS`
   resample (branch never triggers since cards are already 540×960). Add
   `resample=Image.LANCZOS` for safety. Also add an over-count (`len>4`) guard test.
4. `db.py` `record_featured`: missing `-> None` return annotation + `track_keys: list[str]`
   hint. Add them.
5. `db.py` `window_track_candidates`: redundant field double-write on first insert
   (harmless). Optionally restructure with an `else`. Add an exact `start_unix` boundary
   test.
6. `db.py` `migrate`: comment calls the `artists` table "legacy" but it's still used by the
   Phase-1 logger helpers — reword the comment. The rebuild path isn't wrapped in an
   explicit transaction (relies on `connect()` committing once) — optional, low priority.
7. `slideshow/window.py` `resolve_window`: dead `days_used = steps[-1]` pre-init line
   (always overwritten). Remove it.
8. `slideshow/selector.py`: the `floor` param is accepted but unused. **Leave it** — the
   `(n//4)*4` math already reproduces the floor tiers; a previously-suggested "fix" was
   rejected because it would yield non-multiples-of-4. Optionally just add a docstring note.
9. `slideshow/art_resolve.py`: no dedicated malformed-JSON parse-error test (covered by the
   broad `except`). Add one for completeness.
10. `slideshow/builder.py`: the test doesn't assert `genre_spread`; add an assertion. The
    `art_cache: dict` annotation is bare — make it `dict[str, str]`. There's a redundant
    re-truncation to a multiple of 4 (selector already does it) — harmless, can simplify.
11. `slideshow/cli.py`: relative output path `output/slides` depends on CWD (fine; flagged
    for WI-4 / Task Scheduler `Start in`). Bare `import db` (fine).
12. `ingest/lastfm_import.py`: `import_scrobbles` parses the file twice (once to import,
    once to count for `skipped`). Single-pass is possible but a clean refactor was
    deliberately deferred — low priority. Note `skipped` counts XML-filtered entries, not
    DB-rejected duplicates.
13. `ingest/lastfm_client.py` `get_top_tags`: `int(t.get("count", 0))` is outside the
    try/except; a non-numeric `count` would raise (Last.fm always returns ints, so it never
    happens). Optionally widen the try.
14. `ingest/canonical_plays` (db.py): no explicit test for the Last.fm-arrives-before-Spotify
    ordering (logic is correct). Add one.
**Verify:** `./.venv/Scripts/python.exe -m pytest -q` stays green after each change; commit
in small logical chunks.

### WI-3 — Improve genre coverage (reduce `unknown`, richer buckets)
**Why:** ~34% of artists get no genre from Last.fm (`genre_source='none'` → `unknown`
bucket), and rap subgenres are sparse (generic `hip-hop`). This weakens the slideshow's
genre-variety feature until Spotify `--refresh` runs.
**Investigate (read-only, safe while enrichment runs):**
- Probe Last.fm `artist.getTopTags` for top artists (Playboi Carti, Yeat, Ken Carson,
  Travis Scott, etc.) and inspect the tags + their `count` weights:
  ```
  ./.venv/Scripts/python.exe -c "from ingest.lastfm_client import get_top_tags; import config; print(get_top_tags('Ken Carson', config.LASTFM_API_KEY, min_weight=0))"
  ```
  The current threshold is **`min_weight=10`** in `ingest/lastfm_client.get_top_tags`. If
  many real genre tags sit below 10, that's why coverage is low.
**Tune (likely changes):**
- Lower `min_weight` (e.g. to 1–5) and/or take the top-N tags regardless of weight.
- Expand `ingest/genre_map.GENRE_TO_BUCKET` to cover more real Last.fm tags (Last.fm uses
  tags like `"hip-hop"`, `"underground hip hop"`, `"plugg"`, `"rage"`, `"hyperpop"`,
  `"trap"`, `"experimental"` — map the ones that appear for this catalog). Note Last.fm
  tags are messier than Spotify genres (include non-genre tags like `"seen live"`, decades,
  `"favorites"`) — keep a sensible filter.
- After tuning, re-enrich the `none`/`other` artists. Since `enrich_all` skips cached
  artists, use the `--refresh` path BUT note `--refresh` tries Spotify (blocked). For a
  **Last.fm re-pass**, the cleanest is to combine: in `enrich_all`, `refresh=True` re-processes
  non-Spotify artists and `skip_spotify=True` keeps it on Last.fm — there isn't yet a CLI
  flag combining both (`--refresh` alone uses Spotify). **Small task:** add a
  `--lastfm-refresh` CLI flag (or allow `--lastfm-only --refresh` together) that calls
  `enrich_all(..., skip_spotify=True, refresh=True)` to re-do Last.fm genres with the new
  threshold/map. Add a test.
**Verify:** re-run, check `SELECT genre_source, COUNT(*) ... GROUP BY genre_source` and the
bucket distribution; aim to cut `unknown` materially. Then re-run `slideshow.cli` and eyeball
genre variety.
**Remember:** the *real* fix for subgenre richness is the Spotify `--refresh` once unblocked
(§4.4) — WI-3 is the Last.fm-side improvement that helps regardless.

### WI-4 — Phase 4: automate the bi-daily run
**Why:** the roadmap's Phase 4 — make the slideshow generate hands-off on a schedule.
**Design notes (brainstorm with the user first; this is a real feature, not a tweak):**
- A single entry script (e.g. `run_bidaily.py` or reuse `slideshow.cli`) that, on each run:
  1. (optionally) imports any new Last.fm scrobbles / runs the Spotify logger to freshen
     `plays`. The Last.fm export is currently a manual download — decide whether to pull
     incrementally from the Last.fm `user.getRecentTracks` API instead (no 50-track limit;
     would replace the manual export). This is a known open improvement.
  2. ensures the DB is migrated, runs the slideshow build, writes `output/slides/<date>/`.
- **Windows Task Scheduler** is the host (the machine already runs Homebridge). Provide a
  ready-to-paste task: Program = `...\.venv\Scripts\python.exe`, Arguments =
  `-m slideshow.cli`, **Start in** = repo root (because the output path is relative —
  see WI-2 #11), trigger every other day. The README already documents the logger's
  scheduler setup as a template.
- **Periodic Spotify genre refresh:** schedule a separate, infrequent task running
  `python -m ingest.enrich_cli --refresh` (e.g. daily) so Last.fm genres upgrade to Spotify
  automatically once the rate-limit block clears — but space it out and keep the 429
  resilience so it never hammers Spotify again (that's what caused the block).
- Keep TikTok posting manual (out of scope by design).
**Deliverable:** the entry script (with an offline test of its orchestration, mocking the
heavy parts like the existing `slideshow` tests do) + Task Scheduler instructions in the
README + the genre-refresh schedule. Follow the spec→plan→TDD workflow if doing it
rigorously.

---

## 7. Quick verification cheat-sheet
```bash
# full test suite (offline)
./.venv/Scripts/python.exe -m pytest -q

# genre enrichment progress
./.venv/Scripts/python.exe -c "import sqlite3;c=sqlite3.connect('data/plays.db');print('enriched',c.execute('SELECT COUNT(*) FROM artist_genres').fetchone()[0],'/3812'); print(dict(c.execute('SELECT genre_source,COUNT(*) FROM artist_genres GROUP BY genre_source').fetchall()))"

# bucket distribution
./.venv/Scripts/python.exe -c "import sqlite3;c=sqlite3.connect('data/plays.db');[print(b,n) for b,n in c.execute('SELECT primary_bucket,COUNT(*) FROM artist_genres GROUP BY primary_bucket ORDER BY 2 DESC').fetchall()]"

# is Spotify still rate-limited? (genres printed = unblocked; 429 = still blocked)
./.venv/Scripts/python.exe -c "from spotify_client import get_client; print(get_client().search(q='Drake',type='artist',limit=1)['artists']['items'][0]['genres'])"

# regenerate the slideshow (after enrichment)
./.venv/Scripts/python.exe -c "import db; db.init_db()"   # ensure featured_tracks exists
./.venv/Scripts/python.exe -m slideshow.cli               # writes output/slides/<today>/

# upgrade Last.fm genres to Spotify once unblocked
./.venv/Scripts/python.exe -m ingest.enrich_cli --refresh
```

## 8. Owner preferences (from CLAUDE.md)
Highly structured, copy-paste-ready outputs; explicit file paths and step-by-step
instructions; beginner-friendly clarity; offer variations; React/TS/Tailwind for any web
UI. Confirm before irreversible/outward-facing actions. Don't hammer the Spotify API.

---

*End of handoff. Start with §0 and §5.*
