# TikTok Music Rotation

Automated Spotify → Now-Playing card → TikTok slideshow generator, plus a weekly
recap picker. See [CLAUDE.md](CLAUDE.md) for the full project context and roadmap.

**Status:** Phase 1 (the logger) is built. It quietly banks your listening history
into a local SQLite DB so every later phase has data to work with.

> **Heads-up on the Spotify API (verified June 2026):** the logger, top-tracks,
> artist genres, and album art all still work. Two things changed:
> `track.popularity` was removed (so the future "most underrated" metric needs a
> different signal — play-count based for now), and **the app owner must have an
> active Spotify Premium subscription** or the API stops working.

---

## Project layout

```
ttspotslideshow/
├── CLAUDE.md            # full project context & roadmap
├── README.md           # you are here
├── requirements.txt    # Python dependencies
├── .env.example        # template for your Spotify credentials
├── config.py           # loads settings/paths (single source of truth)
├── db.py               # SQLite schema + queries
├── spotify_client.py   # spotipy OAuth wrapper
├── logger.py           # Phase 1 entry point: log recently-played tracks
└── data/               # local SQLite DB lives here (git-ignored)
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
pip install -r requirements.txt
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

---

## Scheduling it (Windows Task Scheduler)

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

## What's next (roadmap)

- **Phase 2 — Song-card renderer** (next): Pillow renders one Spotify-style card
  (album art, title, artist, scrubber) per song. We'll brainstorm the exact look
  before building, and nail one perfect card before scaling.
- **Phase 3 — Collage + slideshow:** 2×2 grid of cards → 1080×1920 slides.
- **Phase 4 — Automate the bi-daily run.**
- **Phase 5 — Weekly recap dashboard** (React/TS).
