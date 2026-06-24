"""Dominant-color extraction and vertical gradient generation."""

import colorsys

from PIL import Image


def dominant_color(img: Image.Image) -> tuple[int, int, int]:
    """Return the most common color of an image via median-cut quantization."""
    small = img.convert("RGB").resize((64, 64))
    quantized = small.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
    palette = quantized.getpalette()
    # getcolors() -> list of (count, palette_index); pick the most frequent.
    count, index = sorted(quantized.getcolors(), reverse=True)[0]
    r, g, b = palette[index * 3: index * 3 + 3]
    return (r, g, b)


def clamp_color(
    rgb: tuple[int, int, int],
    min_lum: int = 50,
    min_sat: float = 0.20,
) -> tuple[int, int, int]:
    """Lift a color to a minimum brightness/saturation so gradients stay visible."""
    r, g, b = (c / 255 for c in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    s = max(s, min_sat)
    v = max(v, min_lum / 255)
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return tuple(int(round(c * 255)) for c in (r, g, b))


def vertical_gradient(
    size: tuple[int, int],
    top: tuple[int, int, int],
    bottom: tuple[int, int, int] = (14, 14, 14),
) -> Image.Image:
    """Build a top->bottom linear gradient image of the given size."""
    width, height = size
    column = Image.new("RGB", (1, height))
    for y in range(height):
        t = y / (height - 1) if height > 1 else 0
        color = tuple(int(round(top[i] * (1 - t) + bottom[i] * t)) for i in range(3))
        column.putpixel((0, y), color)
    return column.resize((width, height))
