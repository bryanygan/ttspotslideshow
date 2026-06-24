from PIL import Image

from render.card import CARD_W, CARD_H, format_time, scrubber_values, render_card


def _sample_art(tmp_path):
    p = tmp_path / "art.jpg"
    Image.new("RGB", (300, 300), (180, 40, 60)).save(p)
    return p


def test_format_time():
    assert format_time(5) == "0:05"
    assert format_time(107) == "1:47"
    assert format_time(225) == "3:45"


def test_scrubber_values_are_deterministic_per_track():
    a = scrubber_values("track-xyz")
    b = scrubber_values("track-xyz")
    assert a == b


def test_scrubber_values_in_range():
    position, elapsed, total = scrubber_values("track-xyz")
    assert 0.10 <= position <= 0.90
    assert 135 <= total <= 270
    assert elapsed == round(position * total)


def test_render_card_size_and_nonblank(tmp_path):
    track = {"track_id": "t1", "title": "Destroy Me", "artist": "2hollis"}
    img = render_card(track, art_path=_sample_art(tmp_path))
    assert img.size == (CARD_W, CARD_H)
    assert img.mode == "RGB"
    lo, hi = img.convert("L").getextrema()
    assert lo != hi  # not a blank, single-tone image


def test_render_card_fallback_without_art():
    track = {"track_id": "t2", "title": "No Art Song", "artist": "Someone"}
    img = render_card(track, art_path=None)
    assert img.size == (CARD_W, CARD_H)


def test_render_card_handles_long_text(tmp_path):
    track = {
        "track_id": "t3",
        "title": "An Extremely Long Song Title That Will Not Fit " * 2,
        "artist": "An Artist With A Very Long Name Indeed " * 2,
    }
    img = render_card(track, art_path=_sample_art(tmp_path))
    assert img.size == (CARD_W, CARD_H)
