# Spotify-style Card Renderer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Pillow rendering engine that turns one track into a 540×960 Spotify Now-Playing card and composites four cards into a 1080×1920 TikTok slide.

**Architecture:** Small focused modules under `render/`: `colors` (gradient), `fonts` (typography), `art` (album-art download/cache), `card` (the core pure render function), `collage` (2×2 grid), and a `render_demo` CLI for the visual gate. `render_card` is a pure, offline, deterministic function; the only networked module is `art`.

**Tech Stack:** Python 3.12, Pillow, pytest. Montserrat font (OFL).

## Global Constraints

- Python 3.12; install into the existing `.venv`.
- Pillow is the only new **runtime** dependency; pytest is dev-only.
- Card dimensions: exactly **540×960**. Slide/collage: exactly **1080×1920**.
- Gradient bottom color: `#0E0E0E` = `(14, 14, 14)`.
- Side padding: **48px**. Album art: **444×444**, rounded corner radius **14**.
- Scrubber seeded from `track_id` (reproducible). `position ∈ [0.10, 0.90]`; `total ∈ [135, 270]` seconds; `elapsed = round(position × total)`; times formatted `m:ss`.
- Fonts: Montserrat (OFL), Bold=title, Medium=artist, Regular=times, in `render/assets/fonts/`.
- `render_card` must be pure: no network, no DB, no disk writes; takes a resolved `art_path` (or `None`).
- All git commit messages end with: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

### Task 1: Rendering deps, package scaffold, and fonts

**Files:**
- Modify: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `render/__init__.py`
- Create: `tests/__init__.py`
- Create: `render/assets/fonts/Montserrat-Bold.ttf`, `Montserrat-Medium.ttf`, `Montserrat-Regular.ttf` (downloaded)
- Test: `tests/test_assets.py`

**Interfaces:**
- Consumes: nothing.
- Produces: the `render/` package, installed Pillow/pytest, and the three Montserrat `.ttf` files at `render/assets/fonts/`.

- [ ] **Step 1: Add Pillow to runtime deps**

Append to `requirements.txt`:
```
Pillow==10.4.0
```

- [ ] **Step 2: Create dev deps file**

Create `requirements-dev.txt`:
```
pytest==8.3.2
```

- [ ] **Step 3: Install dependencies**

Run: `.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt`
Expected: installs Pillow and pytest, "Successfully installed ...".

- [ ] **Step 4: Create package files**

Create empty `render/__init__.py` and empty `tests/__init__.py`.

- [ ] **Step 5: Download Montserrat fonts**

Run (creates the folder and downloads three weights from the official Montserrat repo, OFL-licensed):
```bash
mkdir -p render/assets/fonts
base="https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf"
curl -L -o render/assets/fonts/Montserrat-Bold.ttf    "$base/Montserrat-Bold.ttf"
curl -L -o render/assets/fonts/Montserrat-Medium.ttf  "$base/Montserrat-Medium.ttf"
curl -L -o render/assets/fonts/Montserrat-Regular.ttf "$base/Montserrat-Regular.ttf"
```
Expected: three `.ttf` files, each > 100 KB.

- [ ] **Step 6: Write the failing test**

Create `tests/test_assets.py`:
```python
from pathlib import Path

from PIL import ImageFont

FONT_DIR = Path(__file__).resolve().parent.parent / "render" / "assets" / "fonts"


def test_montserrat_fonts_present_and_loadable():
    for name in ("Montserrat-Bold.ttf", "Montserrat-Medium.ttf",
                 "Montserrat-Regular.ttf"):
        path = FONT_DIR / name
        assert path.exists(), f"missing font: {path}"
        # PIL must be able to load it at a real size.
        font = ImageFont.truetype(str(path), 36)
        assert font.getlength("test") > 0
```

- [ ] **Step 7: Run the test**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_assets.py -v`
Expected: PASS (fonts present and loadable).

- [ ] **Step 8: Commit**

```bash
git add requirements.txt requirements-dev.txt render/__init__.py tests/__init__.py tests/test_assets.py render/assets/fonts/
git commit -m "feat(render): add Pillow/pytest deps, package scaffold, Montserrat fonts

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Color extraction and gradient (`render/colors.py`)

**Files:**
- Create: `render/colors.py`
- Test: `tests/test_colors.py`

**Interfaces:**
- Consumes: Pillow `Image`.
- Produces:
  - `dominant_color(img: Image.Image) -> tuple[int, int, int]`
  - `clamp_color(rgb: tuple[int, int, int], min_lum: int = 50, min_sat: float = 0.20) -> tuple[int, int, int]`
  - `vertical_gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int] = (14, 14, 14)) -> Image.Image`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_colors.py`:
```python
from PIL import Image

from render.colors import dominant_color, clamp_color, vertical_gradient


def test_dominant_color_of_solid_red():
    img = Image.new("RGB", (64, 64), (255, 0, 0))
    r, g, b = dominant_color(img)
    assert r > 200 and g < 55 and b < 55


def test_clamp_color_lifts_black_off_zero():
    r, g, b = clamp_color((0, 0, 0))
    assert r + g + b > 60  # no longer pure black


def test_clamp_color_leaves_bright_color_mostly_alone():
    out = clamp_color((230, 40, 90))
    assert out[0] > 150  # still clearly the same bright hue


def test_vertical_gradient_top_and_bottom():
    grad = vertical_gradient((10, 100), (200, 100, 50))
    assert grad.size == (10, 100)
    top = grad.getpixel((5, 0))
    bottom = grad.getpixel((5, 99))
    assert abs(top[0] - 200) <= 4 and abs(top[1] - 100) <= 4
    assert abs(bottom[0] - 14) <= 4 and abs(bottom[2] - 14) <= 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_colors.py -v`
Expected: FAIL with "No module named 'render.colors'".

- [ ] **Step 3: Implement `render/colors.py`**

```python
"""Dominant-color extraction and vertical gradient generation."""

import colorsys

from PIL import Image


def dominant_color(img: Image.Image) -> tuple[int, int, int]:
    """Return the most common color of an image via median-cut quantization."""
    small = img.convert("RGB").resize((64, 64))
    quantized = small.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
    palette = quantized.getpalette()
    # getcolors() -> list of (count, palette_index); pick the most frequent.
    count, index = sorted(quantized.getcolors(), reverse=True)[0]
    r, g, b = palette[index * 3: index * 3 + 3]
    return (r, g, b)


def clamp_color(
    rgb: tuple[int, int, int],
    min_lum: int = 50,
    min_sat: float = 0.20,
) -> tuple[int, int, int]:
    """Lift a color to a minimum brightness/saturation so gradients stay visible."""
    r, g, b = (c / 255 for c in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    s = max(s, min_sat)
    v = max(v, min_lum / 255)
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return tuple(int(round(c * 255)) for c in (r, g, b))


def vertical_gradient(
    size: tuple[int, int],
    top: tuple[int, int, int],
    bottom: tuple[int, int, int] = (14, 14, 14),
) -> Image.Image:
    """Build a top->bottom linear gradient image of the given size."""
    width, height = size
    column = Image.new("RGB", (1, height))
    for y in range(height):
        t = y / (height - 1) if height > 1 else 0
        color = tuple(int(round(top[i] * (1 - t) + bottom[i] * t)) for i in range(3))
        column.putpixel((0, y), color)
    return column.resize((width, height))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_colors.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add render/colors.py tests/test_colors.py
git commit -m "feat(render): color extraction and vertical gradient

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Font loading and text truncation (`render/fonts.py`)

**Files:**
- Create: `render/fonts.py`
- Test: `tests/test_fonts.py`

**Interfaces:**
- Consumes: the `.ttf` files from Task 1.
- Produces:
  - `load_font(weight: str, size: int) -> ImageFont.FreeTypeFont` (weight in `{"bold", "medium", "regular"}`)
  - `truncate_to_width(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fonts.py`:
```python
from render.fonts import load_font, truncate_to_width


def test_load_font_returns_usable_font():
    font = load_font("bold", 36)
    assert font.getlength("hello") > 0


def test_load_font_is_cached():
    assert load_font("regular", 24) is load_font("regular", 24)


def test_short_text_is_unchanged():
    font = load_font("regular", 24)
    assert truncate_to_width("Hi", font, 500) == "Hi"


def test_long_text_is_truncated_with_ellipsis_and_fits():
    font = load_font("regular", 24)
    long_text = "supercalifragilistic " * 10
    result = truncate_to_width(long_text, font, 200)
    assert result.endswith("…")
    assert font.getlength(result) <= 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_fonts.py -v`
Expected: FAIL with "No module named 'render.fonts'".

- [ ] **Step 3: Implement `render/fonts.py`**

```python
"""Montserrat font loading (cached) and text-fit helpers."""

from pathlib import Path

from PIL import ImageFont

FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
FONT_FILES = {
    "bold": "Montserrat-Bold.ttf",
    "medium": "Montserrat-Medium.ttf",
    "regular": "Montserrat-Regular.ttf",
}

_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def load_font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    """Return a cached Montserrat font for the given weight and size."""
    key = (weight, size)
    if key not in _cache:
        _cache[key] = ImageFont.truetype(str(FONT_DIR / FONT_FILES[weight]), size)
    return _cache[key]


def truncate_to_width(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    """Trim text and append '…' until it fits within max_width pixels."""
    if font.getlength(text) <= max_width:
        return text
    ellipsis = "…"
    trimmed = text
    while trimmed and font.getlength(trimmed + ellipsis) > max_width:
        trimmed = trimmed[:-1]
    return trimmed + ellipsis if trimmed else ellipsis
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_fonts.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add render/fonts.py tests/test_fonts.py
git commit -m "feat(render): cached font loading and text truncation

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Album-art download and cache (`render/art.py`)

**Files:**
- Create: `render/art.py`
- Test: `tests/test_art.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `is_placeholder(url: str | None) -> bool`
  - `load_art(art_url: str | None, cache_dir, fetch=None) -> Path | None` — returns a local cached file path, or `None` for placeholder/missing/failed. `fetch` is an injectable `(url, dest_path) -> None` downloader (defaults to a real urllib download).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_art.py`:
```python
from pathlib import Path

from PIL import Image

from render.art import is_placeholder, load_art

DEFAULT = "https://lastfm.example/i/u/300x300/2a96cbd8b46e442fc41c2b86b821562f.png"
REAL = "https://lastfm.example/i/u/300x300/c84fec3cdc323ad174510337fb19c508.jpg"


def test_is_placeholder_detects_default_and_none():
    assert is_placeholder(None) is True
    assert is_placeholder("") is True
    assert is_placeholder(DEFAULT) is True
    assert is_placeholder(REAL) is False


def test_load_art_returns_none_for_placeholder(tmp_path):
    assert load_art(DEFAULT, tmp_path) is None


def test_load_art_downloads_and_caches(tmp_path):
    calls = []

    def fake_fetch(url, dest):
        calls.append(url)
        Image.new("RGB", (10, 10), (255, 0, 0)).save(dest)

    path = load_art(REAL, tmp_path, fetch=fake_fetch)
    assert path is not None and Path(path).exists()
    assert len(calls) == 1

    # Second call must use the cache (no new fetch).
    def boom(url, dest):
        raise AssertionError("should not refetch a cached file")

    again = load_art(REAL, tmp_path, fetch=boom)
    assert Path(again) == Path(path)


def test_load_art_returns_none_on_fetch_failure(tmp_path):
    def failing_fetch(url, dest):
        raise OSError("network down")

    assert load_art(REAL, tmp_path, fetch=failing_fetch) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_art.py -v`
Expected: FAIL with "No module named 'render.art'".

- [ ] **Step 3: Implement `render/art.py`**

```python
"""Album-art download with a local on-disk cache."""

import hashlib
import urllib.request
from pathlib import Path
from typing import Callable, Optional

# Last.fm serves this hash as its gray-star "no image" placeholder.
DEFAULT_ART_HASH = "2a96cbd8b46e442fc41c2b86b821562f"


def is_placeholder(url: Optional[str]) -> bool:
    """True if the URL is empty/None or the Last.fm default placeholder image."""
    return not url or DEFAULT_ART_HASH in url


def _default_fetch(url: str, dest: Path) -> None:
    urllib.request.urlretrieve(url, dest)


def load_art(
    art_url: Optional[str],
    cache_dir,
    fetch: Optional[Callable[[str, Path], None]] = None,
) -> Optional[Path]:
    """Download art_url into cache_dir (once) and return the local path.

    Returns None for placeholder/missing URLs or if the download fails.
    """
    if is_placeholder(art_url):
        return None

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(art_url.encode("utf-8")).hexdigest()
    dest = cache_dir / f"{digest}.jpg"

    if dest.exists():
        return dest

    fetcher = fetch or _default_fetch
    try:
        fetcher(art_url, dest)
    except Exception:
        if dest.exists():
            dest.unlink(missing_ok=True)
        return None

    return dest if dest.exists() else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_art.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add render/art.py tests/test_art.py
git commit -m "feat(render): album-art download with on-disk cache

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: The card renderer (`render/card.py`)

**Files:**
- Create: `render/card.py`
- Test: `tests/test_card.py`

**Interfaces:**
- Consumes: `render.colors.dominant_color`, `clamp_color`, `vertical_gradient`; `render.fonts.load_font`, `truncate_to_width`.
- Produces:
  - constants `CARD_W = 540`, `CARD_H = 960`
  - `format_time(seconds: int) -> str`
  - `scrubber_values(track_id: str) -> tuple[float, int, int]` returning `(position, elapsed_s, total_s)`
  - `render_card(track: dict, art_path=None) -> Image.Image` where `track` has keys `track_id`, `title`, `artist`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_card.py`:
```python
from PIL import Image

from render.card import CARD_W, CARD_H, format_time, scrubber_values, render_card


def _sample_art(tmp_path):
    p = tmp_path / "art.jpg"
    Image.new("RGB", (300, 300), (180, 40, 60)).save(p)
    return p


def test_format_time():
    assert format_time(5) == "0:05"
    assert format_time(107) == "1:47"
    assert format_time(225) == "3:45"


def test_scrubber_values_are_deterministic_per_track():
    a = scrubber_values("track-xyz")
    b = scrubber_values("track-xyz")
    assert a == b


def test_scrubber_values_in_range():
    position, elapsed, total = scrubber_values("track-xyz")
    assert 0.10 <= position <= 0.90
    assert 135 <= total <= 270
    assert elapsed == round(position * total)


def test_render_card_size_and_nonblank(tmp_path):
    track = {"track_id": "t1", "title": "Destroy Me", "artist": "2hollis"}
    img = render_card(track, art_path=_sample_art(tmp_path))
    assert img.size == (CARD_W, CARD_H)
    assert img.mode == "RGB"
    lo, hi = img.convert("L").getextrema()
    assert lo != hi  # not a blank, single-tone image


def test_render_card_fallback_without_art():
    track = {"track_id": "t2", "title": "No Art Song", "artist": "Someone"}
    img = render_card(track, art_path=None)
    assert img.size == (CARD_W, CARD_H)


def test_render_card_handles_long_text(tmp_path):
    track = {
        "track_id": "t3",
        "title": "An Extremely Long Song Title That Will Not Fit " * 2,
        "artist": "An Artist With A Very Long Name Indeed " * 2,
    }
    img = render_card(track, art_path=_sample_art(tmp_path))
    assert img.size == (CARD_W, CARD_H)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_card.py -v`
Expected: FAIL with "No module named 'render.card'".

- [ ] **Step 3: Implement `render/card.py`**

```python
"""Render a single Spotify Now-Playing-style card (540x960)."""

import random
from pathlib import Path

from PIL import Image, ImageDraw

from render.colors import dominant_color, clamp_color, vertical_gradient
from render.fonts import load_font, truncate_to_width

CARD_W, CARD_H = 540, 960
PAD = 48
ART = 444
ART_Y = 130
ART_RADIUS = 14

WHITE = (255, 255, 255)
GRAY = (179, 179, 179)
TRACK_GRAY = (90, 90, 90)
FALLBACK_TOP = (40, 40, 40)


def format_time(seconds: int) -> str:
    """Format seconds as m:ss."""
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}:{secs:02d}"


def scrubber_values(track_id: str) -> tuple[float, int, int]:
    """Deterministic (position, elapsed_s, total_s) seeded by track_id."""
    rng = random.Random(track_id)
    position = rng.uniform(0.10, 0.90)
    total = rng.randint(135, 270)
    elapsed = round(position * total)
    return position, elapsed, total


def _rounded(img: Image.Image, radius: int) -> Image.Image:
    """Return an RGBA copy of img with rounded corners."""
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, img.size[0] - 1, img.size[1] - 1], radius, fill=255
    )
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def render_card(track: dict, art_path=None) -> Image.Image:
    """Render one card. track needs keys: track_id, title, artist."""
    art = None
    if art_path is not None:
        try:
            art = Image.open(Path(art_path)).convert("RGB").resize((ART, ART))
        except Exception:
            art = None

    top_color = clamp_color(dominant_color(art)) if art is not None else FALLBACK_TOP
    card = vertical_gradient((CARD_W, CARD_H), top_color).convert("RGB")
    draw = ImageDraw.Draw(card)

    # Album art (or fallback block + music note).
    if art is not None:
        rounded = _rounded(art, ART_RADIUS)
        card.paste(rounded, (PAD, ART_Y), rounded)
    else:
        draw.rounded_rectangle(
            [PAD, ART_Y, PAD + ART, ART_Y + ART], ART_RADIUS, fill=(60, 60, 60)
        )
        note_font = load_font("bold", 180)
        draw.text(
            (PAD + ART / 2, ART_Y + ART / 2), "♪",
            font=note_font, fill=(150, 150, 150), anchor="mm",
        )

    # Title + artist.
    title_font = load_font("bold", 36)
    artist_font = load_font("medium", 24)
    draw.text(
        (PAD, 618), truncate_to_width(track["title"], title_font, ART),
        font=title_font, fill=WHITE,
    )
    draw.text(
        (PAD, 664), truncate_to_width(track["artist"], artist_font, ART),
        font=artist_font, fill=GRAY,
    )

    # Scrubber.
    position, elapsed, total = scrubber_values(track["track_id"])
    bar_y = 742
    bar_x0, bar_x1 = PAD, PAD + ART
    fill_x = bar_x0 + int(position * ART)
    draw.rounded_rectangle([bar_x0, bar_y, bar_x1, bar_y + 4], 2, fill=TRACK_GRAY)
    draw.rounded_rectangle([bar_x0, bar_y, fill_x, bar_y + 4], 2, fill=WHITE)
    knob_r = 7
    draw.ellipse(
        [fill_x - knob_r, bar_y + 2 - knob_r, fill_x + knob_r, bar_y + 2 + knob_r],
        fill=WHITE,
    )

    # Times.
    time_font = load_font("regular", 18)
    draw.text((bar_x0, 762), format_time(elapsed), font=time_font, fill=GRAY)
    draw.text((bar_x1, 762), format_time(total), font=time_font, fill=GRAY, anchor="ra")

    return card
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_card.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add render/card.py tests/test_card.py
git commit -m "feat(render): single Now-Playing card renderer

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: The 2×2 collage (`render/collage.py`)

**Files:**
- Create: `render/collage.py`
- Test: `tests/test_collage.py`

**Interfaces:**
- Consumes: `render.card.CARD_W`, `CARD_H`.
- Produces:
  - constants `SLIDE_W = 1080`, `SLIDE_H = 1920`
  - `collage(cards: list[Image.Image]) -> Image.Image` — requires exactly 4 cards, placed `[0 1 / 2 3]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_collage.py`:
```python
import pytest
from PIL import Image

from render.card import CARD_W, CARD_H
from render.collage import SLIDE_W, SLIDE_H, collage


def _solid(color):
    return Image.new("RGB", (CARD_W, CARD_H), color)


def test_collage_size():
    cards = [_solid(c) for c in [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)]]
    slide = collage(cards)
    assert slide.size == (SLIDE_W, SLIDE_H)
    assert slide.mode == "RGB"


def test_collage_quadrant_placement():
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)]
    slide = collage([_solid(c) for c in colors])
    # Centers of each quadrant should match the card placed there.
    assert slide.getpixel((CARD_W // 2, CARD_H // 2)) == colors[0]            # top-left
    assert slide.getpixel((CARD_W + CARD_W // 2, CARD_H // 2)) == colors[1]   # top-right
    assert slide.getpixel((CARD_W // 2, CARD_H + CARD_H // 2)) == colors[2]   # bottom-left
    assert slide.getpixel((CARD_W + CARD_W // 2, CARD_H + CARD_H // 2)) == colors[3]


def test_collage_requires_four_cards():
    with pytest.raises(ValueError):
        collage([_solid((0, 0, 0))])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_collage.py -v`
Expected: FAIL with "No module named 'render.collage'".

- [ ] **Step 3: Implement `render/collage.py`**

```python
"""Composite four cards into a 1080x1920 edge-to-edge 2x2 slide."""

from PIL import Image

from render.card import CARD_W, CARD_H

SLIDE_W, SLIDE_H = 1080, 1920


def collage(cards: list[Image.Image]) -> Image.Image:
    """Place exactly four cards in a 2x2 grid: [0 1 / 2 3]."""
    if len(cards) != 4:
        raise ValueError(f"collage requires exactly 4 cards, got {len(cards)}")

    slide = Image.new("RGB", (SLIDE_W, SLIDE_H))
    positions = [(0, 0), (CARD_W, 0), (0, CARD_H), (CARD_W, CARD_H)]
    for card, pos in zip(cards, positions):
        if card.size != (CARD_W, CARD_H):
            card = card.resize((CARD_W, CARD_H))
        slide.paste(card, pos)
    return slide
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_collage.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add render/collage.py tests/test_collage.py
git commit -m "feat(render): 2x2 collage compositor

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Demo CLI and visual gate (`render/render_demo.py`)

**Files:**
- Create: `render/render_demo.py`
- Test: `tests/test_render_demo.py`

**Interfaces:**
- Consumes: `render.art.load_art`, `render.card.render_card`, `render.collage.collage`.
- Produces: `build_demo_slide(tracks, cache_dir, out_dir) -> Path` (renders four cards into one slide PNG, returns its path) and a `main()` entry point with hard-coded real sample tracks from the Last.fm data.

- [ ] **Step 1: Write the failing test**

Create `tests/test_render_demo.py` (offline: monkeypatches the downloader so no network is needed):
```python
from pathlib import Path

from PIL import Image

import render.art as art
from render.render_demo import build_demo_slide


def test_build_demo_slide_writes_a_slide(tmp_path, monkeypatch):
    def fake_fetch(url, dest):
        Image.new("RGB", (300, 300), (120, 60, 200)).save(dest)

    monkeypatch.setattr(art, "_default_fetch", fake_fetch)

    tracks = [
        {"track_id": f"t{i}", "title": f"Song {i}", "artist": f"Artist {i}",
         "art_url": f"https://lastfm.example/i/u/300x300/cover{i}.jpg"}
        for i in range(4)
    ]
    out = build_demo_slide(tracks, cache_dir=tmp_path / "art", out_dir=tmp_path / "out")
    assert Path(out).exists()
    img = Image.open(out)
    assert img.size == (1080, 1920)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_render_demo.py -v`
Expected: FAIL with "No module named 'render.render_demo'".

- [ ] **Step 3: Implement `render/render_demo.py`**

```python
"""Demo CLI: render sample cards into a 2x2 slide (the visual gate).

Run: python -m render.render_demo
Outputs: output/slides/demo/slide_1.png
"""

from pathlib import Path

from render.art import load_art
from render.card import render_card
from render.collage import collage

# Real sample tracks pulled from the Last.fm export (300x300 art).
_LASTFM_IMG = "https://lastfm.freetls.fastly.net/i/u/300x300"
SAMPLE_TRACKS = [
    {"track_id": "s1", "title": "destroy me", "artist": "2hollis",
     "art_url": f"{_LASTFM_IMG}/c84fec3cdc323ad174510337fb19c508.jpg"},
    {"track_id": "s2", "title": "PRETTY4U", "artist": "Tiffany Day",
     "art_url": f"{_LASTFM_IMG}/6180e2f14ff339d02aab62895e258cc1.jpg"},
    {"track_id": "s3", "title": "Nephew (Feat. Lil Pump)", "artist": "Smokepurpp",
     "art_url": f"{_LASTFM_IMG}/045ebcdd80d83416054dd499ab4d58ef.png"},
    {"track_id": "s4", "title": "Been Ballin", "artist": "Ballout",
     "art_url": f"{_LASTFM_IMG}/c647b47940584cb4a1f4aa0fe753da5b.jpg"},
]


def build_demo_slide(tracks, cache_dir, out_dir) -> Path:
    """Render four tracks into one 2x2 slide PNG and return its path."""
    cards = []
    for track in tracks[:4]:
        art_path = load_art(track.get("art_url"), cache_dir)
        cards.append(render_card(track, art_path=art_path))

    slide = collage(cards)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "slide_1.png"
    slide.save(out_path)
    return out_path


def main() -> None:
    out = build_demo_slide(
        SAMPLE_TRACKS,
        cache_dir=Path("data") / "album_art",
        out_dir=Path("output") / "slides" / "demo",
    )
    print(f"Wrote demo slide -> {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_render_demo.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Run the full suite**

Run: `.\.venv\Scripts\python.exe -m pytest -v`
Expected: all tests PASS.

- [ ] **Step 6: Generate the real demo slide (visual gate)**

Run: `.\.venv\Scripts\python.exe -m render.render_demo`
Expected: prints `Wrote demo slide -> output\slides\demo\slide_1.png`. Open the PNG and review the look (this is the human visual-quality checkpoint).

- [ ] **Step 7: Commit**

```bash
git add render/render_demo.py tests/test_render_demo.py
git commit -m "feat(render): demo CLI rendering a 2x2 sample slide

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- §4 modules `colors`/`fonts`/`art`/`card`/`collage`/`render_demo` → Tasks 2/3/4/5/6/7. ✓
- §5 gradient + seeded scrubber + Montserrat + truncation + minimal chrome → Tasks 2, 3, 5. ✓
- §6 collage 1080×1920 edge-to-edge `[0 1 / 2 3]` → Task 6. ✓
- §7 error handling: missing/placeholder art fallback (Task 5 fallback + Task 4 `is_placeholder`/`load_art` → None), dark-color clamp (Task 2 `clamp_color`), long-text truncation (Task 3 + Task 5 long-text test). ✓
- §8 testing: colors/card/collage/fonts unit tests + visual gate → Tasks 2–7, Task 7 Step 6. ✓
- §9 Pillow-only runtime dep, Montserrat bundled → Task 1. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases" — every code step contains complete code. ✓

**Type consistency:** `dominant_color`/`clamp_color`/`vertical_gradient` (Task 2) used identically in Task 5; `load_font`/`truncate_to_width` (Task 3) used identically in Task 5; `load_art` signature (Task 4) matches Task 7 usage; `CARD_W`/`CARD_H` (Task 5) imported in Task 6; `render_card`/`collage`/`load_art` consumed consistently in Task 7. ✓

No gaps found.
