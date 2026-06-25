# TikTok Music Rotation

Automated listening-history → Spotify-style Now-Playing card → TikTok slideshow
generator, plus a (future) weekly recap picker. See [CLAUDE.md](CLAUDE.md) for the
full project context and roadmap.

**Status:**
- ✅ **Phase 1 — Logger.** Banks your Spotify plays into a local SQLite DB (live capture).
- ✅ **Phase 2 — Card renderer.** Pillow engine that renders a Spotify-style card per
  track and composites four into a 1080×1920 slide.
- ✅ **Phase 3 — Ingest + selection + slideshow.** Imports your Last.fm history,
  enriches per-artist genres (Spotify → Last.fm fallback), picks 12–16 tracks across
  genres for a bi-daily window, and writes a dated folder of slides.
- ⏭️ **Phase 4 — Automate the bi-daily run** (Task Scheduler) — next.
- ⏭️ **Phase 5 — Weekly recap dashboard** (React/TS) — later.

All 88 tests pass (`python -m pytest -q`).

> **Heads-up on the Spotify API (verified June 2026):** `recently-played`, top-tracks,
> artist genres, and album art all still work, but three things matter:
> - `track.popularity` was removed (so the future "most underrated" metric needs a
>   play-count signal instead).
> - **The app owner must have an active Spotify Premium subscription** or the API stops
>   working.
> - The app runs in **Development Mode** and is **aggressively rate-limited**. Genre
>   enrichment that hits Spotify too hard can trigger an extended HTTP 429 block lasting
>   hours. The enrichment tooling is hardened against this (see
>   [Importing history + enriching genres](#phase-3a--importing-history--enriching-genres)).

---

## Data sources

| Source | Role | Notes |
|--------|------|-------|
| **Last.fm scrobble export** (`data/scrobbles-*.xml`) | Historical backbone | ~108k timestamped scrobbles (2020→2026). No genre/duration in the export — genres come from enrichment. |
| **Spotify logger** (`logger.py`) | Live ongoing capture | Last-50 buffer; run on a schedule. |

The two sources are merged in the `plays` table (tagged by `source`) and deduplicated
across sources at query time. The renderer is data-source-agnostic — it takes a simple
track dict, so it works with either.

---

## Project layout

```
ttspotslideshow/
├── CLAUDE.md             # full project context & roadmap (local-only, git-ignored)
├── README.md            # you are here
├── requirements.txt     # runtime deps (spotipy, python-dotenv, Pillow)
├── requirements-dev.txt # dev deps (pytest)
├── .env.example         # template for Spotify + Last.fm credentials
├── config.py            # loads settings/paths (single source of truth)
├── db.py                # SQLite schema + all queries (the data layer)
├── text_norm.py         # normalize() — shared artist/title normalization
├── spotify_client.py    # spotipy OAuth wrapper
├── logger.py            # Phase 1: log Spotify recently-played -> plays
├── ingest/              # Phase 3A: Last.fm import + genre enrichment
│   ├── lastfm_import.py #   stream-parse export XML -> plays (source='lastfm')
│   ├── lastfm_client.py #   stdlib Last.fm getTopTags client
│   ├── genre_map.py     #   micro-genre -> hybrid bucket map + bucket_for()
│   ├── genres.py        #   resolve_artist_genre / enrich_all (Spotify -> Last.fm)
│   └── enrich_cli.py    #   `python -m ingest.enrich_cli [--lastfm-only|--refresh]`
├── render/              # Phase 2: the card/collage renderer (Pillow)
│   ├── colors.py        #   dominant-color extraction + gradient
│   ├── fonts.py         #   cached Montserrat loading + text truncation
│   ├── art.py           #   album-art download + on-disk cache
│   ├── card.py          #   render_card(track) -> 540×960 card (the core unit)
│   ├── collage.py       #   four cards -> 1080×1920 slide
│   ├── render_demo.py   #   CLI: render a sample 2×2 slide
│   └── assets/fonts/    #   Montserrat .ttf files (tracked)
├── slideshow/           # Phase 3B: selection + assembly
│   ├── window.py        #   resolve_window (auto-widen 2→4→7→14→30 days)
│   ├── selector.py      #   genre round-robin + play/recency/novelty score
│   ├── art_resolve.py   #   iTunes hi-res art (600×600) + Last.fm fallback
│   ├── builder.py       #   build_slideshow: select -> art -> render -> collage -> files
│   └── cli.py           #   `python -m slideshow.cli`
├── tests/               # pytest suite (all offline)
├── docs/superpowers/    # design specs + implementation plans
├── data/                # SQLite DB, Last.fm export, album-art cache (git-ignored)
└── output/slides/<date>/ # generated slides (git-ignored)
```

### Data model (`db.py`, `data/plays.db`)

- **`plays`** — one row per play event (`track_id, name, artist, artist_id,
  artist_genre, album_art_url, popularity, played_at, source, played_at_unix`).
  `source` is `'spotify'` (logger) or `'lastfm'` (import).
- **`artist_genres`** — the genre source for selection, keyed by normalized artist name.
  Holds the resolved Spotify/Last.fm tags, a `primary_bucket`, and `genre_source`
  (`'spotify'` | `'lastfm'` | `'none'`).
- **`featured_tracks`** — records what the slideshow has already posted, so a track isn't
  repeated for ~14 days (the "novelty" signal).

`db.migrate(conn)` is idempotent and is run by `init_db()` and by the ingest CLI. The
slideshow CLI does **not** migrate — run `python -c "import db; db.init_db()"` once before
the first slideshow if `featured_tracks` doesn't exist yet.

---

## Phase 0 — One-time setup

### 1. Register a Spotify app
1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
   and sign in with your **Premium** account.
2. Click **Create app**. Name/description can be anything.
3. Under **Redirect URIs**, add exactly:
   `http://127.0.0.1:8888/callback`
   (Spotify requires the loopback IP `127.0.0.1`, not `localhost`.)
4. Save, then open **Settings** to copy your **Client ID** and **Client Secret**.

### 2. (Optional) Get a Last.fm API key
Genre enrichment and history import use Last.fm. Create a free key at
[last.fm/api/account/create](https://www.last.fm/api/account/create).

### 3. Configure local credentials
```powershell
# from the project folder
Copy-Item .env.example .env
```
Open `.env` and paste in your Spotify Client ID/Secret and (optionally) your Last.fm
API key + shared secret.

### 4. Create the Python environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
```
> If `Activate.ps1` is blocked, run once:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### 5. Authorize Spotify (first run only)
```powershell
python logger.py --auth
```
A browser opens; approve access. The token is cached in `.spotify_cache`, so you
won't be prompted again.

---

## Running the logger (Phase 1)

```powershell
python logger.py
```
Prints how many new plays were added and the running total. Run it whenever — it
only fetches plays newer than what it already has and ignores duplicates.

### Scheduling it (Windows Task Scheduler)

Spotify's `recently-played` only returns your **last 50 plays**, so run the logger
several times a day to make sure nothing slips past that buffer.

1. Open **Task Scheduler** → **Create Task**.
2. **General:** name it "Spotify Play Logger"; check *Run whether user is logged
   on or not*.
3. **Triggers:** New → *Daily*, then set **Repeat task every 3 hours** for a
   duration of *Indefinitely*. (Every 3–4 hours is plenty unless you listen very
   heavily.)
4. **Actions:** New → *Start a program*:
   - **Program/script:** `C:\Users\prinp\Documents\GitHub\ttspotslideshow\.venv\Scripts\python.exe`
   - **Add arguments:** `logger.py`
   - **Start in:** `C:\Users\prinp\Documents\GitHub\ttspotslideshow`
5. Save.

---

## Phase 3A — Importing history + enriching genres

This step imports the Last.fm export into the `plays` table and resolves a genre for
every artist (used to spread the slideshow across genres). It is **resumable** — safe to
re-run if interrupted; it skips artists already done.

```powershell
# 1. Drop your Last.fm export at data/scrobbles-*.xml (newest is auto-detected).
# 2. Import history + enrich genres:
python -m ingest.enrich_cli
```

Genre resolution tries **Spotify first** (richer subgenres like `rage`/`plugg`), then
falls back to **Last.fm tags**. It prints progress and a final bucket distribution.

### Spotify rate-limit strategy (important)

The Spotify app is in Development Mode and is aggressively rate-limited. A bulk
enrichment run can trip an extended **HTTP 429 block lasting hours**. The CLI is hardened
(short timeout, no long retry sleeps, commits every 50 artists, stops early after
repeated 429s), but the practical workflow is:

| When | Command | What it does |
|------|---------|--------------|
| Spotify is blocked / you want genres **now** | `python -m ingest.enrich_cli --lastfm-only` | Resolves genres from Last.fm only (never touches Spotify). Rows get `genre_source='lastfm'` or `'none'`. |
| Spotify block has lifted | `python -m ingest.enrich_cli --refresh` | Re-processes every non-Spotify artist and upgrades it to richer Spotify genres. Spotify-sourced rows are left alone; if still rate-limited it defers and you re-run later. |
| Normal first run | `python -m ingest.enrich_cli` | Spotify-primary with Last.fm fallback. |

**Check whether Spotify is still blocked** (prints genres = unblocked; raises 429 =
still blocked):
```powershell
python -c "from spotify_client import get_client; print(get_client().search(q='Drake',type='artist',limit=1)['artists']['items'][0]['genres'])"
```

> **Don't hammer the Spotify API.** Prefer `--lastfm-only` for bulk work and reserve
> `--refresh` for an occasional, spaced-out upgrade pass.

---

## Phase 3B — Generating the slideshow

```powershell
# First time only: ensure the featured_tracks table exists.
python -c "import db; db.init_db()"

# Build the slides:
python -m slideshow.cli
```

Output lands in `output/slides/<today>/` as `slide_1.png`, `slide_2.png`, … (each
1080×1920). The CLI prints how many slides it wrote, the window it used, and the genre
spread.

**How selection works:**
- **Window:** starts with the last 2 days and auto-widens (2 → 4 → 7 → 14 → 30 days)
  until it can fill a slide.
- **Variety:** round-robins across genre buckets so a single slide isn't all one genre.
- **Freshness:** each candidate is scored on play count, recency, and novelty (tracks
  featured in the last ~14 days are penalized so the rotation stays fresh).
- **Count:** targets 16 tracks (floor 12), chunked into groups of 4 → 3–4 slides.
- **Art:** pulls hi-res album art from iTunes (600×600), falling back to Last.fm.

Then post the slides to TikTok manually (TikTok has no clean posting API for personal
accounts — image generation is automated, the ~30-second upload is not).

### Screenshot OCR Playlist Ingest (Optional)

If you have a playlist or queue screenshot from Spotify or Apple Music, you can run the built-in Windows OCR pipeline to read the song names and artists from the image, match them to high-resolution artwork, and compile them into a slideshow:

```powershell
python -m slideshow.ocr <path_to_screenshot>
```

Options:
- `--skip-render`, `-s`: Print identified tracks and artists to terminal without rendering the final slides.
- `--out-dir <path>`: Override the default slide output directory.

This uses Windows 11's native high-performance OCR engine, requiring **zero extra Python package installations or models to download**.

### Slide Diversity & Dispersion

To keep slideshows engaging, the generator automatically shuffles and disperses selected tracks so that **no single slide (4 cards) contains more than 1 track from the same artist or album** (using the artwork URL as a proxy). If there are too many duplicates, the algorithm falls back to distributing them as evenly as possible across the slides.

---

## Phase 4 — Automation (Bi-daily scheduled run)

We automate the full generation pipeline using a single orchestration script `run_bidaily.py`. On each execution, this script:
1. Migrates the database if any migrations are pending (`db.init_db()`).
2. Pulls recently played tracks from Spotify (`logger.py`).
3. Fetches new scrobbles incrementally from the Last.fm API (`import_recent_from_api`).
4. Selects candidates, resolves artwork, and builds the slideshow into `output/slides/<date>/`.

### Run manually:
```powershell
python run_bidaily.py
```

Options:
- `--skip-spotify`: Skip logging Spotify recently played tracks (e.g. if credentials are unconfigured or blocked).
- `--skip-lastfm`: Skip importing from the Last.fm API.
- `--out-dir <path>`: Override the default slide output directory.

### Windows Task Scheduler Setup

To schedule the generation of slideshow slides automatically (e.g., every other day):

1. Open **Task Scheduler**.
2. Click **Create Basic Task...** and name it (e.g. `Spotify-Slideshow-Generator`).
3. Set Trigger to **Daily**, and set **Recur every: 2 days**.
4. Set Action to **Start a program**.
5. Fill in the parameters:
   - **Program/script**: Path to virtualenv python, e.g. `C:\Users\prinp\Documents\GitHub\ttspotslideshow\.venv\Scripts\python.exe`
   - **Add arguments**: `run_bidaily.py`
   - **Start in**: Repo root folder, e.g. `C:\Users\prinp\Documents\GitHub\ttspotslideshow` (critical for resolving relative file outputs and databases).
6. Save the task.

### Periodic Spotify Genre Upgrade (Optional)

Since the Spotify API is subject to aggressive rate limits, bulk updates can trigger 429 blocks. Once your initial bulk Last.fm tags are resolved, you can schedule a separate daily/weekly task to run the enrichment refresh:
- **Program/script**: `C:\Users\prinp\Documents\GitHub\ttspotslideshow\.venv\Scripts\python.exe`
- **Add arguments**: `-m ingest.enrich_cli --refresh`
- **Start in**: `C:\Users\prinp\Documents\GitHub\ttspotslideshow`

This task incrementally upgrades artists in your database from Last.fm tags to richer Spotify genres over time, without hammering the API.

---

## Phase 5 — Weekly Recap Dashboard (Web UI)

The weekly recap dashboard is a React + TypeScript + Tailwind CSS web application served by a lightweight Python backend server (`dashboard_server.py`). It enables you to:
- Browse track candidates from the last 7, 14, or 30 days.
- Sort them by **Play Count** or **Underrated Score** (clamping high personal plays against low Spotify global popularity).
- Review historical selection details (e.g. if the track was featured recently).
- Manually check/select tracks (target 4, 8, 12, 16) and generate compilation slide collages.

### 1. Build and Run the Dashboard

First, build the frontend client bundle:
```powershell
cd dashboard
npm run build
cd ..
```

Then, launch the Python server from the root of the repository:
```powershell
python dashboard_server.py
```

Open your browser and navigate to **[http://localhost:8000/](http://localhost:8000/)**.

### 2. Run in Development Mode (Optional)

If you'd like to run live development hot-reloading for the dashboard UI:
1. Start the backend server: `python dashboard_server.py`
2. Start the Vite React development server:
   ```powershell
   cd dashboard
   npm run dev
   ```
3. Open **[http://localhost:5173/](http://localhost:5173/)** (which will automatically query the backend server on port 8000).

### 3. Saving slides to your phone (iPhone → iCloud Photos)

After you click **Generate Recap Slides**, the rendered slides appear in the
**Your Slides** panel as full images (they're served by the backend at
`GET /api/slides/<recap-id>/slide_N.png`). To save them:

- **iPhone:** long-press a slide → **Add to Photos**. It lands in your Camera
  Roll and syncs to iCloud Photos, ready to post to TikTok.
- **Desktop:** right-click → **Save image**.

The slides are also written to `output/slides/recap-<date>/` on the host.

---

## Remote access — deploy the dashboard (Cloudflare Pages + Tunnel)

> **Architecture:** Cloudflare Pages only hosts the **static React frontend**. The
> actual generation (Pillow, the SQLite DB, your Last.fm data) runs on the host PC
> via `dashboard_server.py`. The hosted page reaches the host through a Cloudflare
> Tunnel. So to use this away from home you need: (1) the host PC always-on running
> the server, (2) a tunnel exposing it as HTTPS, (3) the Pages site pointed at that
> tunnel URL.

### 1. Run the project on an always-on PC (e.g. a mini PC)

```powershell
git clone https://github.com/bryanygan/ttspotslideshow.git
cd ttspotslideshow
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
```

Copy these **gitignored** files over from your dev machine (same paths):
`.env`, `.spotify_cache` (cached OAuth token — avoids a browser prompt under Task
Scheduler), `data/plays.db`, and `data/scrobbles-*.xml`. Then verify:
`python -m pytest -q`.

Set up the bi-daily Task Scheduler job (see **Phase 4** above) and run the
dashboard backend on boot (a Task Scheduler task triggered **At startup**, *Run
whether user is logged on or not*, running `dashboard_server.py`).

### 2. Deploy the frontend to Cloudflare Pages (one-time)

1. Cloudflare dashboard → **Workers & Pages → Create → Pages → Connect to Git** →
   select this repo.
2. Build settings:
   - **Framework preset:** Vite
   - **Build command:** `npm run build`
   - **Build output directory:** `dist`
   - **Root directory (Advanced):** `dashboard`
3. Deploy → you get `https://<project>.pages.dev`.

### 3. Expose the host backend with a Cloudflare Tunnel

Cloudflare Pages is HTTPS, so it can't call `http://localhost:8000` remotely — use
an HTTPS tunnel. On the host, install `cloudflared`, then either:

- **Quick (ephemeral URL, good for testing):**
  ```powershell
  cloudflared tunnel --url http://localhost:8000   # prints https://<random>.trycloudflare.com
  ```
- **Permanent URL (needs a domain on Cloudflare):** create a *named* tunnel, route
  a subdomain (e.g. `recap.yourdomain.com`) to `localhost:8000`, and
  `cloudflared service install` so it survives reboots.

The server already sends `Access-Control-Allow-Origin: *`, so cross-origin calls
from `*.pages.dev` work out of the box.

### 4. Connect & secure

- On your `pages.dev` site, paste the tunnel URL into the header **Backend API**
  field (saved per-browser in localStorage — set it once on each device).
- **Lock it down with Cloudflare Access** (Zero Trust): the tunnel is public, so
  add an Access **self-hosted application** on the tunnel hostname with a policy
  that allows only your email (one-time PIN). This requires no code change and
  stops anyone else from hitting `/api/generate`.

---

## Rendering cards directly (Phase 2 demo)

Render a sample 2×2 slide from a few real tracks (downloads their album art):
```powershell
python -m render.render_demo
```
Output lands at `output/slides/demo/slide_1.png` (1080×1920).

Each card shows album art, title, artist, and a progress scrubber on a gradient
pulled from the album art's dominant color. The scrubber position is seeded from
the track id, so the same track always renders the same (plausible-looking) spot.

---

## Running the tests

All tests are offline (network is dependency-injected / monkeypatched):
```powershell
python -m pytest -q
```

---

## What's next (roadmap)

- **Phase 4 — Automate the bi-daily run.** A single entry script (freshen plays →
  migrate → build slideshow) scheduled via Task Scheduler, plus an occasional, spaced-out
  `--refresh` task to upgrade Last.fm genres to Spotify once the rate-limit block clears.
- **Phase 5 — Weekly recap dashboard** (React/TS) for hand-picking best/underrated tracks.
