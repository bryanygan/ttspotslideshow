"""Album-art download with a local on-disk cache."""

import hashlib
import urllib.request
from pathlib import Path
from typing import Callable, Optional

# is_placeholder / DEFAULT_ART_HASH live in webutil now (shared with ingest, which
# previously had to import them from render). Re-exported here for existing callers.
from webutil import DEFAULT_ART_HASH, is_placeholder  # noqa: F401


def _default_fetch(url: str, dest: Path, timeout: int = 20) -> None:
    """Download url to dest with a hard timeout to avoid indefinite hangs."""
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        dest.write_bytes(resp.read())


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


def find_override_art(
    artist: str,
    title: str,
    overrides_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Search for a manual album art override in overrides_dir.

    Supported formats in the overrides directory:
    - 'Artist - Title.png/jpg/jpeg/webp'
    - 'artist - title.png/jpg/jpeg/webp'
    - 'artist_-_title.png/jpg/jpeg/webp' (with underscores)
    - 'artist_title.png/jpg/jpeg/webp' (concatenated)

    Returns the Path to the override file if found, otherwise None.
    """
    import config
    from text_norm import normalize

    folder = Path(overrides_dir) if overrides_dir is not None else config.ART_OVERRIDES_DIR
    if not folder.exists():
        return None

    norm_artist = normalize(artist)
    norm_title = normalize(title)
    if not norm_artist or not norm_title:
        return None

    target_combined = normalize(f"{artist} - {title}")

    # Check each file in the overrides folder
    for path in folder.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
            continue

        stem = path.stem
        # Normalize underscores, dashes, tabs to spaces for flexible matching
        stem_spaced = stem.replace("_", " ").replace("-", " ").replace("\t", " ")
        norm_stem = normalize(stem_spaced)

        # Match target_combined or normalized key space-separated
        if norm_stem == target_combined or norm_stem == normalize(f"{norm_artist} {norm_title}"):
            return path

        # Try matching by splitting on a dash in the original filename if present
        if " - " in stem:
            parts = stem.split(" - ", 1)
            if normalize(parts[0]) == norm_artist and normalize(parts[1]) == norm_title:
                return path

    return None
