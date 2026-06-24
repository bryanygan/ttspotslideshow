from pathlib import Path

from PIL import Image

import render.art as art
from render.render_demo import build_demo_slide


def test_build_demo_slide_writes_a_slide(tmp_path, monkeypatch):
    def fake_fetch(url, dest):
        Image.new("RGB", (300, 300), (120, 60, 200)).save(dest)

    monkeypatch.setattr(art, "_default_fetch", fake_fetch)

    tracks = [
        {"track_id": f"t{i}", "title": f"Song {i}", "artist": f"Artist {i}",
         "art_url": f"https://lastfm.example/i/u/300x300/cover{i}.jpg"}
        for i in range(4)
    ]
    out = build_demo_slide(tracks, cache_dir=tmp_path / "art", out_dir=tmp_path / "out")
    assert Path(out).exists()
    img = Image.open(out)
    assert img.size == (1080, 1920)
