# Spotify-style Song-Card Renderer — Design Spec

**Date:** 2026-06-23
**Phase:** 2 (the renderer — "the meat")
**Status:** Approved design, pending implementation plan

---

## 1. Purpose

Build the rendering engine that turns a single track's data into a Spotify
Now-Playing-style card image, and composites four of them into a 1080×1920
TikTok slide. This is the shared foundation for both the bi-daily slideshow
generator and the weekly recap.

The success criterion for this phase is **one pixel-good card**, then a clean
2×2 collage — not the full automated pipeline.

---

## 2. Scope

### In scope (Phase 2)
- Dominant-color extraction + gradient generation (`colors`).
- Font loading + text-fit/truncation helpers (`fonts`).
- Album-art download/caching helper (`art`).
- `render_card(track) -> 540×960 image` (`card`) — the core unit.
- `collage(cards) -> 1080×1920 slide` (`collage`) — edge-to-edge 2×2.
- A small `render_demo.py` CLI to render sample cards + a sample collage.

### Out of scope (deferred)
- **Track selection** (querying the DB for the bi-daily window, dedup across
  genres, chunking into groups of 4) → **Phase 3**.
- Genre enrichment of the Last.fm data → separate data task.
- Hi-res album art sourcing beyond a simple loader → enhancement (see §7).
- Posting to TikTok → manual, never automated (per project constraints).

For Phase 2, the renderer is fed **sample / hand-picked tracks** (real rows
pulled from the Last.fm export).

---

## 3. Data inputs

The renderer operates on a minimal `Track` dict (source-agnostic — works for
Last.fm or Spotify rows):

```python
{
    "track_id": str,    # stable id; seeds the random scrubber for reproducibility
    "title":    str,    # song title
    "artist":   str,    # primary artist name
    "art_url":  str,    # album art URL (Last.fm 300px now; hi-res later) or None
}
```

Data availability (from the Last.fm export, verified 2026-06-23):
- 107,890 timestamped scrobbles, 2020-08-14 → 2026-06-24.
- 15,470 unique tracks, 3,809 unique artists.
- 102,279 scrobbles have real album art (300×300); 6,151 use the Last.fm
  gray-star placeholder → must hit the fallback path.
- No genre, no track duration, no popularity in the export.

---

## 4. Architecture & module boundaries

```
render/
├── colors.py     # dominant-color extraction + vertical gradient
├── fonts.py      # Montserrat loading/caching; truncate-to-width helper
├── art.py        # album-art download + local cache (data/album_art/<hash>.jpg)
├── card.py       # render_card(track) -> 540×960 PIL.Image   (CORE UNIT)
├── collage.py    # four cards -> 1080×1920 slide (edge-to-edge 2×2)
├── render_demo.py# CLI: render sample cards + a sample collage to output/
└── assets/fonts/ # Montserrat .ttf files (tracked in git, OFL license)
```

**Principles:**
- `render_card` is a **pure function**: takes a `Track` + a resolved local art
  path → returns an image. No DB knowledge, no network, no disk writes.
- `colors`, `fonts`, `art` are independent helpers, each testable in isolation.
- `collage` only knows how to place four finished images in the grid; it does
  not know how a card is drawn.
- Album-art download lives in `art.py` (the only networked module), keeping
  `card.py` deterministic and offline-testable.

---

## 5. Card layout (540 × 960)

```
┌───────────────────────────┐  gradient: dominant color (top) → #0E0E0E (bottom)
│   ┌───────────────────┐   │  y=130
│   │    album art      │   │  art: 444×444, x=48, rounded corners r≈14
│   │     444×444       │   │
│   └───────────────────┘   │  y=574
│   Song Title              │  y=618  Montserrat Bold ~36, #FFFFFF, 1 line + …
│   Artist Name             │  y=664  Montserrat Medium ~24, #B3B3B3, 1 line + …
│   ──────●────────────     │  y=742  bar 444 wide, 4px rounded;
│   1:47            3:58     │  y=762  filled=white, track=white@28%, knob r≈7
└───────────────────────────┘         times: Montserrat ~18, #B3B3B3
```

- 48px side padding throughout; the art+text+scrubber stack is vertically
  balanced within the 960px height.
- All numeric values above are starting targets; final pixel values are tuned
  against rendered samples during implementation (the "one perfect card" pass).

### Gradient
1. Quantize the album art to extract a dominant color.
2. Clamp it to a minimum brightness/saturation so dark or grayscale art never
   collapses the gradient to flat black.
3. Vertical linear blend from the (clamped) dominant color at the top to
   `#0E0E0E` at the bottom.

### Scrubber (seeded random)
- RNG seeded from `track_id` → **the same track always renders the same
  position** (reproducible across runs, no flicker).
- `position ∈ [0.10, 0.90]`.
- `total ∈ [135s, 270s]` (2:15–4:30); `elapsed = round(position × total)`.
- Both rendered `m:ss`, so the knob position and the numbers always agree.

### Typography
- **Montserrat** (Google Fonts, OFL — free to bundle/redistribute), downloaded
  into `render/assets/fonts/`. Bold = title; Medium = artist + times.
- Title and artist each render on **one line, ellipsized** to fit 444px.
- Chosen as the geometric-sans substitute for Spotify's Circular (not
  licensable). Alternatives if proportions feel off: Mulish, Figtree.

### Chrome
- Minimal by design: album art, title, artist, scrubber + times only.
- No play/skip controls, no "PLAYING FROM" header. A subtle play glyph can be
  added later if a card reads as empty.

---

## 6. Collage (1080 × 1920)

- Edge-to-edge 2×2 grid; each cell exactly 540×960, no gutters.
- `collage(cards: list[Image]) -> Image` places indices 0–3 as:
  `[0 1 / 2 3]` (top-left, top-right, bottom-left, bottom-right).
- Output saved to `output/slides/<YYYY-MM-DD>/slide_<n>.png` by the demo/driver
  (the collage function itself returns an image; saving is the caller's job).

---

## 7. Error handling

| Case | Behavior |
|------|----------|
| Missing/placeholder art, or download fails | Fallback card: neutral dark-gray gradient + centered music-note glyph. Card still valid 540×960. |
| Dark / grayscale album art | Dominant color clamped to min brightness/saturation; gradient stays visible. |
| Very long title/artist | Ellipsized to fit 444px width. |
| Non-Latin / emoji glyphs Montserrat lacks | v1 renders Montserrat's missing-glyph box. Adding a Noto Sans fallback font is a later enhancement, not v1. |
| Album-art download (network) | `art.py` caches to `data/album_art/<hash>.jpg`; re-renders are offline. Failures route to the fallback card. |

---

## 8. Testing

**Automated (regression safety):**
- `colors`: dominant color of a solid-red image ≈ red; gradient top row ≈
  dominant color, bottom row ≈ `#0E0E0E`.
- `card`: output is exactly 540×960, mode RGB, non-blank (pixel variance > 0);
  seeded scrubber yields an identical position across two renders of the same
  `track_id`.
- `collage`: output 1080×1920; each quadrant's center pixel originates from the
  correct card (corner-placement check).
- `fonts`: a very long string truncates to contain `…` and fits within 444px.

**Visual gate (the real quality check):**
- Render actual sample cards from the Last.fm data and review them together.
  Automated tests catch regressions; eyes catch ugliness.

---

## 9. Dependencies

- **Pillow** — the only new runtime dependency for rendering (chosen over an
  HTML/headless-browser or SVG approach: lowest dependency cost, full pixel
  control, matches the project's committed stack).
- **Montserrat .ttf** font files committed under `render/assets/fonts/`.

---

## 10. Open items / future enhancements

- Hi-res album art: upgrade final renders from Last.fm 300px to iTunes Search
  API (600px+, no auth) or Spotify (640px).
- Noto Sans fallback for non-Latin/emoji glyph coverage.
- Optional subtle play glyph if minimal cards feel sparse.
- Genre enrichment (Spotify artist lookup vs Last.fm tags) — needed by Phase 3
  selection, not by the renderer.
