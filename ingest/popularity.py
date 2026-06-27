"""Resolve a track's global popularity: Last.fm primary, ListenBrainz fallback.

Raw listener counts are log-normalized into a 0-100 score so the dashboard's
"underrated" ratio (play_count / popularity) is meaningful again after Spotify
removed track.popularity.
"""

import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Callable, Optional

from webutil import fetch_text

POPULARITY_CEIL = 5_000_000  # ~ a megahit's Last.fm listener count -> score 100

_LASTFM = "https://ws.audioscrobbler.com/2.0/"
_LB_LOOKUP = "https://api.listenbrainz.org/1/metadata/lookup/"
_LB_POPULARITY = "https://api.listenbrainz.org/1/popularity/recording"


def normalize_listeners(listeners: Optional[int]) -> int:
    """Log-scale a raw listener count into a 0-100 popularity score."""
    if not listeners or listeners < 0:
        return 0
    score = 100 * math.log10(listeners + 1) / math.log10(POPULARITY_CEIL + 1)
    return max(0, min(100, round(score)))


def fetch_lastfm_listeners(artist, title, api_key, fetch=None) -> Optional[int]:
    """Last.fm track.getInfo -> global listener count, or None on miss/error."""
    if not api_key:
        return None
    params = urllib.parse.urlencode({
        "method": "track.getInfo",
        "artist": artist,
        "track": title,
        "api_key": api_key,
        "format": "json",
    })
    fetcher = fetch or fetch_text
    try:
        payload = json.loads(fetcher(f"{_LASTFM}?{params}"))
    except Exception:
        return None
    if not isinstance(payload, dict) or "error" in payload:
        return None
    track = payload.get("track") or {}
    try:
        return int(track.get("listeners"))
    except (TypeError, ValueError):
        return None


def _lb_popularity_for_mbid(mbid, token, fetch=None) -> Optional[int]:
    """POST a recording MBID to the ListenBrainz popularity API -> user count."""
    body = json.dumps({"recording_mbids": [mbid]}).encode("utf-8")
    req = urllib.request.Request(
        _LB_POPULARITY,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Token {token}",
        },
        method="POST",
    )
    try:
        if fetch is not None:
            payload = json.loads(fetch(req))
        else:
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    # API returns a list of {recording_mbid, total_listen_count, total_user_count}.
    rows = payload if isinstance(payload, list) else payload.get("payload", [])
    for row in rows or []:
        if row.get("recording_mbid") == mbid:
            try:
                return int(row.get("total_user_count"))
            except (TypeError, ValueError):
                return None
    return None


def fetch_listenbrainz_listeners(artist, title, token, fetch=None) -> Optional[int]:
    """ListenBrainz fallback: artist+title -> MBID -> global user count.

    The metadata-lookup GET requires the auth token (verified live), so the
    production path builds an authed Request rather than the header-less
    ``fetch_text``. Tests inject a URL-accepting ``fetch`` to bypass the network.
    """
    if not token:
        return None
    params = urllib.parse.urlencode({
        "artist_name": artist,
        "recording_name": title,
    })
    url = f"{_LB_LOOKUP}?{params}"
    try:
        if fetch is not None:
            payload = json.loads(fetch(url))
        else:
            req = urllib.request.Request(
                url, headers={"Authorization": f"Token {token}"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    mbid = (payload or {}).get("recording_mbid")
    if not mbid:
        return None
    return _lb_popularity_for_mbid(mbid, token, fetch=fetch)


def resolve_popularity(artist, title, *, lastfm_api_key, listenbrainz_token,
                       fetch=None) -> dict:
    """Try Last.fm, then ListenBrainz. Returns {listeners, popularity, source}."""
    listeners = fetch_lastfm_listeners(artist, title, lastfm_api_key, fetch=fetch)
    source = "lastfm"
    if listeners is None:
        listeners = fetch_listenbrainz_listeners(
            artist, title, listenbrainz_token, fetch=fetch
        )
        source = "listenbrainz"
    if listeners is None:
        return {"listeners": None, "popularity": None, "source": "none"}
    return {
        "listeners": listeners,
        "popularity": normalize_listeners(listeners),
        "source": source,
    }
