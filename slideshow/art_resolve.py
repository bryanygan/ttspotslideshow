"""Resolve hi-res album art via the iTunes Search API, with Last.fm fallback."""

from typing import Callable, Optional

from text_norm import normalize
from webutil import itunes_search


def search_spotify_art(artist: str, title: str) -> Optional[str]:
    """Search Spotify Web API for the track cover art."""
    try:
        from spotify_client import get_client
        sp = get_client()
        query = f"track:{title} artist:{artist}"
        # Execute search
        results = sp.search(q=query, type="track", limit=1)
        tracks = results.get("tracks", {}).get("items", [])
        if tracks:
            images = tracks[0].get("album", {}).get("images", [])
            if images:
                # First one is highest resolution (usually 640x640)
                return images[0].get("url")
    except (Exception, SystemExit):
        # Gracefully handle lack of credentials or connection issues during tests/runs
        pass
    return None


def resolve_art_url(track, fetch: Optional[Callable[[str], str]] = None,
                    cache: Optional[dict] = None) -> str:
    """Best album-art URL for a track: stored URL if present, else Spotify, else iTunes search fallback."""
    key = normalize(track["artist"]) + "\t" + normalize(track["title"])
    if cache is not None and key in cache:
        return cache[key]

    # 1. Use stored URL if present (Spotify or Last.fm) directly to guarantee accuracy
    result = (track.get("album_art_url") or "").strip()
    if result.startswith("http"):
        if cache is not None:
            cache[key] = result
        return result

    # 2. Try Spotify Search (only in production when fetch is None)
    if fetch is None:
        spotify_art = search_spotify_art(track["artist"], track["title"])
        if spotify_art:
            if cache is not None:
                cache[key] = spotify_art
            return spotify_art

    # 3. Fallback to iTunes Search
    results = itunes_search(f"{track['artist']} {track['title']}", fetch=fetch)
    if results:
        artwork = results[0].get("artworkUrl100", "")
        if artwork:
            # Upgrade iTunes fallback to 1000x1000 for higher quality
            result = artwork.replace("100x100", "1000x1000")

    if cache is not None:
        cache[key] = result
    return result
