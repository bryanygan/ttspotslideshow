"""Phase 1 logger: pull recently-played tracks from Spotify into the local DB.

Run this several times a day (Task Scheduler) so nothing slips past Spotify's
50-track recently-played buffer. Each run only fetches plays newer than what we
already have, then dedupes on (track_id, played_at).

Usage:
    python logger.py            # log new plays
    python logger.py --auth     # just run the OAuth login flow and exit
"""

import argparse
import logging
from datetime import datetime, timezone

import spotipy

import db
from spotify_client import get_client
from logsetup import setup_logging

LOG = logging.getLogger("logger")


def _iso_to_unix_ms(iso_ts: str) -> int:
    """Convert a Spotify ISO-8601 timestamp (UTC, may end in 'Z') to Unix ms."""
    dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    return int(dt.timestamp() * 1000)


def _primary_image_url(track: dict) -> str | None:
    """Largest album image URL (Spotify lists images largest-first), or None."""
    images = track.get("album", {}).get("images") or []
    return images[0]["url"] if images else None


def _resolve_genre(sp: spotipy.Spotify, conn, artist_id: str | None,
                   artist_name: str) -> str:
    """Return the artist's primary genre, fetching + caching it if unseen.

    Spotify attaches genres to the artist, not the track, and the batch artist
    endpoint was removed, so each new artist is a single cached lookup.
    """
    if not artist_id:
        return "unknown"

    cached = db.get_cached_genres(conn, artist_id)
    if cached is not None:                      # '' means "looked up, no genres"
        return cached.split(",")[0] if cached else "unknown"

    # Not cached yet -> ask Spotify once, then remember the answer.
    try:
        artist = sp.artist(artist_id)
        genres = artist.get("genres") or []
    except spotipy.SpotifyException:
        genres = []

    db.cache_artist(
        conn,
        artist_id=artist_id,
        name=artist_name,
        genres=",".join(genres),
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
    return genres[0] if genres else "unknown"


def log_recent_plays() -> int:
    """Fetch new plays since our last logged timestamp. Returns rows added."""
    db.init_db()
    sp = get_client()

    # Scope the cursor to our own (Spotify) plays: the Last.fm import holds newer
    # timestamps, and an unscoped max would skip Spotify plays since the last run.
    after = db.latest_played_at(source="spotify")
    after_ms = _iso_to_unix_ms(after) if after else None

    # recently-played returns the most recent plays (max 50). 'after' limits the
    # response to plays newer than a cursor so repeat runs stay cheap.
    response = sp.current_user_recently_played(limit=50, after=after_ms)
    items = response.get("items", [])

    added = 0
    with db.connect() as conn:
        for item in items:
            track = item["track"]
            played_at = item["played_at"]
            primary_artist = (track.get("artists") or [{}])[0]
            artist_id = primary_artist.get("id")
            artist_name = primary_artist.get("name", "Unknown Artist")

            genre = _resolve_genre(sp, conn, artist_id, artist_name)

            was_new = db.insert_play(
                conn,
                track_id=track["id"],
                name=track["name"],
                artist=artist_name,
                artist_id=artist_id,
                artist_genre=genre,
                album_art_url=_primary_image_url(track),
                popularity=None,  # field removed from the Spotify API (Feb 2026)
                played_at=played_at,
            )
            if was_new:
                added += 1

    return added


def main() -> None:
    parser = argparse.ArgumentParser(description="Log recently played Spotify tracks.")
    parser.add_argument(
        "--auth",
        action="store_true",
        help="Run the OAuth login flow and exit (use once during setup).",
    )
    args = parser.parse_args()

    setup_logging("logger")

    if args.auth:
        get_client().current_user()  # forces the login/token exchange
        LOG.info("Authenticated. Token cached -> future runs won't prompt.")
        return

    added = log_recent_plays()
    total = db.play_count()
    LOG.info("Added %d new play(s). Total logged: %d.", added, total)


if __name__ == "__main__":
    main()
