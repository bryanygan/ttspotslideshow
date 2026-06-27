"""Composite cards into a 1080x1700 edge-to-edge slide."""

from PIL import Image

SLIDE_W, SLIDE_H = 1080, 1700

LAYOUT_CONFIGS = {
    "2x2": {
        "count": 4,
        "card_size": (540, 850),
        "positions": [
            (0, 0), (540, 0),
            (0, 850), (540, 850)
        ]
    },
    "3x3": {
        "count": 9,
        "card_size": (360, 566),
        "positions": [
            (0, 0), (360, 0), (720, 0),
            (0, 566), (360, 566), (720, 566),
            (0, 1132), (360, 1132), (720, 1132)
        ]
    },
    "4x4": {
        "count": 16,
        "card_size": (270, 425),
        "positions": [
            (0, 0), (270, 0), (540, 0), (810, 0),
            (0, 425), (270, 425), (540, 425), (810, 425),
            (0, 850), (270, 850), (540, 850), (810, 850),
            (0, 1275), (270, 1275), (540, 1275), (810, 1275)
        ]
    }
}


def collage(cards: list[Image.Image], layout: str = "2x2", watermark: str = None) -> Image.Image:
    """Place cards in a grid layout (2x2, 3x3, or 4x4) and paste them on the canvas."""
    if layout not in LAYOUT_CONFIGS:
        raise ValueError(f"Unsupported layout: {layout}")

    cfg = LAYOUT_CONFIGS[layout]
    expected_count = cfg["count"]
    if len(cards) != expected_count:
        raise ValueError(f"collage layout {layout} requires exactly {expected_count} cards, got {len(cards)}")

    slide = Image.new("RGB", (SLIDE_W, SLIDE_H))
    card_w, card_h = cfg["card_size"]
    positions = cfg["positions"]

    for card, pos in zip(cards, positions):
        if card.size != (card_w, card_h):
            card = card.resize((card_w, card_h), resample=Image.LANCZOS)
        slide.paste(card, pos)

    if watermark:
        from PIL import ImageDraw
        from render.fonts import load_font
        overlay = Image.new("RGBA", slide.size, (0, 0, 0, 0))
        draw_overlay = ImageDraw.Draw(overlay)
        font = load_font("medium", 24)
        text = watermark.upper()
        w = font.getlength(text)
        x = (SLIDE_W - w) // 2
        y = SLIDE_H - 60
        padding_h = 16
        padding_v = 8
        # Draw a semi-transparent black pill behind the watermark to ensure readability on any background
        draw_overlay.rounded_rectangle(
            [x - padding_h, y - padding_v, x + w + padding_h, y + font.size + padding_v],
            radius=12,
            fill=(0, 0, 0, 140)
        )
        draw_overlay.text((x, y), text, fill=(255, 255, 255, 220), font=font)
        slide.paste(overlay, (0, 0), overlay)

    return slide
