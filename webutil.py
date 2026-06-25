"""Shared helpers for external web resources: HTTP GET, iTunes search, art URLs.

These were duplicated across ingest/ and slideshow/ (four copies of a default
urlopen fetcher, two iTunes-search implementations, and a render->ingest import of
is_placeholder). Centralizing them removes the duplication and the cross-package
coupling. Network calls stay injectable via a `fetch` callable for offline tests.
"""

import json
import urllib.parse
import urllib.request
from typing import Callable, Optional

# Last.fm serves this hash as its gray-star "no image" placeholder.
DEFAULT_ART_HASH = "2a96cbd8b46e442fc41c2b86b821562f"

_ITUNES = "https://itunes.apple.com/search"


def fetch_text(url: str, timeout: int = 15) -> str:
    """GET a URL and return its decoded body. The default fetcher for our clients."""
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def is_placeholder(url: Optional[str]) -> bool:
    """True if the URL is empty/None or the Last.fm default placeholder image."""
    return not url or DEFAULT_ART_HASH in url


def itunes_search(term: str, entity: str = "song", limit: int = 1,
                  fetch: Optional[Callable[[str], str]] = None) -> list:
    """Return the iTunes Search API 'results' list for a term, or [] on any error.

    `fetch` is injectable for tests; it defaults to a real HTTP GET.
    """
    params = urllib.parse.urlencode({"term": term, "entity": entity, "limit": limit})
    fetcher = fetch or fetch_text
    try:
        payload = json.loads(fetcher(f"{_ITUNES}?{params}"))
        return payload.get("results", []) or []
    except Exception:
        return []
