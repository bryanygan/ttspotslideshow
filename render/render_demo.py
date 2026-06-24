"""Demo CLI: render sample cards into a 2x2 slide (the visual gate).

Run: python -m render.render_demo
Outputs: output/slides/demo/slide_1.png
"""

from pathlib import Path

from render.art import load_art
from render.card import render_card
from render.collage import collage

# Real sample tracks pulled from the Last.fm export (300x300 art).
_LASTFM_IMG = "https://lastfm.freetls.fastly.net/i/u/300x300"
SAMPLE_TRACKS = [
    {"track_id": "s1", "title": "destroy me", "artist": "2hollis",
     "art_url": f"{_LASTFM_IMG}/c84fec3cdc323ad174510337fb19c508.jpg"},
    {"track_id": "s2", "title": "PRETTY4U", "artist": "Tiffany Day",
     "art_url": f"{_LASTFM_IMG}/6180e2f14ff339d02aab62895e258cc1.jpg"},
    {"track_id": "s3", "title": "Nephew (Feat. Lil Pump)", "artist": "Smokepurpp",
     "art_url": f"{_LASTFM_IMG}/045ebcdd80d83416054dd499ab4d58ef.png"},
    {"track_id": "s4", "title": "Been Ballin", "artist": "Ballout",
     "art_url": f"{_LASTFM_IMG}/c647b47940584cb4a1f4aa0fe753da5b.jpg"},
]


def build_demo_slide(tracks, cache_dir, out_dir) -> Path:
    """Render four tracks into one 2x2 slide PNG and return its path."""
    cards = []
    for track in tracks[:4]:
        art_path = load_art(track.get("art_url"), cache_dir)
        cards.append(render_card(track, art_path=art_path))

    slide = collage(cards)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "slide_1.png"
    slide.save(out_path)
    return out_path


def main() -> None:
    out = build_demo_slide(
        SAMPLE_TRACKS,
        cache_dir=Path("data") / "album_art",
        out_dir=Path("output") / "slides" / "demo",
    )
    print(f"Wrote demo slide -> {out}")


if __name__ == "__main__":
    main()
