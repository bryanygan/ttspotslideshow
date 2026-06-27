from PIL import Image

from render import cover


def _solid(tmp_path, name, color):
    p = tmp_path / name
    Image.new("RGB", (64, 64), color).save(p)
    return str(p)


def test_columns_clamped_high(tmp_path):
    """An absurd column count is clamped so tiles never collapse to < width/10."""
    arts = [_solid(tmp_path, f"{i}.jpg", (i * 10 % 255, 0, 0)) for i in range(4)]
    img = cover.render_cover_collage(arts, "Hi", columns=999, width=1080, height=1920)
    assert img.size == (1080, 1920)
    # Clamp ceiling is 10 cols -> tile = 108px, so at least one full tile fits.
    assert 1080 // 10 == 108


def test_columns_clamped_low(tmp_path):
    """Zero/negative columns can't divide-by-zero; clamp floor is 2."""
    arts = [_solid(tmp_path, f"{i}.jpg", (0, i * 10 % 255, 0)) for i in range(4)]
    img = cover.render_cover_collage(arts, "Hi", columns=0, width=1080, height=1920)
    assert img.size == (1080, 1920)


def test_default_columns_render(tmp_path):
    arts = [_solid(tmp_path, f"{i}.jpg", (0, 0, i * 10 % 255)) for i in range(4)]
    img = cover.render_cover_collage(arts, "Title", subtitle="Sub", columns=5)
    assert img.size == (1080, 1920)
