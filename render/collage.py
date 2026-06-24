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
