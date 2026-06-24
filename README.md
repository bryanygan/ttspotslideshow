# TikTok Music Rotation

Automated listening-history → Spotify-style Now-Playing card → TikTok slideshow
generator, plus a weekly recap picker. See [CLAUDE.md](CLAUDE.md) for the full
project context and roadmap.

**Status:**
- ✅ **Phase 1 — Logger.** Banks your Spotify plays into a local SQLite DB (live capture).
- ✅ **Phase 2 — Card renderer.** Pillow engine that renders a Spotify-style card per
  track and composites four into a 1080×1920 slide. 25 tests passing.
- ⏭️ **Phase 3 — Selection + slideshow** (next): import history, pick 12–16 tracks
  across genres, output dated slides.

> **Heads-up on the Spotify API (verified June 2026):** `recently-played`, top-tracks,
> artist genres, and album art all still work. Two changes matter:
> `track.popularity` was removed (so the future "most underrated" metric needs a
> play-count signal instead), and **the app owner must have an active Spotify Premium
> subscription** or the API stops working.

---

## Data sources

| Source | Role | Notes |
|--------|------|-------|
| **Last.fm scrobble export** (`data/scrobbles-*.xml`) | Historical backbone | ~108k timestamped scrobbles (2020→2026), 15.5k tracks, album art ≤300×300. No genre/duration in the export. |
| **Spotify logger** (`logger.py`) | Live ongoing capture | Last-50 buffer; run on a schedule. |

The renderer is data-source-agnostic — it takes a simple track dict
(`track_id`, `title`, `artist`, `art_url`), so it works with either source.

---

## Project layout

```
ttspotslideshow/
├── CLAUDE.md             # full project context & roadmap
├── README.md            # you are here
├── requirements.txt     # runtime deps (spotipy, python-dotenv, Pillow)
├── requirements-dev.txt # dev deps (pytest)
├── .env.example         # template for your Spotify credentials
├── config.py            # loads settings/paths (single source of truth)
├── db.py                # SQLite schema + queries
├── spotify_client.py    # spotipy OAuth wrapper
├── logger.py            # Phase 1 entry point: log recently-played tracks
├── render/              # Phase 2 rendering engine
│   ├── colors.py        #   dominant-color extraction + gradient
│   ├── fonts.py         #   cached Montserrat loading + text truncation
│   ├── art.py           #   album-art download + on-disk cache
│   ├── card.py          #   render_card(track) -> 540×960 card (the core unit)
│   ├── collage.py       #   four cards -> 1080×1920 slide
│   ├── render_demo.py   #   CLI: render a sample 2×2 slide
│   └── assets/fonts/    #   Montserrat .ttf files (tracked)
├── tests/               # pytest suite for the renderer
├── docs/superpowers/    # design spec + implementation plan
├── data/                # SQLite DB, Last.fm export, album-art cache (git-ignored)
└── output/              # generated slides (git-ignored)
```

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

### 2. Configure local credentials
```powershell
# from the project folder
Copy-Item .env.example .env
```
Open `.env` and paste in your Client ID and Client Secret.

### 3. Create the Python environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
```
> If `Activate.ps1` is blocked, run once:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### 4. Authorize (first run only)
```powershell
python logger.py --auth
```
A browser opens; approve access. The token is cached in `.spotify_cache`, so you
won't be prompted again.

---

## Running the logger

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

## Rendering cards (Phase 2)

Render a sample 2×2 slide from a few real tracks (downloads their album art):
```powershell
python -m render.render_demo
```
Output lands at `output/slides/demo/slide_1.png` (1080×1920).

Each card shows album art, title, artist, and a progress scrubber on a gradient
pulled from the album art's dominant color. The scrubber position is seeded from
the track id, so the same track always renders the same (plausible-looking) spot.

Run the test suite:
```powershell
python -m pytest -q
```

---

## What's next (roadmap)

- **Phase 3 — Selection + slideshow** (next): import the Last.fm export into SQLite,
  query a bi-daily window, pick 12–16 unique tracks across distinct genres, chunk
  into groups of 4 → dated folder of slides.
- **Phase 4 — Automate the bi-daily run** (Task Scheduler).
- **Phase 5 — Weekly recap dashboard** (React/TS) for hand-picking best/underrated.

> Two open items feed Phase 3: a **genre source** for the Last.fm data (Spotify
> per-artist lookup vs Last.fm tags), and finishing **Phase 0** so the live logger
> starts collecting.
