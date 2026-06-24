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
