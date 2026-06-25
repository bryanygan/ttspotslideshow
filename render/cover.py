"""Render a premium cover/title slide (1080x1920) for TikTok slideshow posts."""

from PIL import Image, ImageDraw

from render.colors import vertical_gradient
from render.fonts import load_font

SLIDE_W, SLIDE_H = 1080, 1920


def render_cover_slide(title: str, subtitle: str, theme: str = "purple", footer_text: str = None) -> Image.Image:
    """Generate a premium 1080x1920 intro cover slide for TikTok posts."""
    # Define color mappings for various cover slide gradient themes
    themes = {
        "purple": ((88, 28, 135), (15, 23, 42)),      # Deep Purple -> Dark Slate
        "sunset": ((217, 70, 239), (15, 23, 42)),     # Fuchsia -> Dark Slate
        "sunrise": ((234, 88, 12), (15, 23, 42)),     # Orange -> Dark Slate
        "neon": ((219, 39, 119), (15, 23, 42)),       # Pink -> Dark Slate
        "emerald": ((5, 150, 105), (15, 23, 42)),     # Green -> Dark Slate
        "royal": ((29, 78, 216), (15, 23, 42)),       # Blue -> Dark Slate
        "dark": ((17, 24, 39), (3, 7, 18)),           # Charcoal -> Near Black
    }

    # Retrieve colors from mapping, falling back to purple
    theme_colors = themes.get(theme.lower(), themes["purple"])
    top_color, bottom_color = theme_colors

    slide = vertical_gradient((SLIDE_W, SLIDE_H), top_color, bottom_color)
    draw = ImageDraw.Draw(slide)

    # Load fonts
    title_font = load_font("bold", 72)
    sub_font = load_font("medium", 36)
    footer_font = load_font("regular", 24)

    # Draw Title (centered, with simple word wrap)
    words = title.split(" ")
    lines = []
    current_line = []
    max_text_width = SLIDE_W - 160  # 80px margin on each side

    for word in words:
        test_line = " ".join(current_line + [word])
        if title_font.getlength(test_line) <= max_text_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
    if current_line:
        lines.append(" ".join(current_line))

    # Draw lines centered vertically
    title_line_height = 90
    total_title_height = len(lines) * title_line_height
    start_y = (SLIDE_H - total_title_height) // 2 - 50

    for i, line in enumerate(lines):
        line_w = title_font.getlength(line)
        x = (SLIDE_W - line_w) // 2
        y = start_y + i * title_line_height
        draw.text((x, y), line, fill=(255, 255, 255), font=title_font)

    # Draw Subtitle
    if subtitle:
        sub_y = start_y + total_title_height + 30
        sub_w = sub_font.getlength(subtitle)
        sub_x = (SLIDE_W - sub_w) // 2
        draw.text((sub_x, sub_y), subtitle, fill=(209, 213, 219), font=sub_font)

    # Draw decorative bottom footer
    footer = footer_text if footer_text else "🎵 WEEKLY MUSIC RECAP 🎵"
    footer = footer.upper()
    footer_w = footer_font.getlength(footer)
    footer_x = (SLIDE_W - footer_w) // 2
    footer_y = SLIDE_H - 120
    draw.text((footer_x, footer_y), footer, fill=(156, 163, 175), font=footer_font)

    # Draw a small decorative accent line above footer
    line_length = 120
    line_x1 = (SLIDE_W - line_length) // 2
    line_x2 = line_x1 + line_length
    accent_color = (124, 58, 237) if theme.lower() != "dark" else (75, 85, 99)
    draw.line([(line_x1, footer_y - 20), (line_x2, footer_y - 20)], fill=accent_color, width=3)

    return slide
