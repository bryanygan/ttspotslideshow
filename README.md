# TikTok Spotify Slideshow

> Automated listening-history → album-art card → TikTok slideshow generator with a full web dashboard for weekly recap curation.

**All 147 tests pass** (`python -m pytest -q`).

---

## What it does

Records every Spotify play, picks the best/most-underrated tracks from a rolling window, renders Spotify-style "Now Playing" card slides (1080 × 1920), and lets you curate and export a recap slideshow from a phone-optimised web dashboard — ready to post on TikTok.

### Feature highlights

| Feature | Where |
|---|---|
| Continuous Spotify play logging | `logger.py` + Task Scheduler |
| Last.fm history import + genre enrichment | `ingest/` |
| Album-art card renderer (Pillow) | `render/` |
| Slideshow builder with genre variety, freshness scoring, and artist/album dispersion | `slideshow/builder.py` |
| **AI captions** — local LLM writes the caption in your voice; hashtags added deterministically (max 5) | `slideshow/llm_caption.py` + `slideshow/caption.py` |
| **Web dashboard** — browse candidates, pick tracks, tune cover settings, generate slides | `dashboard/` + `dashboard_server.py` |
| **Screenshot OCR** — upload a Spotify queue screenshot → tracks auto-detected and added to picks | `slideshow/ocr.py` + `/api/ocr` |
| Album art from Spotify (primary) → iTunes fallback with per-track confirm/deny UI | `slideshow/art_resolve.py` |
| Manual art override — upload an image or paste a URL | `/api/overrides/upload`, `/api/art-test/save` |
| Cover slide with collage art, optional title/subtitle/theme | `render/cover.py` |
| Parallel art downloading (8–15 threads) for fast generation | `slideshow/builder.py` |
| Remote access via Cloudflare Pages + Tunnel | see [Remote access](#remote-access--deploy-the-dashboard-cloudflare-pages--tunnel) |

---

## Project layout

```
ttspotslideshow/
├── README.md
├── requirements.txt          # runtime deps (spotipy, python-dotenv, Pillow)
├── requirements-dev.txt      # dev deps (pytest)
├── .env.example              # template for Spotify + Last.fm credentials
├── config.py                 # paths, settings (single source of truth)
├── db.py                     # SQLite schema + all queries
├── text_norm.py              # normalize() — shared artist/title normalization
├── webutil.py                # itunes_search HTTP helper
├── logsetup.py               # structured logging helper
├── spotify_client.py         # spotipy OAuth wrapper
├── logger.py                 # log Spotify recently-played → plays table
├── run_bidaily.py            # orchestration: logger + lastfm + slideshow in one run
├── dashboard_server.py       # Python HTTP server for the web dashboard
│
├── ingest/                   # Last.fm import + genre enrichment
│   ├── lastfm_import.py
│   ├── lastfm_client.py
│   ├── genre_map.py
│   ├── genres.py
│   └── enrich_cli.py         #   python -m ingest.enrich_cli [--lastfm-only|--refresh]
│
├── render/                   # Pillow card + collage + cover renderer
│   ├── colors.py
│   ├── fonts.py
│   ├── art.py                #   album-art download + on-disk cache
│   ├── card.py               #   render_card(track) → 540×960 card
│   ├── collage.py            #   four cards → 1080×1920 slide
│   ├── cover.py              #   cover/hook slide (collage art + optional title)
│   └── assets/fonts/         #   Montserrat .ttf files (tracked)
│
├── slideshow/                # selection + art resolution + slide assembly
│   ├── window.py             #   resolve_window (auto-widen 2→4→7→14→30 days)
│   ├── selector.py           #   genre round-robin + play/recency/novelty score
│   ├── art_resolve.py        #   Spotify art → iTunes fallback → errors
│   ├── builder.py            #   build_slideshow: select→art→render→collage→files
│   ├── ocr.py                #   Windows OCR pipeline: screenshot → track list
│   └── cli.py                #   python -m slideshow.cli
│
├── dashboard/                # React + TypeScript web dashboard
│   ├── src/
│   │   ├── App.tsx           #   top-level layout + tab switcher
│   │   ├── lib/
│   │   │   ├── useRecap.ts   #   centralised state (candidates, picks, OCR, generation)
│   │   │   ├── api.ts        #   fetch wrappers + typed error classes
│   │   │   └── types.ts
│   │   └── options/pocket/
│   │       ├── PocketDJ.tsx  #   main picker UI (Browse / Picks / Create tabs)
│   │       └── OcrScanner.tsx#   Screenshot tab — drag-and-drop OCR upload
│   └── dist/                 #   built bundle (served by dashboard_server.py)
│
├── tests/                    # pytest suite (147 tests, all offline)
├── data/                     # SQLite DB, art cache, art overrides (git-ignored)
└── output/slides/<date>/     # generated slides (git-ignored)
```

### Data model

| Table | Purpose |
|---|---|
| `plays` | One row per play event (`track_id, name, artist, album_art_url, played_at, source, …`) |
| `artist_genres` | Genre bucket per artist (Spotify → Last.fm fallback) used by the selector |
| `featured_tracks` | Tracks already posted — penalized for ~14 days so rotation stays fresh |

`db.migrate(conn)` is idempotent. Run `python -c "import db; db.init_db()"` once before first use.

---

## One-time setup

### 1. Register a Spotify app
1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and sign in with your **Premium** account.
2. Click **Create app**.
3. Under **Redirect URIs** add: `http://127.0.0.1:8888/callback`
4. Copy your **Client ID** and **Client Secret** from Settings.

### 2. (Optional) Get a Last.fm API key
Create a free key at [last.fm/api/account/create](https://www.last.fm/api/account/create).

### 3. Configure credentials
```powershell
Copy-Item .env.example .env
# Open .env and fill in SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, and (optionally) LASTFM_API_KEY
```

### 4. Create the Python environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
```
> If `Activate.ps1` is blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### 5. Authorize Spotify (first run only)
```powershell
python logger.py --auth
```
A browser opens; approve access. The token is cached in `.spotify_cache`.

### 6. Initialize the database
```powershell
python -c "import db; db.init_db()"
```

### 7. Build the dashboard frontend
```powershell
cd dashboard
npm install
npm run build
cd ..
```

---

## Running the logger

```powershell
python logger.py
```
Fetches your last 50 Spotify plays and appends any new ones. Safe to run repeatedly — deduplicates automatically.

### Scheduling (Windows Task Scheduler)

Run several times a day so no plays slip past the 50-play buffer.

1. Open **Task Scheduler** → **Create Task**.
2. **General:** name it `Spotify Play Logger`; check *Run whether user is logged on or not*.
3. **Triggers:** Daily → repeat every **3 hours** for *Indefinitely*.
4. **Actions:** Start a program:
   - **Program/script:** `<repo>\.venv\Scripts\python.exe`
   - **Add arguments:** `logger.py`
   - **Start in:** `<repo root>`

---

## Importing history + enriching genres

```powershell
# 1. Drop your Last.fm export at data/scrobbles-*.xml (newest is auto-detected)
# 2. Import + enrich:
python -m ingest.enrich_cli
```

Genre resolution tries **Spotify first**, then falls back to **Last.fm tags**.

### Rate-limit strategy

| Situation | Command | Notes |
|---|---|---|
| First run | `python -m ingest.enrich_cli` | Spotify-primary with Last.fm fallback |
| Spotify blocked | `python -m ingest.enrich_cli --lastfm-only` | Never touches Spotify |
| After block clears | `python -m ingest.enrich_cli --refresh` | Upgrades Last.fm rows to Spotify genres |

**Check if Spotify is unblocked:**
```powershell
python -c "from spotify_client import get_client; print(get_client().search(q='Drake',type='artist',limit=1)['artists']['items'][0]['genres'])"
```

---

## CLI slideshow generation

```powershell
python -m slideshow.cli
```

Output: `output/slides/<today>/slide_1.png`, `slide_2.png`, … (1080 × 1920 each).

**Selection logic:**
- **Window:** auto-widens 2 → 4 → 7 → 14 → 30 days until a slide can be filled.
- **Variety:** round-robins across genre buckets.
- **Freshness:** tracks posted in the last ~14 days are penalized.
- **Dispersion:** no slide has more than 1 track from the same artist or album.
- **Count:** targets 16 tracks (minimum 12), chunked into groups of 4.

Each build also produces a TikTok-ready `caption` (see below).

---

## AI captions

Every slideshow gets a caption via `slideshow/caption.py`:

1. A small **local** model (default `llama3.2:1b` through [Ollama](https://ollama.com))
   writes the caption *text* in your voice, using your past captions in
   `data/captions.txt` as few-shot examples. Rotation-style posts are prioritized
   as examples.
2. Hashtags are then appended **deterministically** from the tracks' genre
   buckets (+ a rotation-flavored filler pool) — so the **max-5-hashtags** and
   **<300-char** rules can never be broken by the model.
3. If Ollama is unavailable (or the model returns junk), it silently falls back
   to an on-brand deterministic caption. A build never fails on captions.

The caption is saved as `caption.txt` next to the slides and (in the dashboard)
shown in a copyable box with a **Regenerate** button to re-roll the AI text —
so the whole flow works from your phone. See `POST /api/caption`
(`{tracks, cover_title}` → `{caption}`) for the re-roll endpoint.

**Setup:** install Ollama, then `ollama pull llama3.2:1b`. The 1B model was chosen
for a low-RAM host that also runs Homebridge — it memory-maps the weights
(~negligible committed RAM) and `keep_alive=0` unloads it right after each call.
Each caption call is then a ~15s cold start. If you re-roll captions a lot from
the dashboard, set `CAPTION_KEEP_ALIVE=2m` so successive re-rolls take ~2–3s
(the model stays resident for 2 min, then unloads).

**Config (all optional env vars):**

| Var | Default | Purpose |
|---|---|---|
| `CAPTION_AI` | `1` | Set `0`/`false` to disable the LLM and always use the deterministic caption. |
| `CAPTION_MODEL` | `llama3.2:1b` | Any pulled Ollama model. |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Where the Ollama daemon listens. |
| `CAPTION_KEEP_ALIVE` | `0` | Set e.g. `5m` to keep the model warm (faster, more RAM). |
| `CAPTION_TIMEOUT` | `60` | Seconds before giving up and falling back. |

Add more example captions to `data/captions.txt` (one per line, blank-line-separated
for multi-line ones) to steer the voice.

---

## Web dashboard

The primary interface for curating and generating recap slideshows.

```powershell
python dashboard_server.py
# → open http://localhost:8000/
```

### Tabs

| Tab | What it does |
|---|---|
| **Browse** | Grid of candidates from the last 7/14/30 days, sortable by Play Count or Underrated Score. Tap to add to picks. |
| **Picks** | Review and reorder your selection. Quick-select presets (4 / 8 / 12 / 16). |
| **Create** | Configure the optional cover slide (title, subtitle, theme), set a watermark, hit **Generate**. Slides appear inline — long-press on mobile to save to Photos. |
| **Bi-daily** | Trigger the automated pipeline on demand, watch its live log, and browse the history of past dated slide sets (with captions). See below. |
| **Screenshot** | Drag-and-drop a Spotify queue screenshot → Windows OCR detects tracks → add them to picks in one tap. |

A slim **connection banner** under the header monitors `GET /api/health`. If the
backend is unreachable it shows a clear "can't reach the backend — retrying in
Ns" strip and auto-recovers once it's back (no more cryptic blank/CORS screen);
degraded states (low disk, caption model offline, stale bi-daily slides) show as
warnings.

### Album art resolution order

When generating slides, art is resolved in this priority:

1. **Stored URL** — previously confirmed URL saved in the DB.
2. **Spotify API search** — highest-quality source; used without confirmation.
3. **iTunes fallback** — searched when Spotify finds nothing. Because iTunes results aren't always accurate, a **yellow confirmation panel** appears:
   - **✓ Looks right** → saves the URL to the DB for future runs and proceeds.
   - **✕ Wrong** → moves the track to the missing-cover upload panel.
4. **No cover found** → red **Missing Cover Art** panel with upload and URL-paste controls per track.

### File-based art overrides

Place an image in `data/art_overrides/` named `Artist Name - Song Title.ext` (case-insensitive; `.png`/`.jpg`/`.jpeg`/`.webp`). Takes priority over everything.

### Screenshot OCR (CLI)

```powershell
python -m slideshow.ocr <path_to_screenshot>
    --skip-render / -s    # print tracks only, skip rendering
    --out-dir <path>      # override output directory
```

Uses **Windows 11 native OCR** — no extra packages or models needed.

### Saving slides to your phone

After generating, slides appear in the **Create** tab. On iPhone, long-press a slide → **Add to Photos** → syncs to iCloud → ready to post to TikTok. On desktop, right-click → **Save image**.

Slides are also written to `output/slides/recap-<date>/` on the host.

---

## Automated bi-daily run

```powershell
python run_bidaily.py [--skip-spotify] [--skip-lastfm] [--out-dir <path>]
```

Runs: log Spotify plays → fetch Last.fm scrobbles → build slideshow.

You can also trigger this from the dashboard's **Bi-daily** tab (`POST
/api/bidaily/run`, which skips the slow popularity enrichment by default for a
fast on-demand build), watch its live log (`GET /api/bidaily/status`), and browse
past dated slide sets (`GET /api/bidaily/history`).

### Task Scheduler setup

1. **Task Scheduler** → **Create Basic Task** → name it `Spotify-Slideshow-Generator`.
2. **Trigger:** Daily, recur every **2 days**.
3. **Action:** Start a program:
   - **Program/script:** `<repo>\.venv\Scripts\python.exe`
   - **Add arguments:** `run_bidaily.py`
   - **Start in:** `<repo root>` ← critical for relative DB and output paths

### Optional: periodic genre upgrade task
```
Program/script: <repo>\.venv\Scripts\python.exe
Add arguments:  -m ingest.enrich_cli --refresh
Start in:       <repo root>
```
Run weekly to gradually upgrade Last.fm genres to richer Spotify genres without hammering the rate limit.

---

## Reliability — run the backend and Ollama as services

The dashboard backend and the Ollama server are long-running, so they should run as **auto-restarting Windows services** via [NSSM](https://nssm.cc/) rather than user-session startup applications or fragile Task Scheduler tasks. This ensures they start automatically on system boot (before user login) and restart instantly if they crash.

### 1. Run the Dashboard Backend as a Service
```powershell
# One-time, from an elevated PowerShell:
powershell -ExecutionPolicy Bypass -File scripts\install_dashboard_service.ps1
```
This installs the `ttspot-dashboard` service, disables the old `ttspot-Dashboard` task, and takes over port 8000. `scripts\uninstall_dashboard_service.ps1` reverses it.

### 2. Run Ollama as a Service
```powershell
# One-time, from an elevated PowerShell:
powershell -ExecutionPolicy Bypass -File scripts\install_ollama_service.ps1
```
This installs the `ollama` service, configures it to load your user's pulled models (from `C:\Users\Admin\.ollama\models`), and disables the default user startup shortcut (renamed to `Ollama.lnk.disabled`) to prevent port conflicts when you log in. `scripts\uninstall_ollama_service.ps1` reverses it.

### 3. Register the Watchdog Scheduled Task
To ensure absolute reliability (e.g., if either the Dashboard or Ollama APIs hang or fail to respond despite their service status being "Running"), a watchdog scheduled task is provided:
```powershell
# One-time, from an elevated PowerShell:
powershell -ExecutionPolicy Bypass -File deploy\register_watchdog.ps1
```
This registers the `ttspot-Watchdog` scheduled task running under the `NT AUTHORITY\SYSTEM` account. It checks the health APIs of the Dashboard and Ollama every 10 minutes and restarts their respective services automatically if they become unresponsive. Logs are kept in `data\logs\watchdog.log`.

The periodic jobs (`ttspot-Slideshow` bi-daily, logger) stay as Task Scheduler tasks — those are short-lived and now carry restart-on-failure so a transient error (e.g. a flaky album-art download) self-heals with a retry.


---

## Remote access — deploy the dashboard (Cloudflare Pages + Tunnel)

> **Architecture:** Cloudflare Pages hosts the static React frontend. Generation runs on your home PC. The hosted page reaches the PC through a Cloudflare Tunnel.

### 1. Set up the host PC

```powershell
git clone https://github.com/bryanygan/ttspotslideshow.git
cd ttspotslideshow
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
```

Copy these gitignored files from your dev machine: `.env`, `.spotify_cache`, `data/plays.db`, `data/scrobbles-*.xml`. Verify: `python -m pytest -q`.

Add two Task Scheduler tasks:
- Bi-daily run (see above).
- Startup task (*At startup*, *Run whether user is logged on or not*) running `dashboard_server.py`.

### 2. Deploy the frontend to Cloudflare Pages (one-time)

1. Cloudflare dashboard → **Workers & Pages → Create → Pages → Connect to Git** → select this repo.
2. Build settings:
   - **Framework preset:** Vite
   - **Build command:** `npm run build`
   - **Build output directory:** `dist`
   - **Root directory (Advanced):** `dashboard`
3. Deploy → get `https://<project>.pages.dev`.

### 3. Expose the backend with a Cloudflare Tunnel

```powershell
# Quick (ephemeral, good for testing):
cloudflared tunnel --url http://localhost:8000

# Permanent (needs a Cloudflare-managed domain):
# Create a named tunnel, route recap.yourdomain.com → localhost:8000
# cloudflared service install
```

The server sends `Access-Control-Allow-Origin: *`, so cross-origin calls from `*.pages.dev` work out of the box.

### 4. Connect & secure

- On your `pages.dev` site, paste the tunnel URL into the **Backend API** settings field (saved in localStorage per browser/device).
- **Cloudflare Access** (Zero Trust): add a self-hosted application on the tunnel hostname with a policy allowing only your email (one-time PIN). No code changes needed.

---

## Development

### Run the tests
```powershell
python -m pytest -q
# 147 tests, all offline (network dependency-injected / monkeypatched)
```

### Dashboard dev mode (hot reload)
```powershell
# Terminal 1:
python dashboard_server.py

# Terminal 2:
cd dashboard
npm run dev
# → http://localhost:5173/
```

### Render a demo slide
```powershell
python -m render.render_demo
# Output: output/slides/demo/slide_1.png (1080×1920)
```

---

## Spotify API notes (verified June 2026)

- `recently-played`, top-tracks, artist genres, and album art all work fine.
- `track.popularity` was removed — the underrated score uses personal play-count data from the DB instead.
- **Active Spotify Premium subscription required** or the API stops working.
- Running in **Development Mode** means aggressive rate limiting. Use `--lastfm-only` for bulk genre enrichment and `--refresh` for gradual upgrades.
