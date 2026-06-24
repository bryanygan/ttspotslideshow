"""Resolve each artist's genre bucket: Spotify primary, Last.fm fallback."""

from datetime import datetime, timezone

import spotipy

import db
from text_norm import normalize
from ingest.genre_map import bucket_for
from ingest.lastfm_client import get_top_tags


def resolve_artist_genre(name, spotify_client, lastfm_api_key, fetch=None) -> dict:
    """Resolve one artist to a genre bucket. Spotify first, then Last.fm, then none.

    Sets ``transient=True`` when the Spotify call itself failed transiently (rate
    limit / timeout / network). The caller should DEFER such artists — leave them
    uncached so a later, resumable run can still fetch their Spotify genres,
    rather than locking in a weaker Last.fm/none result.
    """
    result = {
        "display_name": name,
        "spotify_artist_id": "",
        "raw_genres": [],
        "lastfm_tags": [],
        "primary_bucket": "unknown",
        "genre_source": "none",
        "transient": False,
    }

    # 1. Spotify primary (accept top hit only if the name matches).
    rate_limited = False
    try:
        items = spotify_client.search(q=name, type="artist", limit=1)["artists"]["items"]
    except spotipy.SpotifyException as exc:
        items = []
        if getattr(exc, "http_status", None) == 429:
            rate_limited = True  # rate limited -> transient, retry later
    except Exception:
        items = []
        rate_limited = True  # timeout / connection error -> transient
    if items and normalize(items[0].get("name", "")) == normalize(name):
        result["spotify_artist_id"] = items[0].get("id", "")
        genres = items[0].get("genres", []) or []
        result["raw_genres"] = genres
        if genres:
            result["primary_bucket"] = bucket_for(genres)
            result["genre_source"] = "spotify"
            return result

    # If Spotify itself failed transiently, defer instead of falling to Last.fm.
    if rate_limited:
        result["transient"] = True
        return result

    # 2. Last.fm fallback (Spotify returned cleanly but had no usable genres).
    tags = get_top_tags(name, lastfm_api_key, fetch=fetch)
    if tags:
        result["lastfm_tags"] = tags
        result["primary_bucket"] = bucket_for(tags)
        result["genre_source"] = "lastfm"
        return result

    # 3. Nothing.
    return result


def enrich_all(conn, spotify_client, lastfm_api_key, fetch=None, sleep=None,
               commit_every=50, progress=None, max_consecutive_transient=20) -> dict:
    """Enrich every not-yet-cached artist. Returns a per-source summary.

    Commits every `commit_every` new enrichments so progress is persisted and the
    run is resumable: if it's interrupted (network hang, rate limit, Ctrl-C), a
    re-run skips the already-cached artists and continues. `progress(done, total)`
    is called periodically if provided.

    Transient Spotify failures (rate limit / timeout) DEFER the artist (left
    uncached for a later run). After `max_consecutive_transient` such failures in
    a row the run stops early (`stopped_early=True`) — Spotify is rate-limiting, so
    there's no point spinning; re-run once the limit clears.
    """
    summary = {"spotify": 0, "lastfm": 0, "none": 0, "skipped": 0,
               "deferred": 0, "stopped_early": False}
    names = db.distinct_artist_names(conn)
    total = len(names)
    since_commit = 0
    consecutive_transient = 0
    idx = 0

    for idx, name in enumerate(names, start=1):
        key = normalize(name)
        if db.get_artist_genre(conn, key) is not None:
            summary["skipped"] += 1
        else:
            resolved = resolve_artist_genre(
                name, spotify_client, lastfm_api_key, fetch=fetch
            )
            if resolved["transient"]:
                summary["deferred"] += 1
                consecutive_transient += 1
                if consecutive_transient >= max_consecutive_transient:
                    summary["stopped_early"] = True
                    break
                continue

            consecutive_transient = 0
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
            since_commit += 1
            if resolved["genre_source"] == "lastfm" and sleep is not None:
                sleep(0.25)  # be polite to the Last.fm API
            if since_commit >= commit_every:
                conn.commit()
                since_commit = 0

        if progress is not None and idx % commit_every == 0:
            progress(idx, total)

    conn.commit()
    if progress is not None:
        progress(idx, total)
    return summary
