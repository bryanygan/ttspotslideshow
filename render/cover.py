"""Render a premium cover/title slide (1080x1920) for TikTok slideshow posts.

The cover is a randomized collage of album covers from the listener's all-time
history, with the hook text (and optional subtitle/footer) overlaid on a tinted
scrim. `render_cover_slide` is kept as a gradient-only fallback for when no art
is available.
"""

from pathlib import Path

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


def _square_crop(img: Image.Image, size: int) -> Image.Image:
    """Center-crop to a square and resize to `size`."""
    img = img.convert("RGB")
    w, h = img.size
    m = min(w, h)
    left = (w - m) // 2
    top = (h - m) // 2
    img = img.crop((left, top, left + m, top + m))
    return img.resize((size, size), Image.Resampling.LANCZOS)


def _build_mosaic(art_paths, columns: int) -> Image.Image:
    """Tile album covers into a full-bleed 1080x1920 mosaic.

    Loads each path, skips any that fail to open, and cycles through the valid
    images if there aren't enough to fill every tile.
    """
    canvas = Image.new("RGB", (SLIDE_W, SLIDE_H), (10, 10, 15))
    tile = SLIDE_W // columns
    rows = (SLIDE_H + tile - 1) // tile
    needed = columns * rows

    tiles: list[Image.Image] = []
    attempts = 0
    max_attempts = max(len(art_paths) * 2, needed * 2)
    i = 0
    while len(tiles) < needed and art_paths and attempts < max_attempts:
        path = art_paths[i % len(art_paths)]
        i += 1
        attempts += 1
        try:
            with Image.open(path) as im:
                tiles.append(_square_crop(im, tile))
        except Exception:
            continue

    if not tiles:
        return canvas

    idx = 0
    for r in range(rows):
        for c in range(columns):
            canvas.paste(tiles[idx % len(tiles)], (c * tile, r * tile))
            idx += 1
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
) -> Image.Image:
    """Build a 1080x1920 album-cover collage cover with overlaid hook text.

    `art_paths` is a list of local image paths (already downloaded/validated).
    Falls back to a gradient cover when no usable art is supplied.
    """
    art_paths = [p for p in (art_paths or []) if p]
    if not art_paths:
        return render_cover_slide(title, subtitle, theme=theme, footer_text=footer_text)

    # Mosaic background. Apply theme tint scrim if selected.
    mosaic = _build_mosaic(art_paths, columns).convert("RGBA")
    if theme and theme.lower() != "none":
        top_color, bottom_color = _theme_colors(theme)
        tint = vertical_gradient((SLIDE_W, SLIDE_H), top_color, bottom_color).convert("RGBA")
        tint.putalpha(150)  # ~59% tint
        base = Image.alpha_composite(mosaic, tint)
    else:
        base = mosaic

    # A soft centered plate behind the hook text guarantees legibility over any
    # underlying covers.
    title_font = load_font("bold", 96)
    sub_font = load_font("medium", 40)
    footer_font = load_font("regular", 28)

    max_text_width = SLIDE_W - 200
    lines = _wrap(title, title_font, max_text_width) if title else []
    title_line_height = 112
    total_title_height = len(lines) * title_line_height
    sub_height = 70 if subtitle else 0
    block_height = total_title_height + sub_height
    start_y = (SLIDE_H - block_height) // 2 - 40

    if lines or subtitle:
        plate = Image.new("RGBA", (SLIDE_W, SLIDE_H), (0, 0, 0, 0))
        pdraw = ImageDraw.Draw(plate)
        widest = max(
            [title_font.getlength(l) for l in lines]
            + ([sub_font.getlength(subtitle)] if subtitle else [0])
        )
        pad_x, pad_y = 70, 60
        plate_w = min(SLIDE_W - 80, int(widest) + pad_x * 2)
        plate_x = (SLIDE_W - plate_w) // 2
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
        x = (SLIDE_W - line_w) // 2
        y = start_y + i * title_line_height
        draw.text((x + 3, y + 3), line, fill=(0, 0, 0), font=title_font)
        draw.text((x, y), line, fill=(255, 255, 255), font=title_font)

    if subtitle:
        sub_w = sub_font.getlength(subtitle)
        sub_x = (SLIDE_W - sub_w) // 2
        sub_y = start_y + total_title_height + 14
        draw.text((sub_x, sub_y), subtitle, fill=(228, 228, 235), font=sub_font)

    # Footer + accent line — only if explicitly provided.
    if footer_text:
        footer = footer_text.upper()
        footer_w = footer_font.getlength(footer)
        footer_x = (SLIDE_W - footer_w) // 2
        footer_y = SLIDE_H - 120
        accent = (167, 139, 250) if (theme or "").lower() != "dark" else (148, 163, 184)
        line_len = 120
        draw.line(
            [((SLIDE_W - line_len) // 2, footer_y - 22), ((SLIDE_W + line_len) // 2, footer_y - 22)],
            fill=accent,
            width=3,
        )
        draw.text((footer_x + 2, footer_y + 2), footer, fill=(0, 0, 0), font=footer_font)
        draw.text((footer_x, footer_y), footer, fill=(226, 226, 235), font=footer_font)

    return slide


def render_cover_slide(title: str, subtitle: str, theme: str = "purple", footer_text: str = None) -> Image.Image:
    """Gradient-only 1080x1920 cover slide (fallback when no art is available)."""
    top_color, bottom_color = _theme_colors(theme)

    slide = vertical_gradient((SLIDE_W, SLIDE_H), top_color, bottom_color)
    draw = ImageDraw.Draw(slide)

    title_font = load_font("bold", 72)
    sub_font = load_font("medium", 36)
    footer_font = load_font("regular", 24)

    lines = _wrap(title, title_font, SLIDE_W - 160) if title else []
    title_line_height = 90
    total_title_height = len(lines) * title_line_height
    start_y = (SLIDE_H - total_title_height) // 2 - 50

    for i, line in enumerate(lines):
        line_w = title_font.getlength(line)
        x = (SLIDE_W - line_w) // 2
        y = start_y + i * title_line_height
        draw.text((x, y), line, fill=(255, 255, 255), font=title_font)

    if subtitle:
        sub_y = start_y + total_title_height + 30
        sub_w = sub_font.getlength(subtitle)
        sub_x = (SLIDE_W - sub_w) // 2
        draw.text((sub_x, sub_y), subtitle, fill=(209, 213, 219), font=sub_font)

    # Footer + accent line — only if explicitly provided.
    if footer_text:
        footer = footer_text.upper()
        footer_w = footer_font.getlength(footer)
        footer_x = (SLIDE_W - footer_w) // 2
        footer_y = SLIDE_H - 120
        draw.text((footer_x, footer_y), footer, fill=(156, 163, 175), font=footer_font)

        line_length = 120
        line_x1 = (SLIDE_W - line_length) // 2
        accent_color = (124, 58, 237) if theme.lower() != "dark" else (75, 85, 99)
        draw.line([(line_x1, footer_y - 20), (line_x1 + line_length, footer_y - 20)], fill=accent_color, width=3)

    return slide
