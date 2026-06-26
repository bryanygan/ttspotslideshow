"""Resolve hi-res album art via the iTunes Search API, with Last.fm fallback."""

from typing import Callable, Optional

from text_norm import normalize
from webutil import itunes_search


def resolve_art_url(track, fetch: Optional[Callable[[str], str]] = None,
                    cache: Optional[dict] = None) -> str:
    """Best album-art URL for a track: stored URL if present, else iTunes search fallback."""
    key = normalize(track["artist"]) + "\t" + normalize(track["title"])
    if cache is not None and key in cache:
        return cache[key]

    result = (track.get("album_art_url") or "").strip()
    # Bypass iTunes search for accurate Spotify artwork URLs (skip search to prevent mismatches).
    # Last.fm fallbacks (which contain 'lastfm' or 'fastly') are still upgraded via iTunes search.
    if result.startswith("http") and not any(x in result for x in ["lastfm", "fastly"]):
        if cache is not None:
            cache[key] = result
        return result

    results = itunes_search(f"{track['artist']} {track['title']}", fetch=fetch)
    if results:
        artwork = results[0].get("artworkUrl100", "")
        if artwork:
            result = artwork.replace("100x100", "600x600")

    if cache is not None:
        cache[key] = result
    return result
