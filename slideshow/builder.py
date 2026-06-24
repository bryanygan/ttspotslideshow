"""Orchestrate selection -> art -> render -> collage -> dated slide folder."""

from datetime import date
from pathlib import Path

import db
from slideshow.window import resolve_window
from slideshow.selector import select_tracks
from slideshow.art_resolve import resolve_art_url
from render.art import load_art
from render.card import render_card
from render.collage import collage


def build_slideshow(conn, out_root, target=16, floor=12, now_unix=None,
                    today=None, fetch=None, cache_dir=None) -> dict:
    """Build the dated slide set. Returns a run summary."""
    run_date = today or date.today().isoformat()
    cache_dir = Path(cache_dir) if cache_dir else (Path("data") / "album_art")
    out_dir = Path(out_root) / run_date

    candidates, days_used = resolve_window(conn, target, floor, now_unix=now_unix)
    featured = db.featured_history(conn)
    tracks = select_tracks(candidates, featured, run_date, target, floor)

    # Only whole 4-card slides are rendered.
    rendered = tracks[: (len(tracks) // 4) * 4]

    summary = {
        "date": run_date,
        "days_used": days_used,
        "track_count": len(rendered),
        "slide_count": 0,
        "genre_spread": {},
        "out_dir": str(out_dir),
    }
    if not rendered:
        return summary

    art_cache: dict = {}
    cards = []
    for track in rendered:
        url = resolve_art_url(track, fetch=fetch, cache=art_cache)
        art_path = load_art(url, cache_dir)
        cards.append(render_card(track, art_path=art_path))

    out_dir.mkdir(parents=True, exist_ok=True)
    slide_count = 0
    for i in range(0, len(cards), 4):
        slide_count += 1
        collage(cards[i:i + 4]).save(out_dir / f"slide_{slide_count}.png")

    db.record_featured(conn, [t["track_key"] for t in rendered], run_date)

    spread: dict = {}
    for track in rendered:
        spread[track["primary_bucket"]] = spread.get(track["primary_bucket"], 0) + 1
    summary["slide_count"] = slide_count
    summary["genre_spread"] = spread
    return summary
