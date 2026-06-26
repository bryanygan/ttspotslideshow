"""Resolve hi-res album art via Spotify, with iTunes Search API fallback.

Source hierarchy:
  1. Stored URL (if not a Last.fm/Fastly low-res placeholder)
  2. Spotify API search
  3. iTunes Search API (requires confirmation in the UI before use)
"""

import re
from typing import Callable, Optional

from text_norm import normalize
from webutil import itunes_search


def clean_term(text: str) -> str:
    """Remove special characters and junk descriptors from search text."""
    # Remove leading punctuation/hashtags
    text = re.sub(r"^[#,\-\s+]+", "", text)
    # Remove common video/leak descriptors
    text = re.sub(
        r"\((Full Leaked|Slowed|Reverb|Bass Cover|Lofi|Official|Audio|Video|Lyrics|Remix|Edit)\)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\[(Full Leaked|Slowed|Reverb|Bass Cover|Lofi|Official|Audio|Video|Lyrics|Remix|Edit)\]",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Remove producer tags
    text = re.sub(
        r"\b(Prod\.\s+by|Produced\s+by)\s+[\w\s]+", "", text, flags=re.IGNORECASE
    )
    return text.strip()


def _is_itunes_url(url: str) -> bool:
    """Return True if the URL originated from the iTunes/Apple CDN."""
    return bool(url) and "mzstatic.com" in url


def search_spotify_art(artist: str, title: str) -> Optional[str]:
    """Search Spotify Web API for the track cover art, with query cleaning and loose fallbacks."""
    try:
        from spotify_client import get_client
        sp = get_client()

        # Clean inputs
        clean_title = clean_term(title)
        clean_artist = clean_term(artist)

        # 1. Try Strict Search
        query = f"track:{clean_title} artist:{clean_artist}"
        results = sp.search(q=query, type="track", limit=1)
        tracks = results.get("tracks", {}).get("items", [])

        # 2. Try Loose Search Fallback if strict failed (strip features, try text-only search)
        if not tracks:
            # Strip featured artists from title (e.g. "Song (feat. Artist)" -> "Song")
            simple_title = re.sub(
                r"\(?feat\..*?\)?", "", clean_title, flags=re.IGNORECASE
            ).strip()
            # Strip secondary main artists from artist list (e.g. "Artist A & Artist B" -> "Artist A")
            simple_artist = re.split(
                r"[,&]|\band\b", clean_artist, flags=re.IGNORECASE
            )[0].strip()

            # Simple text query: "Artist Title"
            loose_query = f"{simple_artist} {simple_title}"
            results = sp.search(q=loose_query, type="track", limit=1)
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
    """Best album-art URL for a track.

    Priority:
      1. Stored URL (if not a Last.fm/Fastly low-res placeholder) — returned immediately.
      2. Spotify API search — only in production (fetch is None).
      3. iTunes Search API fallback — URL will be flagged as needing user confirmation
         by the caller (check with _is_itunes_url()).
    """
    key = normalize(track["artist"]) + "\t" + normalize(track["title"])
    if cache is not None and key in cache:
        return cache[key]

    # 1. Use stored URL if present, unless it's a Last.fm low-res placeholder
    result = (track.get("album_art_url") or "").strip()
    if result.startswith("http") and not any(x in result for x in ["lastfm", "fastly"]):
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
    clean_title = clean_term(track["title"])
    clean_artist = clean_term(track["artist"])
    result = ""  # reset: don't carry forward the disqualified stored URL
    results = itunes_search(f"{clean_artist} {clean_title}", fetch=fetch)
    if results:
        artwork = results[0].get("artworkUrl100", "")
        if artwork:
            # Upgrade iTunes thumbnail to 1000x1000 for higher quality
            result = artwork.replace("100x100", "1000x1000")

    if cache is not None:
        cache[key] = result
    return result
