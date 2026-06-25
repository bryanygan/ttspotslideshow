"""Composite four cards into a 1080x1920 edge-to-edge 2x2 slide."""

from PIL import Image

from render.card import CARD_W, CARD_H

SLIDE_W, SLIDE_H = 1080, 1920


def collage(cards: list[Image.Image], watermark: str = None) -> Image.Image:
    """Place exactly four cards in a 2x2 grid: [0 1 / 2 3]."""
    if len(cards) != 4:
        raise ValueError(f"collage requires exactly 4 cards, got {len(cards)}")

    slide = Image.new("RGB", (SLIDE_W, SLIDE_H))
    positions = [(0, 0), (CARD_W, 0), (0, CARD_H), (CARD_W, CARD_H)]
    for card, pos in zip(cards, positions):
        if card.size != (CARD_W, CARD_H):
            card = card.resize((CARD_W, CARD_H), resample=Image.LANCZOS)
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
