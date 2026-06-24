"""Thin wrapper around spotipy's OAuth setup.

Keeps all the auth wiring in one place. The first time you call get_client() a
browser window opens to authorize the app; after that the token is cached in
.spotify_cache and silently refreshed.
"""

import spotipy
from spotipy.oauth2 import SpotifyOAuth

import config


def get_client() -> spotipy.Spotify:
    """Return an authenticated Spotify client (prompts for login on first run)."""
    config.assert_credentials()
    auth_manager = SpotifyOAuth(
        client_id=config.CLIENT_ID,
        client_secret=config.CLIENT_SECRET,
        redirect_uri=config.REDIRECT_URI,
        scope=config.SCOPES,
        cache_path=str(config.TOKEN_CACHE_PATH),
        open_browser=True,
    )
    # requests_timeout caps each HTTP call so a hung/slow connection can't stall
    # the whole enrichment batch indefinitely; retries handle transient errors.
    return spotipy.Spotify(
        auth_manager=auth_manager,
        requests_timeout=10,
        retries=3,
        status_retries=3,
        backoff_factor=0.3,
    )
