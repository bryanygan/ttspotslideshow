"""Parse Spotify / Last.fm playlists into selectable candidate tracks.

Given a playlist link (or raw ID), resolve its tracks into the same lightweight
candidate dicts the OCR scanner produces, so they can seed the dashboard's pick
pool:

    {track_key, track_id, title, artist, album_art_url, primary_bucket}

Spotify support is full (paginated playlist items). Last.fm has no clean public
"give me this playlist's tracks" endpoint, so we support the two link shapes that
*do* map to API methods: a user's loved tracks and a user's top tracks.
"""

import json
import re
import urllib.parse
from typing import Callable, Optional

import db
from text_norm import normalize
from webutil import fetch_text, is_placeholder

_LASTFM_API = "https://ws.audioscrobbler.com/2.0/"


class PlaylistParseError(Exception):
    """Raised when a playlist link can't be recognised or fetched."""


def _bucket_for(conn, artist: str) -> str:
    """Look up the cached genre bucket for an artist, defaulting to 'unknown'."""
    if conn is None:
        return "unknown"
    try:
        row = db.get_artist_genre(conn, normalize(artist))
        if row:
            return row["primary_bucket"]
    except Exception:
        pass
    return "unknown"


def _candidate(conn, *, track_id: str, title: str, artist: str,
               album_art_url: str) -> dict:
    """Build one candidate dict in the shape the dashboard expects."""
    track_key = normalize(artist) + "\t" + normalize(title)
    return {
        "track_key": track_key,
        "track_id": track_id or "",
        "title": title,
        "artist": artist,
        "album_art_url": album_art_url or "",
        "primary_bucket": _bucket_for(conn, artist),
    }


def _dedupe(candidates: list[dict]) -> list[dict]:
    """Drop duplicate track_keys, preserving first-seen order."""
    seen: set[str] = set()
    out = []
    for c in candidates:
        if c["track_key"] in seen:
            continue
        seen.add(c["track_key"])
        out.append(c)
    return out


# --- Spotify -----------------------------------------------------------------

def _extract_spotify_playlist_id(text: str) -> Optional[str]:
    """Pull a Spotify playlist ID out of a URL, URI, or raw ID."""
    text = text.strip()
    # spotify:playlist:<id>
    m = re.search(r"playlist[:/]([A-Za-z0-9]{22})", text)
    if m:
        return m.group(1)
    # bare 22-char base62 id
    if re.fullmatch(r"[A-Za-z0-9]{22}", text):
        return text
    return None


def parse_spotify_playlist(playlist_id: str, conn=None) -> list[dict]:
    """Resolve all tracks in a Spotify playlist into candidate dicts.

    Tries public Embed Widget scraping first to support algorithmic/personalized
    mixes and bypass new API restrictions, and falls back to the official Spotify
    Web API /items endpoint for private playlists owned/followed by the user.
    """
    import urllib.request
    import re
    import json
    from spotify_client import get_client

    candidates: list[dict] = []
    scrape_success = False

    # 1. Try public Embed Widget scraping (bypasses OAuth restrictions, works on mixes)
    try:
        embed_url = f"https://open.spotify.com/embed/playlist/{playlist_id}"
        req = urllib.request.Request(
            embed_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        with urllib.request.urlopen(req) as response:
            html = response.read().decode("utf-8")

        pattern = r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>'
        script_m = re.search(pattern, html, re.DOTALL)
        if not script_m:
            scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
            for s in scripts:
                if s.strip().startswith('{"props"'):
                    script_m = re.match(r'^(.*)$', s.strip())
                    break

        if script_m:
            data = json.loads(script_m.group(1).strip())
            entity = data["props"]["pageProps"]["state"]["data"]["entity"]
            track_list = entity.get("trackList", [])
            if track_list:
                for item in track_list:
                    uri = item.get("uri") or ""
                    track_id = uri.split(":")[-1] if uri.startswith("spotify:track:") else ""
                    name = item.get("title") or ""
                    artist = item.get("subtitle") or ""
                    if not track_id or not name or not artist:
                        continue
                    candidates.append(_candidate(
                        conn,
                        track_id=track_id,
                        title=name,
                        artist=artist,
                        album_art_url="",  # resolved during generation to avoid API 429s
                    ))
                scrape_success = True
    except Exception:
        # Silently fall back to official API if scrape fails
        pass

    # 2. Fallback to official Spotify API using the correct /items endpoint
    if not scrape_success:
        sp = get_client()
        offset = 0
        page_size = 100
        while True:
            try:
                # Direct _get to bypass spotipy's deprecated /tracks URL
                plid = sp._get_id("playlist", playlist_id)
                page = sp._get(
                    f"playlists/{plid}/items",
                    limit=page_size,
                    offset=offset,
                    additional_types="track",
                )
            except Exception as exc:
                raise PlaylistParseError(f"Failed to fetch Spotify playlist: {exc}") from exc

            items = page.get("items", [])
            if not items:
                break

            for item in items:
                track = item.get("track") or item.get("item") or {}
                # Skip local files / podcast episodes / unavailable rows.
                if not track or track.get("type") != "track":
                    continue
                name = track.get("name") or ""
                artists = track.get("artists") or []
                artist = ", ".join(a.get("name", "") for a in artists).strip(", ")
                if not name or not artist:
                    continue
                images = (track.get("album") or {}).get("images") or []
                art_url = images[0].get("url") if images else ""
                candidates.append(_candidate(
                    conn,
                    track_id=track.get("id") or "",
                    title=name,
                    artist=artist,
                    album_art_url=art_url,
                ))

            if page.get("next"):
                offset += page_size
            else:
                break

    return _dedupe(candidates)


def search_spotify_tracks(query: str, conn=None, limit: int = 10) -> list[dict]:
    """Search Spotify for tracks matching `query`; return candidate dicts.

    Each dict matches the playlist/OCR candidate shape plus a `popularity`
    field (Spotify returns it inline on search, so the dashboard's underrated
    score works without an extra /tracks call).
    """
    from spotify_client import get_client

    q = (query or "").strip()
    if not q:
        raise PlaylistParseError("Empty search query.")

    sp = get_client()
    try:
        page = sp.search(q=q, type="track", limit=limit)
    except Exception as exc:
        raise PlaylistParseError(f"Spotify search failed: {exc}") from exc

    items = (page.get("tracks") or {}).get("items") or []
    candidates: list[dict] = []
    for track in items:
        if not track or track.get("type") not in (None, "track"):
            continue
        name = track.get("name") or ""
        artists = track.get("artists") or []
        artist = ", ".join(a.get("name", "") for a in artists).strip(", ")
        if not name or not artist:
            continue
        images = (track.get("album") or {}).get("images") or []
        art_url = images[0].get("url") if images else ""
        cand = _candidate(
            conn,
            track_id=track.get("id") or "",
            title=name,
            artist=artist,
            album_art_url=art_url,
        )
        cand["popularity"] = track.get("popularity", 50)
        candidates.append(cand)

    return _dedupe(candidates)


# --- Last.fm -----------------------------------------------------------------

def _extract_lastfm(text: str) -> Optional[tuple[str, str]]:
    """Return (method, username) for a recognised Last.fm link, else None.

    Supported shapes:
      last.fm/user/<user>/loved          -> user.getLovedTracks
      last.fm/user/<user>/library/tracks -> user.getTopTracks
      last.fm/user/<user>                -> user.getTopTracks (default)
    """
    m = re.search(r"last\.fm/user/([^/?#]+)(/[^?#]*)?", text.strip(), re.IGNORECASE)
    if not m:
        return None
    username = urllib.parse.unquote(m.group(1))
    tail = (m.group(2) or "").lower()
    if "loved" in tail:
        return ("user.getlovedtracks", username)
    return ("user.gettoptracks", username)


def parse_lastfm_playlist(method: str, username: str, api_key: str,
                          conn=None, limit: int = 100,
                          fetch: Optional[Callable[[str], str]] = None) -> list[dict]:
    """Resolve a Last.fm loved/top track list into candidate dicts."""
    fetcher = fetch or fetch_text
    params = {
        "method": method,
        "user": username,
        "api_key": api_key,
        "format": "json",
        "limit": limit,
    }
    url = _LASTFM_API + "?" + urllib.parse.urlencode(params)
    try:
        data = json.loads(fetcher(url))
    except Exception as exc:
        raise PlaylistParseError(f"Failed to fetch Last.fm tracks: {exc}") from exc

    if "error" in data:
        raise PlaylistParseError(
            f"Last.fm error: {data.get('message', data['error'])}"
        )

    # The container key differs per method (lovedtracks vs toptracks).
    container = data.get("lovedtracks") or data.get("toptracks") or {}
    tracks = container.get("track", [])
    if not isinstance(tracks, list):
        tracks = [tracks]

    candidates: list[dict] = []
    for t in tracks:
        name = (t.get("name") or "").strip()
        artist_obj = t.get("artist") or {}
        artist = (artist_obj.get("name") or artist_obj.get("#text") or "").strip()
        if not name or not artist:
            continue
        art_url = ""
        for img in t.get("image", []):
            if img.get("size") == "extralarge":
                art_url = (img.get("#text") or "").strip()
                break
        if is_placeholder(art_url):
            art_url = ""
        candidates.append(_candidate(
            conn,
            track_id=(t.get("mbid") or "").strip(),
            title=name,
            artist=artist,
            album_art_url=art_url,
        ))

    return _dedupe(candidates)


# --- Dispatcher --------------------------------------------------------------

def parse_playlist(url_or_id: str, conn=None,
                   lastfm_api_key: Optional[str] = None) -> dict:
    """Detect the source of a playlist link and resolve its tracks.

    Returns ``{"source": "spotify"|"lastfm", "tracks": [...]}``.
    Raises PlaylistParseError if the link isn't recognised or the fetch fails.
    """
    text = (url_or_id or "").strip()
    if not text:
        raise PlaylistParseError("No playlist link provided.")

    # Last.fm links are unambiguous (contain last.fm); check them first so a
    # username that happens to be 22 chars can't be mistaken for a Spotify ID.
    if "last.fm" in text.lower():
        parsed = _extract_lastfm(text)
        if not parsed:
            raise PlaylistParseError(
                "Unrecognised Last.fm link. Use a user's loved or library URL, "
                "e.g. https://www.last.fm/user/<name>/loved"
            )
        method, username = parsed
        if not lastfm_api_key:
            raise PlaylistParseError("Last.fm API key is not configured on the server.")
        tracks = parse_lastfm_playlist(method, username, lastfm_api_key, conn=conn)
        return {"source": "lastfm", "tracks": tracks}

    spotify_id = _extract_spotify_playlist_id(text)
    if spotify_id:
        tracks = parse_spotify_playlist(spotify_id, conn=conn)
        return {"source": "spotify", "tracks": tracks}

    raise PlaylistParseError(
        "Couldn't recognise that link. Paste a Spotify playlist URL/ID or a "
        "Last.fm user loved/library URL."
    )
