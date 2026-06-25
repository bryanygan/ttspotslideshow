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


def test_collage_rejects_more_than_four_cards():
    with pytest.raises(ValueError):
        collage([_solid((0, 0, 0)) for _ in range(5)])
