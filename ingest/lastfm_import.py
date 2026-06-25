"""Stream-parse a Last.fm scrobble export into the plays table."""

from datetime import datetime, timezone
from typing import Callable, Iterator, Optional
import xml.etree.ElementTree as ET

import db
from webutil import is_placeholder, fetch_text


def _text(elem, tag: str) -> str:
    child = elem.find(tag)
    return (child.text or "").strip() if child is not None else ""


def iter_scrobbles(xml_path, stats: Optional[dict] = None) -> Iterator[dict]:
    """Yield one dict per real, dated scrobble. Skips now-playing/malformed.

    Uses the root-clear idiom: children of the current <track> stay intact during
    extraction, and the root is cleared after each track so processed (emptied)
    track shells don't accumulate -> constant memory on the full export.

    If a ``stats`` dict is passed, its ``"total"`` key is incremented for every
    <track> element seen (yielded or skipped), so a caller can derive the skipped
    count without a second full parse of the file.
    """
    root = None
    for event, elem in ET.iterparse(str(xml_path), events=("start", "end")):
        if event == "start":
            if root is None:
                root = elem
            continue
        if elem.tag != "track":
            continue
        if stats is not None:
            stats["total"] = stats.get("total", 0) + 1
        try:
            if elem.get("nowplaying") == "true":
                continue
            date_el = elem.find("date")
            if date_el is None or not date_el.get("uts"):
                continue
            artist = _text(elem, "artist")
            name = _text(elem, "name")
            if not artist or not name:
                continue

            uts = int(date_el.get("uts"))
            track_mbid = _text(elem, "mbid")
            art_url = ""
            for img in elem.findall("image"):
                if img.get("size") == "extralarge":
                    art_url = (img.text or "").strip()
                    break
            if is_placeholder(art_url):
                art_url = ""

            yield {
                "track_id": track_mbid,
                "name": name,
                "artist": artist,
                "album_art_url": art_url,
                "played_at": datetime.fromtimestamp(uts, timezone.utc).isoformat(),
                "played_at_unix": uts,
            }
        finally:
            elem.clear()
            if root is not None:
                root.clear()


def import_scrobbles(conn, xml_path) -> tuple[int, int]:
    """Import all scrobbles from xml_path. Returns (imported, skipped).

    Single-pass: ``stats["total"]`` counts every <track> element while iterating,
    and ``skipped`` is the difference from the dated/valid candidates we attempted
    to insert. (``imported`` <= ``candidates`` because of duplicate INSERT-IGNOREs;
    ``skipped`` counts only XML-filtered tracks, not DB-rejected duplicates.)
    """
    stats = {"total": 0}
    imported = 0
    candidates = 0
    for row in iter_scrobbles(xml_path, stats=stats):
        candidates += 1
        if db.insert_lastfm_play(conn, **row):
            imported += 1
    skipped = stats["total"] - candidates
    return imported, skipped


def import_recent_from_api(
    conn,
    api_key: str,
    username: str,
    since_unix: Optional[int] = None,
    fetch: Optional[Callable[[str], str]] = None,
) -> int:
    """Fetch recent scrobbles from Last.fm API and insert them into the DB.

    Returns the number of new plays added.
    """
    import json
    import urllib.parse

    fetcher = fetch or fetch_text
    added = 0
    page = 1

    while True:
        params = {
            "method": "user.getrecenttracks",
            "user": username,
            "api_key": api_key,
            "format": "json",
            "limit": 200,
            "page": page,
        }
        if since_unix is not None:
            params["from"] = since_unix

        url = "https://ws.audioscrobbler.com/2.0/?" + urllib.parse.urlencode(params)
        try:
            raw = fetcher(url)
            data = json.loads(raw)
        except Exception:
            break

        if "error" in data:
            break

        recent = data.get("recenttracks", {})
        tracks = recent.get("track", [])
        if not isinstance(tracks, list):
            tracks = [tracks]

        if not tracks:
            break

        for track in tracks:
            if track.get("@attr", {}).get("nowplaying") == "true":
                continue
            date_el = track.get("date")
            if not date_el or not date_el.get("uts"):
                continue

            try:
                uts = int(date_el["uts"])
            except (TypeError, ValueError):
                continue

            artist = track.get("artist", {}).get("#text", "").strip()
            name = track.get("name", "").strip()
            if not artist or not name:
                continue

            track_id = track.get("mbid", "").strip()

            art_url = ""
            for img in track.get("image", []):
                if img.get("size") == "extralarge":
                    art_url = img.get("#text", "").strip()
                    break
            if is_placeholder(art_url):
                art_url = ""

            played_at = datetime.fromtimestamp(uts, timezone.utc).isoformat()

            was_new = db.insert_lastfm_play(
                conn,
                track_id=track_id,
                name=name,
                artist=artist,
                album_art_url=art_url,
                played_at=played_at,
                played_at_unix=uts,
            )
            if was_new:
                added += 1

        # Check if we should stop paging
        attr = recent.get("@attr", {})
        try:
            total_pages = int(attr.get("totalPages", 1))
        except (TypeError, ValueError):
            total_pages = 1

        if page >= total_pages:
            break
        page += 1

    return added
