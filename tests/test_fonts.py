from render.fonts import load_font, truncate_to_width


def test_load_font_returns_usable_font():
    font = load_font("bold", 36)
    assert font.getlength("hello") > 0


def test_load_font_is_cached():
    assert load_font("regular", 24) is load_font("regular", 24)


def test_short_text_is_unchanged():
    font = load_font("regular", 24)
    assert truncate_to_width("Hi", font, 500) == "Hi"


def test_long_text_is_truncated_with_ellipsis_and_fits():
    font = load_font("regular", 24)
    long_text = "supercalifragilistic " * 10
    result = truncate_to_width(long_text, font, 200)
    assert result.endswith("…")
    assert font.getlength(result) <= 200
