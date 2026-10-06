# Mini-PC deployment quickstart

Condensed checklist. Full explanation is in the root `README.md` →
"Remote access — deploy the dashboard".

```
iPhone ─► Cloudflare Pages (static dashboard) ─► Cloudflare Tunnel (HTTPS) ─► mini PC :8000
```
The mini PC does all the work; Cloudflare Pages is just the remote control.

## 1. Project onto the mini PC
1. Install **Python 3.12** (add to PATH) and **Git**.
2. ```powershell
   git clone https://github.com/bryanygan/ttspotslideshow.git
   cd ttspotslideshow
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt -r requirements-dev.txt
   ```
3. **Copy these gitignored files** from your dev PC into the same paths:
   `.env`, `.spotify_cache`, `data\plays.db`, `data\scrobbles-*.xml` (and optionally
   `data\album_art\`). Without `.spotify_cache`, run `python logger.py --auth` once.
4. Verify: `python -m pytest -q` (expect all pass) and
   `python run_bidaily.py --skip-spotify --skip-lastfm` (should write slides).

## 2. Scheduled tasks (automation)
Run once in an **elevated** PowerShell from the repo root:
```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\register_tasks.ps1
```
Registers: bi-daily slideshow, 3-hourly Spotify logger, and weekly genre refresh. (The dashboard backend and Ollama run as auto-restarting Windows Services via NSSM, and are monitored by the watchdog task registered via `.\deploy\register_watchdog.ps1` — see README).


## 3. Cloudflare Pages (frontend)
Workers & Pages → Create → Pages → Connect to Git → this repo. Build settings:
- Framework preset: **Vite** · Build command: `npm run build` · Output dir: `dist`
- **Root directory: `dashboard`** · (if Node error) env var `NODE_VERSION=20`

Deploy → `https://<project>.pages.dev`.

## 4. Cloudflare Tunnel + Access (connect & secure)
- **Easiest:** Zero Trust → Networks → Tunnels → Create → Cloudflared → run the install
  command on the mini PC (installs a service). Add Public Hostname
  `api.yourdomain.com` → `http://localhost:8000`.
  (CLI alternative: see `cloudflared-config.example.yml`.)
- **Secure it:** Zero Trust → Access → Applications → Self-hosted on
  `api.yourdomain.com`, policy = allow your email only.

## 5. Use it (iPhone)
Open the `pages.dev` site → paste `https://api.yourdomain.com` into the **Backend API**
field → generate → **long-press a slide → Add to Photos**.
