"""Smart caption and hashtag generator for TikTok slideshows."""

import re
from collections import Counter

_MUSIC_EMOJIS = ["\U0001f3a7", "\U0001f3b5", "\U0001f3b6", "\U0001f3a4", "\U0001f3b9"]  # 🎧🎵🎶🎤🎹

_FILLER_TAGS = ["#nowplaying", "#music", "#fyp"]


def _normalize_genre_to_hashtag(genre: str) -> str:
    """Convert a genre bucket name to a lowercase hashtag string.

    Examples: "Hip-Hop" -> "#hiphop", "R&B" -> "#rb", "boom-bap" -> "#boombap"
    """
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
    genres = [t.get("primary_bucket") for t in tracks if t.get("primary_bucket")]
    if not genres:
        return _FILLER_TAGS[:max_tags]

    # Count frequency and sort descending
    genre_counts = Counter(genres).most_common()
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


def generate_caption(tracks: list[dict], cover_title: str | None = None) -> str:
    """Generate a TikTok-ready caption with hashtags.

    Args:
        tracks: List of track dicts with keys: artist, title, primary_bucket (genre)
        cover_title: Optional cover slide title

    Returns:
        A formatted caption string, e.g.:
        "My Weekly Mix 🎧 Featuring: Kendrick Lamar, Travis Scott, and more.
        #hiphop #trap #plugg #rap #music"

    Rules:
        - Max 5 hashtags (TikTok limit)
        - Prioritize hashtags by genre frequency (most common genres first)
        - Convert genre bucket names to lowercase hashtag format
        - Include artist names in the caption text
        - If cover_title is provided, use it as the opening line
        - Keep total caption under 300 characters
        - Use music-relevant emojis
    """
    if not tracks:
        return ""

    # Build opening line
    title = cover_title if cover_title else "My Weekly Mix"
    emoji = _MUSIC_EMOJIS[0]  # 🎧

    # Collect unique artists (preserve order, limit to first 4)
    seen: set[str] = set()
    artists: list[str] = []
    for t in tracks:
        artist = t.get("artist", "Unknown")
        if artist not in seen:
            seen.add(artist)
            artists.append(artist)

    # Build the featured artists portion
    max_artists = 4
    featured = artists[:max_artists]
    if len(featured) == 1:
        artists_text = featured[0]
    elif len(featured) == 2:
        artists_text = f"{featured[0]} and {featured[1]}"
    elif len(featured) >= 3:
        artists_text = f"{', '.join(featured[:-1])}, and {featured[-1]}"
    else:
        artists_text = "Various artists"

    if len(artists) > max_artists:
        artists_text += ", and more"

    # Assemble base caption (without hashtags)
    caption = f"{title} {emoji} Featuring: {artists_text}. "

    # Generate hashtags
    hashtags = get_suggested_hashtags(tracks, max_tags=5)
    hashtags_text = " ".join(hashtags)

    # Check total length; if too long, truncate artist list
    full_caption = f"{caption}{hashtags_text}"
    if len(full_caption) > 300:
        # Try with fewer artists
        for n in range(max_artists - 1, 0, -1):
            featured = artists[:n]
            if len(featured) == 1:
                artists_text = featured[0]
            elif len(featured) == 2:
                artists_text = f"{featured[0]} and {featured[1]}"
            else:
                artists_text = ", ".join(featured)

            if len(artists) > n:
                artists_text += ", and more"

            caption = f"{title} {emoji} Featuring: {artists_text}. "
            full_caption = f"{caption}{hashtags_text}"
            if len(full_caption) <= 300:
                break

        # If still too long, reduce hashtags
        if len(full_caption) > 300:
            for i in range(len(hashtags) - 1, 0, -1):
                hashtags_text = " ".join(hashtags[:i])
                full_caption = f"{caption}{hashtags_text}"
                if len(full_caption) <= 300:
                    break

    return full_caption.strip()
