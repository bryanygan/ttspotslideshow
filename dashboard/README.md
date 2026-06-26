# Weekly Recap dashboard

Mobile-first web UI for picking tracks and generating TikTok recap slides. React
+ TypeScript + Tailwind v4 (Vite). Talks to the Python backend
(`dashboard_server.py`) for candidates, slide generation, and album-art overrides.

The UI is the "Pocket DJ" design: app-like with a bottom tab bar.

- **Browse** — album-art grid of candidate tracks; tap to select, tap the image
  icon to replace a cover. Window + plays/underrated sort at the top.
- **Picks** — smart-selection presets (target size + Top Played / Fresh Hits /
  Artist Vibe / Genre Vibe / Underrated / Random) and your ordered picks with
  reorder, swap, random-replace, and remove.
- **Create** — cover options (hook text + presets, subtitle, theme, watermark),
  a live cover preview, the 4-up slide summary, Generate, and the slide gallery
  with save-to-Photos guidance.

The cover/hook slide is a 1080×1920 randomized collage of your all-time album
covers (rendered server-side), with the hook text overlaid.

## Run locally

```
python dashboard_server.py        # backend on http://localhost:8000 (repo root)
cd dashboard && npm install && npm run dev
```

Open the Vite URL. If the backend isn't at the default, set its address via the
⚙ gear → Backend API (saved per-device; key `api_base`).

## Build

```
npm run build      # tsc + vite -> dist/
npm run preview
```

## Deployment

The frontend is hosted on Cloudflare Pages (Vite preset, root `dashboard`,
output `dist`) and rebuilds automatically on push to the repo. The backend runs
on the mini PC and is reached over a Cloudflare Tunnel — see `deploy/DEPLOY.md`.
After backend code changes, pull + restart `dashboard_server.py` on the host.
