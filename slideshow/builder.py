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


def disperse_tracks(
    tracks: list[dict],
    slide_size: int = 4,
    max_artist: int = 1,
    max_album: int = 1,
) -> list[dict]:
    """Reorder tracks so that no slide contains more than max_artist from the same artist
    and no more than max_album from the same album (using album_art_url as proxy).
    """
    num_slides = len(tracks) // slide_size
    if num_slides <= 1:
        return tracks

    slides: list[list[dict]] = [[] for _ in range(num_slides)]
    remaining = list(tracks)

    for slot in range(slide_size):
        for s_idx in range(num_slides):
            if not remaining:
                break
            slide = slides[s_idx]

            # Find the first track that violates neither constraint
            best_idx = -1
            for i, track in enumerate(remaining):
                artist = track.get("artist")
                art_url = track.get("album_art_url")

                artist_count = sum(1 for t in slide if t.get("artist") == artist)
                album_count = sum(
                    1
                    for t in slide
                    if t.get("album_art_url") == art_url and art_url
                )

                if artist_count < max_artist and album_count < max_album:
                    best_idx = i
                    break

            # If no track satisfies both, try to satisfy only the artist constraint
            if best_idx == -1:
                for i, track in enumerate(remaining):
                    artist = track.get("artist")
                    artist_count = sum(
                        1 for t in slide if t.get("artist") == artist
                    )
                    if artist_count < max_artist:
                        best_idx = i
                        break

            # If still nothing, just take the first remaining track
            if best_idx == -1:
                best_idx = 0

            slide.append(remaining.pop(best_idx))

    flat = []
    for s in slides:
        flat.extend(s)
    flat.extend(remaining)
    return flat


def build_slideshow(conn, out_root, target=16, floor=12, now_unix=None,
                    today=None, fetch=None, cache_dir=None) -> dict:
    """Build the dated slide set. Returns a run summary."""
    run_date = today or date.today().isoformat()
    cache_dir = Path(cache_dir) if cache_dir else (Path("data") / "album_art")
    out_dir = Path(out_root) / run_date

    candidates, days_used = resolve_window(conn, target, floor, now_unix=now_unix)
    featured = db.featured_history(conn)
    tracks = select_tracks(candidates, featured, run_date, target, floor)
    dispersed = disperse_tracks(tracks)

    # Only whole 4-card slides are rendered.
    rendered = dispersed[: (len(dispersed) // 4) * 4]

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

    art_cache: dict[str, str] = {}
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


def build_recap_slideshow(conn, out_root, tracks: list[dict], today=None,
                          fetch=None, cache_dir=None) -> dict:
    """Build slides for specific selected tracks. Returns a run summary."""
    from datetime import date
    from render.card import render_card
    from render.collage import collage
    from render.art import load_art
    from slideshow.art_resolve import resolve_art_url

    run_date = today or date.today().isoformat()
    cache_dir = Path(cache_dir) if cache_dir else (Path("data") / "album_art")
    out_dir = Path(out_root) / f"recap-{run_date}"

    dispersed = disperse_tracks(tracks)
    # We round down to the nearest multiple of 4, since slides are 4-up.
    rendered = dispersed[: (len(dispersed) // 4) * 4]

    summary = {
        "date": run_date,
        "track_count": len(rendered),
        "slide_count": 0,
        "genre_spread": {},
        "out_dir": str(out_dir),
    }
    if not rendered:
        return summary

    art_cache: dict[str, str] = {}
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

    db.record_featured(conn, [t["track_key"] for t in rendered], f"recap-{run_date}")

    spread: dict = {}
    for track in rendered:
        bucket = track.get("primary_bucket", "unknown")
        spread[bucket] = spread.get(bucket, 0) + 1

    summary["slide_count"] = slide_count
    summary["genre_spread"] = spread
    return summary
