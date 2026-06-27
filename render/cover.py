"""Render a premium cover/title slide (1080x1920) for TikTok slideshow posts.

The cover is a randomized collage of album covers from the listener's all-time
history, with the hook text (and optional subtitle/footer) overlaid on a tinted
scrim. `render_cover_slide` is kept as a gradient-only fallback for when no art
is available.
"""

from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw

from render.colors import vertical_gradient
from render.fonts import load_font

SLIDE_W, SLIDE_H = 1080, 1920

# Theme -> (top, bottom) tint colors, reused for both the collage scrim and the
# gradient fallback.
THEMES = {
    "purple": ((88, 28, 135), (15, 23, 42)),      # Deep Purple -> Dark Slate
    "sunset": ((217, 70, 239), (15, 23, 42)),     # Fuchsia -> Dark Slate
    "sunrise": ((234, 88, 12), (15, 23, 42)),     # Orange -> Dark Slate
    "neon": ((219, 39, 119), (15, 23, 42)),       # Pink -> Dark Slate
    "emerald": ((5, 150, 105), (15, 23, 42)),     # Green -> Dark Slate
    "royal": ((29, 78, 216), (15, 23, 42)),       # Blue -> Dark Slate
    "dark": ((17, 24, 39), (3, 7, 18)),           # Charcoal -> Near Black
}


def _theme_colors(theme):
    return THEMES.get((theme or "purple").lower(), THEMES["purple"])


def _load_cell(path: Path, target_w: int, target_h: int) -> Optional[Image.Image]:
    """Load image, crop to target cell aspect ratio, and resize to target cell dimensions."""
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            w, h = img.size
            img_aspect = w / h
            target_aspect = target_w / target_h
            if img_aspect > target_aspect:
                # Image is wider than target aspect ratio: crop sides
                new_w = int(h * target_aspect)
                left = (w - new_w) // 2
                img = img.crop((left, 0, left + new_w, h))
            else:
                # Image is taller than target aspect ratio: crop top/bottom
                new_h = int(w / target_aspect)
                top = (h - new_h) // 2
                img = img.crop((0, top, w, top + new_h))
            return img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    except Exception:
        return None


def _build_mosaic(art_paths, columns: int, rows: int, width: int = 1080, height: int = 1920) -> Image.Image:
    """Tile album covers into a full-bleed mosaic.

    Loads each path, center-crops to the tile's aspect ratio, and cycles through
    the valid images if there aren't enough to fill every tile.
    """
    canvas = Image.new("RGB", (width, height), (10, 10, 15))
    w_cell = width // columns
    h_cell = height // rows
    needed = columns * rows

    tiles: list[Image.Image] = []
    attempts = 0
    max_attempts = max(len(art_paths) * 2, needed * 2)
    i = 0
    while len(tiles) < needed and art_paths and attempts < max_attempts:
        path = art_paths[i % len(art_paths)]
        i += 1
        attempts += 1
        tile = _load_cell(path, w_cell, h_cell)
        if tile:
            tiles.append(tile)

    if not tiles:
        return canvas

    from itertools import cycle
    tile_cycle = cycle(tiles)

    for r in range(rows):
        for c in range(columns):
            tile = next(tile_cycle)
            canvas.paste(tile, (c * w_cell, r * h_cell))
    return canvas


def _wrap(text, font, max_width):
    words = text.split(" ")
    lines, current = [], []
    for word in words:
        test = " ".join(current + [word])
        if font.getlength(test) <= max_width or not current:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


def render_cover_collage(
    art_paths,
    title: str,
    subtitle: str = "",
    theme: str = "purple",
    footer_text: str = None,
    columns: int = 5,
    rows: int = 9,
    width: int = 1080,
    height: int = 1920,
) -> Image.Image:
    """Build a cover collage cover with overlaid hook text.

    `art_paths` is a list of local image paths (already downloaded/validated).
    Falls back to a gradient cover when no usable art is supplied.
    """
    art_paths = [p for p in (art_paths or []) if p]
    columns = max(2, min(16, int(columns)))
    rows = max(2, min(25, int(rows)))
    if not art_paths:
        return render_cover_slide(title, subtitle, theme=theme, footer_text=footer_text, width=width, height=height)

    # Mosaic background. Apply theme tint scrim if selected.
    mosaic = _build_mosaic(art_paths, columns, rows, width, height).convert("RGBA")
    if theme and theme.lower() != "none":
        top_color, bottom_color = _theme_colors(theme)
        tint = vertical_gradient((width, height), top_color, bottom_color).convert("RGBA")
        tint.putalpha(150)  # ~59% tint
        base = Image.alpha_composite(mosaic, tint)
    else:
        base = mosaic

    # A soft centered plate behind the hook text guarantees legibility over any
    # underlying covers.
    title_font = load_font("bold", 96)
    sub_font = load_font("medium", 40)
    footer_font = load_font("regular", 28)

    max_text_width = width - 200
    lines = _wrap(title, title_font, max_text_width) if title else []
    title_line_height = 112
    total_title_height = len(lines) * title_line_height
    sub_height = 70 if subtitle else 0
    block_height = total_title_height + sub_height
    start_y = (height - block_height) // 2 - 40

    if lines or subtitle:
        plate = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        pdraw = ImageDraw.Draw(plate)
        widest = max(
            [title_font.getlength(l) for l in lines]
            + ([sub_font.getlength(subtitle)] if subtitle else [0])
        )
        pad_x, pad_y = 70, 60
        plate_w = min(width - 80, int(widest) + pad_x * 2)
        plate_x = (width - plate_w) // 2
        plate_top = start_y - pad_y
        plate_bottom = start_y + block_height + pad_y
        pdraw.rounded_rectangle(
            [plate_x, plate_top, plate_x + plate_w, plate_bottom],
            radius=48,
            fill=(0, 0, 0, 130),
        )
        base = Image.alpha_composite(base, plate)

    slide = base.convert("RGB")
    draw = ImageDraw.Draw(slide)

    # Title (centered) with a soft drop shadow.
    for i, line in enumerate(lines):
        line_w = title_font.getlength(line)
        x = (width - line_w) // 2
        y = start_y + i * title_line_height
        draw.text((x + 3, y + 3), line, fill=(0, 0, 0), font=title_font)
        draw.text((x, y), line, fill=(255, 255, 255), font=title_font)

    if subtitle:
        sub_w = sub_font.getlength(subtitle)
        sub_x = (width - sub_w) // 2
        sub_y = start_y + total_title_height + 14
        draw.text((sub_x, sub_y), subtitle, fill=(228, 228, 235), font=sub_font)

    # Footer + accent line — only if explicitly provided.
    if footer_text:
        footer = footer_text.upper()
        footer_w = footer_font.getlength(footer)
        footer_x = (width - footer_w) // 2
        footer_y = height - 120
        accent = (167, 139, 250) if (theme or "").lower() != "dark" else (148, 163, 184)
        line_len = 120
        draw.line(
            [((width - line_len) // 2, footer_y - 22), ((width + line_len) // 2, footer_y - 22)],
            fill=accent,
            width=3,
        )
        draw.text((footer_x + 2, footer_y + 2), footer, fill=(0, 0, 0), font=footer_font)
        draw.text((footer_x, footer_y), footer, fill=(226, 226, 235), font=footer_font)

    return slide


def render_cover_slide(title: str, subtitle: str, theme: str = "purple", footer_text: str = None,
                       width: int = 1080, height: int = 1920) -> Image.Image:
    """Gradient-only cover slide (fallback when no art is available)."""
    top_color, bottom_color = _theme_colors(theme)

    slide = vertical_gradient((width, height), top_color, bottom_color)
    draw = ImageDraw.Draw(slide)

    title_font = load_font("bold", 72)
    sub_font = load_font("medium", 36)
    footer_font = load_font("regular", 24)

    lines = _wrap(title, title_font, width - 160) if title else []
    title_line_height = 90
    total_title_height = len(lines) * title_line_height
    start_y = (height - total_title_height) // 2 - 50

    for i, line in enumerate(lines):
        line_w = title_font.getlength(line)
        x = (width - line_w) // 2
        y = start_y + i * title_line_height
        draw.text((x, y), line, fill=(255, 255, 255), font=title_font)

    if subtitle:
        sub_y = start_y + total_title_height + 30
        sub_w = sub_font.getlength(subtitle)
        sub_x = (width - sub_w) // 2
        draw.text((sub_x, sub_y), subtitle, fill=(209, 213, 219), font=sub_font)

    # Footer + accent line — only if explicitly provided.
    if footer_text:
        footer = footer_text.upper()
        footer_w = footer_font.getlength(footer)
        footer_x = (width - footer_w) // 2
        footer_y = height - 120
        draw.text((footer_x, footer_y), footer, fill=(156, 163, 175), font=footer_font)

        line_length = 120
        line_x1 = (width - line_length) // 2
        accent_color = (124, 58, 237) if theme.lower() != "dark" else (75, 85, 99)
        draw.line([(line_x1, footer_y - 20), (line_x1 + line_length, footer_y - 20)], fill=accent_color, width=3)

    return slide
