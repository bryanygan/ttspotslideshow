from pathlib import Path

from PIL import Image

from render.art import is_placeholder, load_art

DEFAULT = "https://lastfm.example/i/u/300x300/2a96cbd8b46e442fc41c2b86b821562f.png"
REAL = "https://lastfm.example/i/u/300x300/c84fec3cdc323ad174510337fb19c508.jpg"


def test_is_placeholder_detects_default_and_none():
    assert is_placeholder(None) is True
    assert is_placeholder("") is True
    assert is_placeholder(DEFAULT) is True
    assert is_placeholder(REAL) is False


def test_load_art_returns_none_for_placeholder(tmp_path):
    assert load_art(DEFAULT, tmp_path) is None


def test_load_art_downloads_and_caches(tmp_path):
    calls = []

    def fake_fetch(url, dest):
        calls.append(url)
        Image.new("RGB", (10, 10), (255, 0, 0)).save(dest)

    path = load_art(REAL, tmp_path, fetch=fake_fetch)
    assert path is not None and Path(path).exists()
    assert len(calls) == 1

    # Second call must use the cache (no new fetch).
    def boom(url, dest):
        raise AssertionError("should not refetch a cached file")

    again = load_art(REAL, tmp_path, fetch=boom)
    assert Path(again) == Path(path)


def test_load_art_returns_none_on_fetch_failure(tmp_path):
    def failing_fetch(url, dest):
        raise OSError("network down")

    assert load_art(REAL, tmp_path, fetch=failing_fetch) is None
