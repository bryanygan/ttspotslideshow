"""Stream-parse a Last.fm scrobble export into the plays table."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
import xml.etree.ElementTree as ET

import db
from render.art import is_placeholder


def _text(elem, tag: str) -> str:
    child = elem.find(tag)
    return (child.text or "").strip() if child is not None else ""


def iter_scrobbles(xml_path) -> Iterator[dict]:
    """Yield one dict per real, dated scrobble. Skips now-playing/malformed."""
    for _, elem in ET.iterparse(str(xml_path), events=("end",)):
        if elem.tag != "track":
            continue
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


def import_scrobbles(conn, xml_path) -> tuple[int, int]:
    """Import all scrobbles from xml_path. Returns (imported, skipped)."""
    # Count total <track> elements to derive skipped = total - imported_candidates.
    imported = 0
    candidates = 0
    for row in iter_scrobbles(xml_path):
        candidates += 1
        if db.insert_lastfm_play(conn, **row):
            imported += 1
    total_tracks = _count_tracks(xml_path)
    skipped = total_tracks - candidates
    return imported, skipped


def _count_tracks(xml_path) -> int:
    n = 0
    for _, elem in ET.iterparse(str(xml_path), events=("end",)):
        if elem.tag == "track":
            n += 1
        elem.clear()
    return n
