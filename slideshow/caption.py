"""Smart caption and hashtag generator for TikTok slideshows.

A deterministic rotation-style vibe line plus genre hashtags, generated
together here so the "max 5 hashtags" rule holds.
"""

import re


# Rotation-flavored filler tags, matching Bryan's real "daily rotation" posts.
_FILLER_TAGS = ["#musictok", "#spotifywrapped", "#nowplaying", "#music", "#fyp"]

# Catch-all genre buckets that make meaningless hashtags — skipped everywhere.
_SKIP_GENRES = {"unknown", "other"}

# Nicer hashtags for buckets whose plain normalization reads oddly.
_GENRE_HASHTAG_ALIASES = {
    "r&b": "#rnb",
    "hip-hop": "#hiphop",
    "boom-bap": "#boombap",
    "drum-and-bass": "#dnb",
}


def _normalize_genre_to_hashtag(genre: str) -> str:
    """Convert a genre bucket name to a lowercase hashtag string.

    Examples: "Hip-Hop" -> "#hiphop", "R&B" -> "#rnb", "boom-bap" -> "#boombap"
    """
    alias = _GENRE_HASHTAG_ALIASES.get(genre.lower())
    if alias:
        return alias
    # Lowercase, remove ampersands, hyphens, and spaces
    cleaned = genre.lower()
    cleaned = cleaned.replace("&", "")
    cleaned = cleaned.replace("-", "")
    cleaned = cleaned.replace(" ", "")
    # Remove any remaining non-alphanumeric characters
    cleaned = re.sub(r"[^a-z0-9]", "", cleaned)
    return f"#{cleaned}"


def get_suggested_hashtags(tracks: list[dict], max_tags: int = 5) -> list[str]:
    """Return a list of suggested hashtag strings (with # prefix).

    Extracts unique genres from tracks, sorts by frequency descending, and
    converts to hashtag format. Fills with general music hashtags if fewer
    unique genres than max_tags.
    """
    genres = [
        t.get("primary_bucket")
        for t in tracks
        if t.get("primary_bucket") and t["primary_bucket"].lower() not in _SKIP_GENRES
    ]
    if not genres:
        return _FILLER_TAGS[:max_tags]

    # Count frequency and sort descending
    counts = {}
    for g in genres:
        counts[g] = counts.get(g, 0) + 1
    genre_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)

    hashtags = []
    for genre, _count in genre_counts:
        if len(hashtags) >= max_tags:
            break
        hashtags.append(_normalize_genre_to_hashtag(genre))

    # Fill with general music hashtags if needed
    for filler in _FILLER_TAGS:
        if len(hashtags) >= max_tags:
            break
        if filler not in hashtags:
            hashtags.append(filler)

    return hashtags[:max_tags]


def _assemble_with_hashtags(body: str, tracks: list[dict], max_len: int = 300) -> str:
    """Append up to 5 deterministic hashtags to a caption body, keeping <300 chars.

    Hashtags go on their own line. If the result is too long, hashtags are
    dropped one at a time (never below one), then the body is truncated as a
    last resort.
    """
    hashtags = get_suggested_hashtags(tracks, max_tags=5)

    caption = f"{body}\n{' '.join(hashtags)}".strip()
    if len(caption) <= max_len:
        return caption

    # Too long: drop trailing hashtags, keeping at least one.
    for i in range(len(hashtags) - 1, 0, -1):
        caption = f"{body}\n{' '.join(hashtags[:i])}".strip()
        if len(caption) <= max_len:
            return caption

    # Last resort: truncate the body but keep one hashtag.
    tail = f"\n{hashtags[0]}" if hashtags else ""
    keep = max_len - len(tail)
    return (body[:keep].rstrip() + tail).strip()


def generate_caption(tracks: list[dict], cover_title: str | None = None) -> str:
    """Generate a TikTok-ready caption with hashtags.

    Args:
        tracks: List of track dicts with keys: artist, title, primary_bucket.
        cover_title: Optional cover slide title.

    Returns:
        A caption string with at most 5 hashtags, under 300 characters.
    """
    return _template_caption(tracks, cover_title=cover_title)


# On-brand vibe lines for the caption. Kept in Bryan's rotation voice — no "Featuring: X, Y" lists.
# ``{genre}`` is filled with the dominant genre bucket.
_ROTATION_LINES = [
    "daily music rotation, been leaning heavy into {genre} lately",
    "yet another rotation post, {genre} has been on repeat fr",
    "lowk been in my {genre} bag nonstop these days",
    "current rotation, {genre} running the whole playlist rn",
    "been vibing to a lot of {genre} on the commute lately",
    "kinda {genre} heavy this time, not mad at it tbh",
]


def _dominant_genre(tracks: list[dict]) -> str:
    counts: dict[str, int] = {}
    for t in tracks:
        g = t.get("primary_bucket")
        if g and g.lower() not in _SKIP_GENRES:
            counts[g] = counts.get(g, 0) + 1
    if not counts:
        return "everything"
    return max(counts, key=counts.get).lower()


def _template_caption(tracks: list[dict], cover_title: str | None = None) -> str:
    """Deterministic, on-brand caption.

    Produces a short rotation-style vibe line in Bryan's voice plus up to 5
    genre hashtags, always under 300 characters. Deterministic per track list
    (so the same input yields the same caption), with light variety driven by
    the track count and dominant genre.
    """
    if not tracks:
        return ""

    genre = _dominant_genre(tracks)
    line = _ROTATION_LINES[len(tracks) % len(_ROTATION_LINES)].format(genre=genre)
    return _assemble_with_hashtags(line, tracks)
