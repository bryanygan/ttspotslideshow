from slideshow.cli import format_summary


def test_format_summary_full():
    s = {
        "date": "2026-06-24", "days_used": 2, "track_count": 16,
        "slide_count": 4, "genre_spread": {"rage": 6, "trap": 5, "pop": 5},
        "out_dir": "output/slides/2026-06-24",
    }
    text = format_summary(s)
    assert "4 slide" in text
    assert "output/slides/2026-06-24" in text
    assert "rage" in text


def test_format_summary_empty():
    s = {"date": "2026-06-24", "days_used": 30, "track_count": 0,
         "slide_count": 0, "genre_spread": {}, "out_dir": "x"}
    text = format_summary(s)
    assert "No" in text or "nothing" in text.lower()
