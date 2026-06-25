"""Render a single Spotify Now-Playing-style card (540x960)."""

import random
from pathlib import Path

from PIL import Image, ImageDraw

from render.colors import dominant_color, clamp_color, vertical_gradient
from render.fonts import load_font, truncate_to_width

CARD_W, CARD_H = 540, 960
PAD = 32
ART = 476
ART_Y = 130
ART_RADIUS = 14

WHITE = (255, 255, 255, 255)
GRAY = (255, 255, 255, 180)  # 70% opacity white
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
    bottom_color = tuple(max(int(c * 0.45), 14) for c in top_color)
    card = vertical_gradient((CARD_W, CARD_H), top_color, bottom_color).convert("RGB")
    draw = ImageDraw.Draw(card)

    # Album art (or fallback block + music note).
    if art is not None:
        rounded = _rounded(art, ART_RADIUS)
        card.paste(rounded, (PAD, ART_Y), rounded)
    else:
        draw.rounded_rectangle(
            [PAD, ART_Y, PAD + ART, ART_Y + ART], ART_RADIUS, fill=(60, 60, 60)
        )
        # Music-note placeholder drawn with primitives (no font glyph needed).
        note_color = (150, 150, 150)
        cx = PAD + ART / 2
        cy = ART_Y + ART / 2
        head_w, head_h = 90, 70
        head_cx = cx - 15
        head_cy = cy + 70
        draw.ellipse(
            [head_cx - head_w / 2, head_cy - head_h / 2,
             head_cx + head_w / 2, head_cy + head_h / 2],
            fill=note_color,
        )
        stem_x = head_cx + head_w / 2 - 14
        draw.rectangle([stem_x, cy - 120, stem_x + 16, head_cy], fill=note_color)
        draw.polygon(
            [(stem_x + 16, cy - 120), (stem_x + 72, cy - 78), (stem_x + 16, cy - 36)],
            fill=note_color,
        )

    # Create transparent overlay for alpha drawing
    overlay = Image.new("RGBA", card.size, (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)

    # Title + artist fonts
    title_font = load_font("bold", 30)
    artist_font = load_font("medium", 20)
    time_font = load_font("regular", 16)

    # Text wrapping/truncation. Limit width to leave space for the right-hand plus icon.
    text_max_width = 414
    title_text = truncate_to_width(track["title"], title_font, text_max_width)
    artist_text = truncate_to_width(track["artist"], artist_font, text_max_width)

    # Measure text heights
    title_bbox = draw_overlay.textbbox((0, 0), title_text, font=title_font)
    title_h = title_bbox[3] - title_bbox[1]

    artist_bbox = draw_overlay.textbbox((0, 0), artist_text, font=artist_font)
    artist_h = artist_bbox[3] - artist_bbox[1]

    # Layout positioning
    text_y = 698

    # Draw Title
    draw_overlay.text(
        (PAD, text_y), title_text,
        font=title_font, fill=WHITE,
    )

    # Draw Artist
    artist_y = text_y + title_h + 12
    draw_overlay.text(
        (PAD, artist_y), artist_text,
        font=artist_font, fill=GRAY,
    )

    # Calculate text block total height for centering the plus icon
    text_block_h = (artist_y + artist_h) - text_y

    # Plus-in-a-circle icon on the right side of the text block
    icon_size = 38
    icon_x = PAD + ART - icon_size
    icon_y = text_y + (text_block_h - icon_size) // 2

    # Draw outline circle (70% opacity white)
    draw_overlay.ellipse(
        [icon_x, icon_y, icon_x + icon_size, icon_y + icon_size],
        outline=(255, 255, 255, 180),
        width=2,
    )
    # Draw plus sign (2px line width, arms span 8px from center)
    cx, cy = icon_x + 19, icon_y + 19
    arm_len = 8
    plus_w = 2
    draw_overlay.line([(cx - arm_len, cy), (cx + arm_len, cy)], fill=(255, 255, 255, 180), width=plus_w)
    draw_overlay.line([(cx, cy - arm_len), (cx, cy + arm_len)], fill=(255, 255, 255, 180), width=plus_w)

    # Scrubber.
    position, elapsed, total = scrubber_values(track["track_id"])
    bar_y = artist_y + artist_h + 46
    bar_x0, bar_x1 = PAD, PAD + ART
    fill_x = bar_x0 + int(position * ART)

    # Draw track (30% opacity white)
    draw_overlay.rounded_rectangle([bar_x0, bar_y, bar_x1, bar_y + 4], 2, fill=(255, 255, 255, 75))
    # Draw filled progress (100% white)
    draw_overlay.rounded_rectangle([bar_x0, bar_y, fill_x, bar_y + 4], 2, fill=(255, 255, 255, 255))
    # Draw knob (radius 8, centered at (fill_x, bar_y + 2))
    knob_r = 8
    draw_overlay.ellipse(
        [fill_x - knob_r, bar_y + 2 - knob_r, fill_x + knob_r, bar_y + 2 + knob_r],
        fill=WHITE,
    )

    # Times.
    time_y = bar_y + 4 + 14
    draw_overlay.text((bar_x0, time_y), format_time(elapsed), font=time_font, fill=GRAY)
    draw_overlay.text((bar_x1, time_y), format_time(total), font=time_font, fill=GRAY, anchor="ra")

    # Paste the transparent overlay onto the main gradient background
    card.paste(overlay, (0, 0), overlay)

    return card
