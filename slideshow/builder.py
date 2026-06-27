"""Orchestrate selection -> art -> render -> collage -> dated slide folder."""

import random
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import db
from slideshow.caption import generate_caption
from slideshow.window import resolve_window
from slideshow.selector import select_tracks
from slideshow.art_resolve import resolve_art_url
from render.art import load_art, find_override_art
from render.card import render_card
from render.collage import collage


class ProgressEmitter:
    """Thread-safe progress callback that emits stage/percent/eta events."""

    def __init__(self, callback=None):
        self._callback = callback
        self._lock = __import__("threading").Lock()
        self._start = time.monotonic()

    def emit(self, stage: str, current: int, total: int, detail: str = ""):
        pct = int((current / total) * 100) if total > 0 else 0
        elapsed = time.monotonic() - self._start
        eta = None
        if pct > 0 and current > 0:
            eta = round(elapsed / current * (total - current), 1)
        if self._callback:
            self._callback({
                "stage": stage,
                "progress": pct,
                "current": current,
                "total": total,
                "eta": eta,
                "detail": detail,
            })


class MissingCoverError(Exception):
    """Raised when one or more tracks are missing album cover art entirely."""
    def __init__(self, missing_tracks):
        self.missing_tracks = missing_tracks
        super().__init__(f"Missing album cover art for {len(missing_tracks)} tracks.")


class UnconfirmedCoverError(Exception):
    """Raised when one or more tracks only have an iTunes fallback cover that needs
    user confirmation before it can be used."""
    def __init__(self, unconfirmed_tracks):
        self.unconfirmed_tracks = unconfirmed_tracks
        super().__init__(f"iTunes cover confirmation required for {len(unconfirmed_tracks)} tracks.")


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


def _dedupe_paths_by_content(paths: list[Path]) -> list[Path]:
    """Return a new list of Paths, deduplicated by the SHA256 hash of their contents."""
    import hashlib
    seen_hashes = set()
    unique_paths = []
    for p in paths:
        if not p.exists():
            continue
        try:
            content_hash = hashlib.sha256(p.read_bytes()).hexdigest()
            if content_hash not in seen_hashes:
                seen_hashes.add(content_hash)
                unique_paths.append(p)
        except Exception:
            unique_paths.append(p)
    return unique_paths


def _collage_art_paths(conn, cache_dir, overrides_dir=None, cap=60, cover_pool=None):
    """Collect up to `cap` local album-art paths.

    If `cover_pool` is provided (list of image URLs), we resolve those.
    Otherwise, we collect from all-time history, shuffled.
    """
    from webutil import is_placeholder
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import hashlib

    if cover_pool:
        # Dedupe by URL so the collage shows distinct covers.
        seen: set[str] = set()
        pool = []
        for url in cover_pool:
            u = (url or "").strip()
            if u and u not in seen:
                seen.add(u)
                pool.append(u)
        random.shuffle(pool)

        local_paths = []
        uncached_urls = []
        for url in pool:
            # Check manual overrides URL representation from frontend
            if url.startswith("/api/overrides/"):
                filename = url.split("/")[-1]
                if overrides_dir:
                    local_path = Path(overrides_dir) / filename
                else:
                    import config
                    local_path = config.ART_OVERRIDES_DIR / filename
                if local_path.exists():
                    local_paths.append(local_path)
                    continue

            if not is_placeholder(url):
                digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
                dest = Path(cache_dir) / f"{digest}.jpg"
                if dest.exists():
                    local_paths.append(dest)
                else:
                    uncached_urls.append(url)

        if len(local_paths) >= cap:
            return local_paths[:cap]

        downloaded_paths = []
        needed = cap - len(local_paths)
        to_download = uncached_urls[:needed + 10]

        if to_download:
            with ThreadPoolExecutor(max_workers=15) as executor:
                future_to_url = {
                    executor.submit(load_art, url, cache_dir): url
                    for url in to_download
                }
                for future in as_completed(future_to_url):
                    try:
                        local = future.result()
                        if local:
                            downloaded_paths.append(local)
                            if len(local_paths) + len(downloaded_paths) >= cap:
                                for f in future_to_url:
                                    f.cancel()
                                break
                    except Exception:
                        pass
        all_paths = local_paths + downloaded_paths
        deduped = _dedupe_paths_by_content(all_paths)
        return deduped[:cap]

    candidates = db.window_track_candidates(conn, 0)  # 0 -> all-time

    # Dedupe by album-art URL so the collage shows distinct covers.
    seen: set[str] = set()
    pool = []
    for c in candidates:
        url = (c.get("album_art_url") or "").strip()
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        pool.append(c)
    random.shuffle(pool)

    local_paths = []
    uncached_urls = []
    for c in pool:
        override = find_override_art(c.get("artist", ""), c.get("title", ""), overrides_dir)
        if override:
            local_paths.append(override)
            continue

        url = c.get("album_art_url")
        if url and not is_placeholder(url):
            digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
            dest = Path(cache_dir) / f"{digest}.jpg"
            if dest.exists():
                local_paths.append(dest)
            else:
                uncached_urls.append(url)

    if len(local_paths) >= cap:
        return local_paths[:cap]

    downloaded_paths = []
    needed = cap - len(local_paths)
    to_download = uncached_urls[:needed + 10]

    if to_download:
        with ThreadPoolExecutor(max_workers=15) as executor:
            future_to_url = {
                executor.submit(load_art, url, cache_dir): url
                for url in to_download
            }
            for future in as_completed(future_to_url):
                try:
                    local = future.result()
                    if local:
                        downloaded_paths.append(local)
                        if len(local_paths) + len(downloaded_paths) >= cap:
                            for f in future_to_url:
                                f.cancel()
                            break
                except Exception:
                    pass
    all_paths = local_paths + downloaded_paths
    deduped = _dedupe_paths_by_content(all_paths)
    return deduped[:cap]


def _render_and_save(conn, rendered, out_dir, featured_date, fetch, cache_dir,
                     overrides_dir=None, cover_title=None, cover_subtitle=None,
                     cover_theme=None, watermark=None, cover_pool=None,
                     progress=None, allow_itunes_covers=False, layout="2x2",
                     cover_only=False, cover_columns=5):
    """Resolve art, render cards, write 4-up slides, and record featured tracks.

    Returns (slide_count, genre_spread). Shared by build_slideshow and
    build_recap_slideshow so the rendering/IO logic lives in one place.
    `featured_date` must be a plain ISO date (the selector parses it with
    date.fromisoformat()), even when out_dir uses a "recap-" prefix.
    """
    from webutil import is_placeholder
    import hashlib

    if cover_only:
        out_dir.mkdir(parents=True, exist_ok=True)
        if progress:
            progress.emit("collage", 0, 1, "Building cover slide (only)…")
        from render.cover import render_cover_collage
        art_paths_collage = _collage_art_paths(conn, cache_dir, overrides_dir, cover_pool=cover_pool)
        cover = render_cover_collage(
            art_paths_collage, cover_title or "", cover_subtitle or "",
            theme=cover_theme, footer_text=watermark, columns=cover_columns
        )
        cover.save(out_dir / "slide_1.png")
        if progress:
            progress.emit("collage", 1, 1, "Cover slide done")
        return 1, {}

    art_cache: dict[str, str] = {}
    resolved_urls = [None] * len(rendered)
    art_paths = [None] * len(rendered)
    to_download = {}  # type: dict[str, list[int]]

    total_tracks = len(rendered)
    if progress:
        progress.emit("resolving", 0, total_tracks, "Resolving cover art…")

    for idx, track in enumerate(rendered):
        override_path = find_override_art(track["artist"], track["title"], overrides_dir)
        if override_path:
            art_paths[idx] = override_path
        else:
            url = resolve_art_url(track, fetch=fetch, cache=art_cache)
            resolved_urls[idx] = url
            if url and not is_placeholder(url):
                digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
                dest = Path(cache_dir) / f"{digest}.jpg"
                if dest.exists():
                    art_paths[idx] = dest
                else:
                    to_download.setdefault(url, []).append(idx)
            else:
                art_paths[idx] = None
        if progress:
            progress.emit("resolving", idx + 1, total_tracks, f"Resolved {idx + 1}/{total_tracks}")

    if to_download:
        from concurrent.futures import ThreadPoolExecutor
        unique_urls = list(to_download.keys())
        downloaded = [0]
        with ThreadPoolExecutor(max_workers=8) as executor:
            from concurrent.futures import as_completed
            future_to_url = {
                executor.submit(load_art, url, cache_dir): url
                for url in unique_urls
            }
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    local_path = future.result()
                except Exception:
                    local_path = None
                for idx in to_download[url]:
                    art_paths[idx] = local_path
                downloaded[0] += 1
                if progress:
                    progress.emit("downloading", downloaded[0], len(unique_urls),
                                  f"Downloaded {downloaded[0]}/{len(unique_urls)} covers")

    # Check for iTunes covers (need user confirmation) and fully missing covers
    from slideshow.art_resolve import _is_itunes_url
    unconfirmed_tracks = []
    missing_tracks = []
    for idx, path in enumerate(art_paths):
        url = resolved_urls[idx]
        if not path:
            missing_tracks.append({
                "artist": rendered[idx].get("artist", "Unknown"),
                "title": rendered[idx].get("title", "Unknown"),
                "track_key": rendered[idx].get("track_key", "")
            })
        elif url and _is_itunes_url(url):
            unconfirmed_tracks.append({
                "artist": rendered[idx].get("artist", "Unknown"),
                "title": rendered[idx].get("title", "Unknown"),
                "track_key": rendered[idx].get("track_key", ""),
                "itunes_url": url,
            })

    # Headless callers (e.g. the Discord /slides bot) can't click "confirm", so
    # they opt into using the iTunes fallback covers as-is.
    if unconfirmed_tracks and not allow_itunes_covers:
        raise UnconfirmedCoverError(unconfirmed_tracks)

    if missing_tracks:
        raise MissingCoverError(missing_tracks)

    # Render cards
    if progress:
        progress.emit("rendering", 0, total_tracks, "Rendering cards…")

    cards = []
    for idx, track in enumerate(rendered):
        cards.append(render_card(track, art_path=art_paths[idx]))
        if progress:
            progress.emit("rendering", idx + 1, total_tracks,
                          f"Rendered card {idx + 1}/{total_tracks}")

    out_dir.mkdir(parents=True, exist_ok=True)
    slide_count = 0
    slide_size = 9 if layout == "3x3" else (16 if layout == "4x4" else 4)
    num_collages = (len(cards) + slide_size - 1) // slide_size + (1 if cover_title is not None else 0)
    collage_done = 0

    # Draw and save the cover slide first if requested.
    if cover_title is not None:
        if progress:
            progress.emit("collage", 0, num_collages, "Building cover slide…")
        from render.cover import render_cover_collage
        art_paths_collage = _collage_art_paths(conn, cache_dir, overrides_dir, cover_pool=cover_pool)
        cover = render_cover_collage(
            art_paths_collage, cover_title, cover_subtitle or "",
            theme=cover_theme, footer_text=watermark, columns=cover_columns
        )
        slide_count += 1
        cover.save(out_dir / f"slide_{slide_count}.png")
        collage_done = 1
        if progress:
            progress.emit("collage", collage_done, num_collages, "Cover slide done")

    for i in range(0, len(cards), slide_size):
        slide_count += 1
        collage_done += 1
        collage(cards[i:i + slide_size], layout=layout, watermark=watermark).save(out_dir / f"slide_{slide_count}.png")
        if progress:
            progress.emit("collage", collage_done, num_collages,
                          f"Slide {slide_count} composed")

    db.record_featured(conn, [t["track_key"] for t in rendered], featured_date)

    spread: dict = {}
    for track in rendered:
        bucket = track.get("primary_bucket", "unknown")
        spread[bucket] = spread.get(bucket, 0) + 1
    return slide_count, spread


def build_slideshow(conn, out_root, target=16, floor=12, now_unix=None,
                    today=None, fetch=None, cache_dir=None, overrides_dir=None,
                    bypass_novelty=False, cover_title=None, cover_subtitle=None,
                    cover_theme=None, watermark=None, playlist_id=None,
                    progress=None, layout="2x2") -> dict:
    """Build the dated slide set. Returns a run summary."""
    run_date = today or date.today().isoformat()
    cache_dir = Path(cache_dir) if cache_dir else (Path("data") / "album_art")
    out_dir = Path(out_root) / run_date

    slide_size = 9 if layout == "3x3" else (16 if layout == "4x4" else 4)

    candidates, days_used = resolve_window(conn, target, floor, now_unix=now_unix)
    featured = {} if bypass_novelty else db.featured_history(conn)
    tracks = select_tracks(candidates, featured, run_date, target, floor)
    dispersed = disperse_tracks(tracks, slide_size=slide_size)

    # Only whole slides are rendered.
    rendered = dispersed[: (len(dispersed) // slide_size) * slide_size]

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

    slide_count, spread = _render_and_save(
        conn, rendered, out_dir, run_date, fetch, cache_dir, overrides_dir=overrides_dir,
        cover_title=cover_title, cover_subtitle=cover_subtitle,
        cover_theme=cover_theme, watermark=watermark, progress=progress, layout=layout
    )
    summary["slide_count"] = slide_count
    summary["genre_spread"] = spread

    # Sync tracks to Spotify playlist (best-effort, non-fatal)
    if playlist_id is not None:
        from slideshow.playlist_sync import sync_playlist
        playlist_url = sync_playlist(conn, rendered, playlist_id=playlist_id)
        if playlist_url:
            summary["playlist_url"] = playlist_url

    return summary


def build_recap_slideshow(conn, out_root, tracks: list[dict], today=None,
                          fetch=None, cache_dir=None, overrides_dir=None,
                          cover_title=None, cover_subtitle=None,
                          cover_theme=None, watermark=None,
                          recap_id=None, cover_pool=None, playlist_id=None,
                          export_video=False, progress=None,
                          allow_itunes_covers=False, layout="2x2",
                          cover_only=False, cover_columns=5) -> dict:
    """Build slides for specific selected tracks. Returns a run summary."""
    run_date = today or date.today().isoformat()
    cache_dir = Path(cache_dir) if cache_dir else (Path("data") / "album_art")

    if not recap_id:
        import time
        import uuid
        unique_suffix = f"{int(time.time())}-{uuid.uuid4().hex[:6]}"
        recap_id = f"recap-{run_date}-{unique_suffix}"

    out_dir = Path(out_root) / recap_id

    slide_size = 9 if layout == "3x3" else (16 if layout == "4x4" else 4)

    dispersed = disperse_tracks(tracks, slide_size=slide_size)
    # We round down to the nearest multiple of slide_size
    rendered = dispersed[: (len(dispersed) // slide_size) * slide_size]

    summary = {
        "date": run_date,
        "track_count": len(rendered) if not cover_only else 0,
        "slide_count": 0,
        "genre_spread": {},
        "out_dir": str(out_dir),
    }
    if not rendered and not cover_only:
        return summary

    # Store the plain ISO run_date (NOT the "recap-" folder name): the selector's
    # novelty check parses last_featured_date with date.fromisoformat(), so a
    # "recap-..." string here would crash the next regular build.
    slide_count, spread = _render_and_save(
        conn, rendered, out_dir, run_date, fetch, cache_dir, overrides_dir=overrides_dir,
        cover_title=cover_title, cover_subtitle=cover_subtitle,
        cover_theme=cover_theme, watermark=watermark, cover_pool=cover_pool,
        progress=progress, allow_itunes_covers=allow_itunes_covers, layout=layout,
        cover_only=cover_only, cover_columns=cover_columns
    )
    summary["slide_count"] = slide_count
    summary["genre_spread"] = spread

    # Sync tracks to Spotify playlist (best-effort, non-fatal)
    if playlist_id is not None:
        from slideshow.playlist_sync import sync_playlist
        playlist_url = sync_playlist(conn, rendered, playlist_id=playlist_id)
        if playlist_url:
            summary["playlist_url"] = playlist_url

    # Export video (best-effort, non-fatal)
    if export_video:
        from render.video_export import export_video
        slide_paths = [out_dir / f"slide_{i}.png" for i in range(1, slide_count + 1)]
        video_path = export_video(slide_paths, out_dir / "recap.mp4")
        if video_path:
            summary["video_path"] = str(video_path)

    # Generate TikTok-ready caption with hashtags
    summary["caption"] = generate_caption(rendered, cover_title=cover_title)

    return summary
