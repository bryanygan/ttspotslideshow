# Dashboard v2 — Mobile-First UI Overhaul (two options)

**Date:** 2026-06-25
**Status:** Approved (design)

## Problem

The Phase 5 recap dashboard (`dashboard/src/App.tsx`) is a single 1,119-line
component with a desktop two-column layout. On mobile it collapses into one long,
cluttered scroll: a fat controls panel stacked above a dense candidate table.
It feels hard to navigate and crowded on a phone — the device most likely used
to pick songs and save slides to the camera roll.

## Goal

A complete UI overhaul, **mobile-first** but good on desktop, delivered as **two
distinct design options** the user can run and compare against the **existing
data and backend** before deciding whether to merge. The current `dashboard/`
folder is left untouched as the working version.

## Constraints

- No backend changes. Reuse `dashboard_server.py` (port 8000) and its API:
  - `GET /api/candidates?days=N` → `{ candidates: Candidate[] }`
  - `POST /api/generate` `{ tracks, cover_title, cover_subtitle, cover_theme, watermark }` → `{ summary, slides }`
  - `POST /api/overrides/upload` (raw image body, `X-Artist` / `X-Title` headers) → `{ url }`
  - `GET /api/slides/...`, `GET /api/overrides/...`
- Same stack: React 19 + TypeScript + Tailwind v4 + Vite (mirror existing config).
- **Full feature parity**, reorganized with progressive disclosure (nothing dropped).

## Feature inventory (must all be present in both options)

1. Time-window picker: 3, 7, 14, 30, 90, 180, 365 days.
2. Sort: play count / underrated (plays ÷ popularity).
3. Candidate browse: album art, title, artist, genre bucket, plays, popularity
   bar, underrated score (when sorting underrated), "last featured" badge.
4. Manual album-art upload per track (click cover → file picker → optimistic swap).
5. Multi-select with preserved selection order.
6. Six smart-selection presets: Top Played, Fresh Hits (recent), Artist Vibe,
   Genre Vibe, Underrated, Random Mix — plus target count 4 / 8 / 12 / 16.
7. Selected-tracks tray: reorder (up/down buttons), swap (pick replacement),
   replace-with-random, remove.
8. TikTok cover options: include cover toggle, hook text + 4 presets, subtitle
   (auto-syncs to "Last N Days"), theme select (7 themes), watermark/footer.
9. Recap summary: total candidates, selected count, 4-up slide math + leftover
   warning when not a multiple of 4.
10. Generate → slide gallery with save-to-Photos guidance + host output path.
11. Backend API base config, persisted to localStorage.
12. Loading / empty / error states.

## Architecture

Split logic from presentation so both options are guaranteed feature-identical.

```
dashboard-v2/
├─ src/
│  ├─ lib/
│  │  ├─ types.ts        Candidate + shared types
│  │  ├─ api.ts          fetch wrappers, takes apiBase
│  │  ├─ presets.ts      the 6 selection algorithms as pure functions
│  │  ├─ constants.ts    cover themes, hook presets, window + count options
│  │  └─ useRecap.ts     ONE hook: all state + actions + derived values
│  ├─ ui/                shared primitives: Sheet, AlbumArt, Spinner, Toggle
│  ├─ options/
│  │  ├─ pocket/         Option A — "Pocket DJ"
│  │  └─ console/        Option B — "Console"
│  ├─ App.tsx            A/B toggle (localStorage) + backend-URL settings, wraps useRecap
│  └─ main.tsx
```

`useRecap()` owns: candidates, loading/error, days, sortBy, selectedKeys +
selectedOrder, quickSelectCount, cover state, generating, slideUrls,
successSummary, apiBase — and all actions (toggle, presets, reorder, swap,
random-replace, clear, generate, uploadArt, fetch). Both options render the same
hook instance, so flipping the A/B toggle preserves selections for easy compare.

## Option A — "Pocket DJ" (app-like, thumb-first)

- Bottom tab bar: **Browse · Picks · Create**.
- Browse: 2-col album-art card grid; tap to toggle (checkmark + glow); sticky
  slim top bar with window chip + sort toggle; art upload via card ⋯ menu.
- Floating "N picks ▴" pill opens the Picks tray from any tab.
- Picks: large reorderable rows (up/down), swap, random, remove.
- Create: cover hook + presets, subtitle, theme, watermark, summary, Generate,
  slide gallery.
- Aesthetic: vibrant, album-art-forward, purple→pink gradient accents, glassy
  bars, playful micro-interactions, dark.

## Option B — "Console" (clean, dense, pro)

- Mobile: single crisp scroll; sticky top toolbar (window + sort); compact dense
  rows (checkbox + small art + plays + popularity); **sticky bottom command bar**
  ("N selected — Generate ▸") expanding into a sheet with presets, cover
  settings, and summary.
- Desktop: true two-pane — controls rail + candidate table + selected tray.
- Aesthetic: restrained near-monochrome **zinc** base with a single **electric
  violet** accent; tight type; thin dividers; Linear/Vercel editorial feel.

## Decisions

- Reorder interaction: **up/down buttons** (reliable on touch, no dependency).
- Console accent: **electric violet** (brand continuity, refined).
- Run/compare: **one app, in-app A/B toggle**, persisted to localStorage.

## Run instructions

```
cd dashboard-v2
npm install
npm run dev
```

Open the Vite URL on phone or desktop, use the top A/B toggle, set the backend
field to the running `dashboard_server.py` (default `http://localhost:8000`).

## Out of scope

- Backend/API changes.
- Touching or replacing the existing `dashboard/` (stays the working version).
- Drag-and-drop reorder, new selection algorithms, or new cover themes.
```
