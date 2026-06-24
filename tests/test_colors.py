from PIL import Image

from render.colors import dominant_color, clamp_color, vertical_gradient


def test_dominant_color_of_solid_red():
    img = Image.new("RGB", (64, 64), (255, 0, 0))
    r, g, b = dominant_color(img)
    assert r > 200 and g < 55 and b < 55


def test_clamp_color_lifts_black_off_zero():
    r, g, b = clamp_color((0, 0, 0))
    assert r + g + b > 60  # no longer pure black


def test_clamp_color_leaves_bright_color_mostly_alone():
    out = clamp_color((230, 40, 90))
    assert out[0] > 150  # still clearly the same bright hue


def test_vertical_gradient_top_and_bottom():
    grad = vertical_gradient((10, 100), (200, 100, 50))
    assert grad.size == (10, 100)
    top = grad.getpixel((5, 0))
    bottom = grad.getpixel((5, 99))
    assert abs(top[0] - 200) <= 4 and abs(top[1] - 100) <= 4
    assert abs(bottom[0] - 14) <= 4 and abs(bottom[2] - 14) <= 4
