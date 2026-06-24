"""Shared text normalization for dedup keys and artist matching.

Deliberately conservative: collapses case/whitespace and strips a trailing
remaster/version suffix, but never alters the core title/artist enough to merge
genuinely different songs.
"""

import re

_WS = re.compile(r"\s+")
# Trailing " - <something> remaster" or " - <something> version" (case-insensitive).
_SUFFIX = re.compile(r"\s*-\s*[^-]*\b(remaster(?:ed)?|version)\b.*$", re.IGNORECASE)


def normalize(text: str) -> str:
    """Lowercase, strip, collapse whitespace, and drop a trailing remaster/version tag."""
    if not text:
        return ""
    text = _SUFFIX.sub("", text)
    text = _WS.sub(" ", text).strip().lower()
    return text
