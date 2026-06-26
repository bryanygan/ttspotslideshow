"""Sync slideshow tracks to a Spotify playlist.

Provides ``sync_playlist(conn, tracks, playlist_id=None)`` which finds or creates
the "Bryan's Bi-Daily Rotation" playlist, replaces its contents with the given
tracks, and returns the playlist URL.

Errors are logged as warnings and never raised — a failed sync must not crash
the slideshow generation.
"""

import logging

logger = logging.getLogger(__name__)

PLAYLIST_NAME = "Bryan's Bi-Daily Rotation"
PLAYLIST_DESCRIPTION = "Auto-generated from the bi-daily TTSpotSlideShow recap."


def sync_playlist(conn, tracks: list[dict], playlist_id: str | None = None) -> str | None:
    """Sync *tracks* to the target Spotify playlist.

    Parameters
    ----------
    conn : sqlite3.Connection
        Database connection (unused here but kept for API symmetry with the
        builder module).
    tracks : list[dict]
        Each dict must have a ``track_id`` key holding a 22-char Spotify ID.
    playlist_id : str or None
        If provided, use this playlist directly.  Otherwise the function looks
        for an existing playlist named *PLAYLIST_NAME* in the current user's
        library and creates one if none is found.

    Returns
    -------
    str or None
        The playlist's Spotify external URL, or ``None`` when sync fails.
    """
    try:
        from spotify_client import get_client
        sp = get_client()
    except Exception as exc:
        logger.warning("playlist_sync: failed to create Spotify client: %s", exc)
        return None

    try:
        # --- Resolve playlist_id ------------------------------------------------
        if playlist_id is None:
            playlist_id = _find_or_create_playlist(sp, PLAYLIST_NAME)
            if playlist_id is None:
                return None

        # --- Build Spotify URIs -------------------------------------------------
        track_ids = [
            t["track_id"]
            for t in tracks
            if t.get("track_id") and len(t["track_id"]) == 22 and t["track_id"].isalnum()
        ]
        if not track_ids:
            logger.warning("playlist_sync: no valid track IDs to sync")
            return None

        spotify_uris = [f"spotify:track:{tid}" for tid in track_ids]

        # --- Replace playlist contents -----------------------------------------
        sp.playlist_replace_items(playlist_id, spotify_uris)

        # --- Fetch and return URL ----------------------------------------------
        playlist = sp.playlist(playlist_id)
        return playlist.get("external_urls", {}).get("spotify")

    except Exception as exc:
        _log_spotify_error(exc)
        return None


def _find_or_create_playlist(sp, name: str) -> str | None:
    """Return the ID of an existing playlist named *name*, or create one."""
    try:
        user_id = sp.current_user()["id"]
    except Exception as exc:
        logger.warning("playlist_sync: could not resolve current user: %s", exc)
        return None

    # Search existing playlists (up to 50)
    try:
        results = sp.user_playlists(user_id, limit=50)
        for pl in results.get("items", []):
            if pl.get("name") == name:
                return pl["id"]
    except Exception as exc:
        logger.warning("playlist_sync: error listing playlists: %s", exc)

    # Create a new one
    try:
        pl = sp.user_playlist_create(user_id, name, public=True, description=PLAYLIST_DESCRIPTION)
        logger.info("playlist_sync: created playlist '%s' (%s)", name, pl["id"])
        return pl["id"]
    except Exception as exc:
        logger.warning("playlist_sync: could not create playlist '%s': %s", name, exc)
        return None


def _log_spotify_error(exc: Exception) -> None:
    """Log a Spotify / network error at warning level with actionable hints."""
    msg = str(exc)
    if "429" in msg:
        logger.warning("playlist_sync: rate-limited by Spotify (429) — try again later")
    elif "401" in msg:
        logger.warning("playlist_sync: auth error (401) — token may be expired, re-authorize")
    elif "403" in msg:
        logger.warning("playlist_sync: forbidden (403) — check playlist-modify scopes in config")
    else:
        logger.warning("playlist_sync: sync failed: %s", msg)
