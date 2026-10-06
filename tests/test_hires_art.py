from pathlib import Path

from PIL import Image

from render.art import load_art
from render.export import preview_paths, save_slide, write_previews
from webutil import DEFAULT_ART_HASH, hires_art_url


def test_hires_rewrites_lastfm_sizes():
    for size in ("300x300", "174s", "64s"):
        url = f"https://lastfm.freetls.fastly.net/i/u/{size}/abc.jpg"
        assert hires_art_url(url) == "https://lastfm.freetls.fastly.net/i/u/770x0/abc.jpg"


def test_hires_leaves_other_urls_alone():
    for url in ("https://i.scdn.co/image/abc", "", None,
                f"https://lastfm.freetls.fastly.net/i/u/300x300/{DEFAULT_ART_HASH}.png"):
        assert hires_art_url(url) == url


def test_load_art_falls_back_to_300px_when_hires_fails(tmp_path):
    tried = []

    def fetch(url, dest):
        tried.append(url)
        if "770x0" in url:
            raise OSError("not found")
        dest.write_bytes(b"jpg")

    out = load_art("https://lastfm.freetls.fastly.net/i/u/770x0/abc.jpg", tmp_path, fetch)
    assert out is not None and out.exists()
    assert tried == [
        "https://lastfm.freetls.fastly.net/i/u/770x0/abc.jpg",
        "https://lastfm.freetls.fastly.net/i/u/300x300/abc.jpg",
    ]


def test_save_slide_writes_png_preview_and_thumb(tmp_path):
    png = tmp_path / "slide_1.png"
    save_slide(Image.new("RGB", (1080, 1700), "red"), png)
    preview, thumb = preview_paths(png)

    assert Image.open(png).size == (1080, 1700)
    assert Image.open(preview).format == "WEBP" and Image.open(preview).size == (1080, 1700)
    assert Image.open(thumb).format == "WEBP" and Image.open(thumb).size[0] == 540
    assert not list(tmp_path.glob("*.tmp"))


def test_write_previews_handles_rgba(tmp_path):
    png = tmp_path / "slide_2.png"
    write_previews(Image.new("RGBA", (200, 300)), png)
    assert Path(preview_paths(png)[0]).exists()
