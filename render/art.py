"""Album-art download with a local on-disk cache."""

import hashlib
import urllib.request
from pathlib import Path
from typing import Callable, Optional

# is_placeholder / DEFAULT_ART_HASH live in webutil now (shared with ingest, which
# previously had to import them from render). Re-exported here for existing callers.
from webutil import DEFAULT_ART_HASH, is_placeholder  # noqa: F401


def _default_fetch(url: str, dest: Path) -> None:
    urllib.request.urlretrieve(url, dest)


def load_art(
    art_url: Optional[str],
    cache_dir,
    fetch: Optional[Callable[[str, Path], None]] = None,
) -> Optional[Path]:
    """Download art_url into cache_dir (once) and return the local path.

    Returns None for placeholder/missing URLs or if the download fails.
    """
    if is_placeholder(art_url):
        return None

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(art_url.encode("utf-8")).hexdigest()
    dest = cache_dir / f"{digest}.jpg"

    if dest.exists():
        return dest

    fetcher = fetch or _default_fetch
    try:
        fetcher(art_url, dest)
    except Exception:
        if dest.exists():
            dest.unlink(missing_ok=True)
        return None

    return dest if dest.exists() else None
