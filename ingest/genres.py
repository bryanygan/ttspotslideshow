"""Resolve each artist's genre bucket: Spotify primary, Last.fm fallback."""

from datetime import datetime, timezone

import db
from text_norm import normalize
from ingest.genre_map import bucket_for
from ingest.lastfm_client import get_top_tags


def resolve_artist_genre(name, spotify_client, lastfm_api_key, fetch=None) -> dict:
    """Resolve one artist to a genre bucket. Spotify first, then Last.fm, then none."""
    result = {
        "display_name": name,
        "spotify_artist_id": "",
        "raw_genres": [],
        "lastfm_tags": [],
        "primary_bucket": "unknown",
        "genre_source": "none",
    }

    # 1. Spotify primary (accept top hit only if the name matches).
    try:
        items = spotify_client.search(q=name, type="artist", limit=1)["artists"]["items"]
    except Exception:
        items = []
    if items and normalize(items[0].get("name", "")) == normalize(name):
        result["spotify_artist_id"] = items[0].get("id", "")
        genres = items[0].get("genres", []) or []
        result["raw_genres"] = genres
        if genres:
            result["primary_bucket"] = bucket_for(genres)
            result["genre_source"] = "spotify"
            return result

    # 2. Last.fm fallback.
    tags = get_top_tags(name, lastfm_api_key, fetch=fetch)
    if tags:
        result["lastfm_tags"] = tags
        result["primary_bucket"] = bucket_for(tags)
        result["genre_source"] = "lastfm"
        return result

    # 3. Nothing.
    return result


def enrich_all(conn, spotify_client, lastfm_api_key, fetch=None, sleep=None) -> dict:
    """Enrich every not-yet-cached artist. Returns a per-source summary."""
    summary = {"spotify": 0, "lastfm": 0, "none": 0, "skipped": 0}
    for name in db.distinct_artist_names(conn):
        key = normalize(name)
        if db.get_artist_genre(conn, key) is not None:
            summary["skipped"] += 1
            continue

        resolved = resolve_artist_genre(name, spotify_client, lastfm_api_key, fetch=fetch)
        db.upsert_artist_genre(
            conn,
            artist_key=key,
            display_name=resolved["display_name"],
            spotify_artist_id=resolved["spotify_artist_id"],
            raw_genres=",".join(resolved["raw_genres"]),
            lastfm_tags=",".join(resolved["lastfm_tags"]),
            primary_bucket=resolved["primary_bucket"],
            genre_source=resolved["genre_source"],
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
        summary[resolved["genre_source"]] += 1
        if resolved["genre_source"] == "lastfm" and sleep is not None:
            sleep(0.25)  # be polite to the Last.fm API
    return summary
