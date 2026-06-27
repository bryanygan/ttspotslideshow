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


def collage(cards: list[Image.Image], layout: str = "2x2", watermark: str = None,
            width: int = 1080, height: int = 1700) -> Image.Image:
    """Place cards in a grid layout (2x2, 3x3, or 4x4) and paste them on the canvas."""
    if layout not in LAYOUT_CONFIGS:
        raise ValueError(f"Unsupported layout: {layout}")

    cfg = LAYOUT_CONFIGS[layout]
    expected_count = cfg["count"]
    if len(cards) != expected_count:
        raise ValueError(f"collage layout {layout} requires exactly {expected_count} cards, got {len(cards)}")

    slide = Image.new("RGB", (width, height))
    cols = 3 if layout == "3x3" else (4 if layout == "4x4" else 2)
    rows = cols
    
    card_w = width // cols
    card_h = height // rows

    positions = []
    for r in range(rows):
        for c in range(cols):
            positions.append((c * card_w, r * card_h))

    for card, pos in zip(cards, positions):
        # Scale proportionally and center card in its slot to prevent distortion
        card_aspect = card.width / card.height
        slot_aspect = card_w / card_h
        if card_aspect > slot_aspect:
            new_w = card_w
            new_h = int(card_w / card_aspect)
        else:
            new_h = card_h
            new_w = int(card_h * card_aspect)

        if card.size != (new_w, new_h):
            card = card.resize((new_w, new_h), resample=Image.LANCZOS)

        dx = (card_w - new_w) // 2
        dy = (card_h - new_h) // 2
        slide.paste(card, (pos[0] + dx, pos[1] + dy))

    if watermark:
        from PIL import ImageDraw
        from render.fonts import load_font
        overlay = Image.new("RGBA", slide.size, (0, 0, 0, 0))
        draw_overlay = ImageDraw.Draw(overlay)
        font = load_font("medium", 24)
        text = watermark.upper()
        w = font.getlength(text)
        x = (width - w) // 2
        y = height - 60
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
