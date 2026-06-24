"""Resolve hi-res album art via the iTunes Search API, with Last.fm fallback."""

import json
import urllib.parse
import urllib.request
from typing import Callable, Optional

from text_norm import normalize

_ITUNES = "https://itunes.apple.com/search"


def _default_fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=15) as resp:
        return resp.read().decode("utf-8")


def resolve_art_url(track, fetch: Optional[Callable[[str], str]] = None,
                    cache: Optional[dict] = None) -> str:
    """Best album-art URL for a track: iTunes 600x600, else stored Last.fm, else ''."""
    key = normalize(track["artist"]) + "\t" + normalize(track["title"])
    if cache is not None and key in cache:
        return cache[key]

    fetcher = fetch or _default_fetch
    result = track.get("album_art_url") or ""
    params = urllib.parse.urlencode({
        "term": f"{track['artist']} {track['title']}",
        "entity": "song",
        "limit": 1,
    })
    try:
        payload = json.loads(fetcher(f"{_ITUNES}?{params}"))
        results = payload.get("results", [])
        artwork = results[0].get("artworkUrl100", "") if results else ""
        if artwork:
            result = artwork.replace("100x100", "600x600")
    except Exception:
        pass  # keep the Last.fm fallback already in `result`

    if cache is not None:
        cache[key] = result
    return result
