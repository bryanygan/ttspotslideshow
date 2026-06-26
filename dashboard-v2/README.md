# Recap Studio — dashboard v2 (mobile-first overhaul)

A from-scratch, **mobile-first** rebuild of the Phase 5 recap dashboard, shipped
as **two switchable design options** so you can run both against your real data
and pick a direction before merging anything. The existing `dashboard/` is left
untouched.

Flip between the two with the **A · Pocket / B · Console** toggle in the top bar.
Your selections carry over when you switch, so it's a true side-by-side compare.

- **A — Pocket DJ:** app-like and thumb-first. Bottom tabs (Browse / Picks /
  Create), an album-art-forward grid, a floating "picks" pill, and a live cover
  preview on the Create tab. Vibrant violet→fuchsia.
- **B — Console:** dense and minimal. A data-first list with monospaced metrics,
  a two-pane desktop layout, and a persistent CLI-style command bar on mobile
  that opens a composer sheet. Zinc + electric violet.

Both options have **full feature parity** with the original: time windows,
plays/underrated sort, manual cover-art upload, multi-select with ordering, the
six smart-selection presets + target count, swap/random/remove, TikTok cover
options (hook + presets, subtitle, theme, watermark), 4-up slide math, generate,
and the slide gallery with save-to-Photos guidance.

## Run it

This UI is just a frontend — it talks to the **existing Python backend**, which
serves your real logged data.

1. **Start the backend** (from the repo root), if it isn't already running:

   ```
   python dashboard_server.py
   ```

   It listens on `http://localhost:8000` and has CORS enabled.

2. **Start this dashboard** (in a second terminal):

   ```
   cd dashboard-v2
   npm install
   npm run dev
   ```

   Vite serves on `http://localhost:5174` (it won't collide with the old
   dashboard on 5173 or the backend on 8000).

3. Open the URL on your desktop or phone. If the backend isn't at the default,
   set its address via the **⚙ gear → Backend API** field (saved on the device).

### Viewing on your phone

Run the backend and `npm run dev` on the mini PC / your computer, then open
`http://<that-computer-LAN-IP>:5174` on your phone (same Wi-Fi). Set the Backend
API field to `http://<that-computer-LAN-IP>:8000`.

## How it's built

Logic and presentation are split so both options are guaranteed feature-identical:

```
src/
├─ lib/        types, api, presets (selection algorithms), constants, useRecap()
├─ ui/         shared primitives + content blocks (cover form, presets, tray, gallery)
├─ options/
│  ├─ pocket/  Option A
│  └─ console/ Option B
└─ App.tsx     A/B toggle + backend settings; owns the single useRecap() instance
```

`useRecap()` holds all state and actions; each option is pure presentation over
it. When you pick a winner, that option can ship on its own and the comparison
bar in `App.tsx` goes away.

## Build for production

```
npm run build      # type-checks then bundles to dist/
npm run preview
```
