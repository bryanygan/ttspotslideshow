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
    min_weight: int = 10,
) -> list[str]:
    """Return lowercased Last.fm top tags for an artist with weight >= min_weight."""
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
    return [
        t["name"].strip().lower()
        for t in tags
        if int(t.get("count", 0)) >= min_weight and t.get("name")
    ]
