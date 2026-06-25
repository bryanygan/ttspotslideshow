"""Minimal Last.fm API client (stdlib only) for genre-tag fallback."""

import json
import urllib.parse
import urllib.request
from typing import Callable, Optional

_BASE = "https://ws.audioscrobbler.com/2.0/"


def _default_fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=15) as resp:
        return resp.read().decode("utf-8")


def get_top_tags(
    artist: str,
    api_key: str,
    fetch: Optional[Callable[[str], str]] = None,
    min_weight: int = 1,
) -> list[str]:
    """Return lowercased Last.fm top tags for an artist with weight >= min_weight.

    The default floor is deliberately low (1) because real genre tags can carry
    small relative weights (e.g. 'plugg'=3). Non-genre tags that come along for the
    ride are filtered out downstream by ``genre_map.is_genre_noise``; ``bucket_for``
    only ever picks a *mapped* tag, so weak noise never changes the bucket.
    """
    params = urllib.parse.urlencode({
        "method": "artist.gettoptags",
        "artist": artist,
        "api_key": api_key,
        "format": "json",
    })
    url = f"{_BASE}?{params}"
    fetcher = fetch or _default_fetch
    try:
        payload = json.loads(fetcher(url))
    except Exception:
        return []
    if "error" in payload:
        return []
    tags = payload.get("toptags", {}).get("tag", [])
    result = []
    for t in tags:
        name = t.get("name")
        if not name:
            continue
        try:
            weight = int(t.get("count", 0))
        except (TypeError, ValueError):
            weight = 0  # Last.fm always returns ints, but never trust the wire
        if weight >= min_weight:
            result.append(name.strip().lower())
    return result
