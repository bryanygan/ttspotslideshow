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


def test_collage_3x3_size():
    cards = [_solid((10, 20, 30)) for _ in range(9)]
    slide = collage(cards, layout="3x3")
    assert slide.size == (SLIDE_W, SLIDE_H)
    assert slide.mode == "RGB"
    assert slide.getpixel((180, 283)) == (10, 20, 30)


def test_collage_4x4_size():
    cards = [_solid((40, 50, 60)) for _ in range(16)]
    slide = collage(cards, layout="4x4")
    assert slide.size == (SLIDE_W, SLIDE_H)
    assert slide.mode == "RGB"
    assert slide.getpixel((135, 212)) == (40, 50, 60)


def test_collage_invalid_count_3x3():
    with pytest.raises(ValueError):
        collage([_solid((0, 0, 0)) for _ in range(8)], layout="3x3")

