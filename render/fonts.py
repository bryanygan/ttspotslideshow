"""Montserrat font loading (cached) and text-fit helpers."""

from pathlib import Path

from PIL import ImageFont

FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
FONT_FILES = {
    "bold": "Montserrat-Bold.ttf",
    "medium": "Montserrat-Medium.ttf",
    "regular": "Montserrat-Regular.ttf",
}

_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def load_font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    """Return a cached Montserrat font for the given weight and size."""
    key = (weight, size)
    if key not in _cache:
        _cache[key] = ImageFont.truetype(str(FONT_DIR / FONT_FILES[weight]), size)
    return _cache[key]


def truncate_to_width(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    """Trim text and append '…' until it fits within max_width pixels."""
    if font.getlength(text) <= max_width:
        return text
    ellipsis = "…"
    trimmed = text
    while trimmed and font.getlength(trimmed + ellipsis) > max_width:
        trimmed = trimmed[:-1]
    return trimmed + ellipsis if trimmed else ellipsis
