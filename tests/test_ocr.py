import json
import pytest
from slideshow.ocr import is_valid_match, parse_tracks_from_lines


def test_is_valid_match():
    # Direct pairing: L1 = Title, L2 = Artist
    res = {"trackName": "Destroy Me", "artistName": "2hollis"}
    assert is_valid_match("destroy me", "2hollis", res)

    # Reverse pairing: L1 = Artist, L2 = Title
    assert is_valid_match("2hollis", "destroy me", res)

    # Overlap / combined: merged lines containing both
    assert is_valid_match("Destroy Me by 2hollis", "Next Track", res)

    # Invalid: no match
    res_other = {"trackName": "14", "artistName": "Tana"}
    assert not is_valid_match("destroy me", "2hollis", res_other)


def test_parse_tracks_from_lines_mocked():
    lines = ["destroy me", "2hollis", "14", "Tana", "Some Garbage Line", "3:45"]

    # Mock iTunes search to return payloads
    db_results = {
        "destroy me 2hollis": {
            "trackName": "Destroy Me",
            "artistName": "2hollis",
            "artworkUrl100": "https://url100x100.jpg",
            "trackId": 12345,
        },
        "14 Tana": {
            "trackName": "14",
            "artistName": "Tana",
            "artworkUrl100": "https://tana100x100.jpg",
            "trackId": 67890,
        },
    }

    def fetch(url):
        # Extract term from url
        # e.g., url = "https://itunes.apple.com/search?term=destroy+me+2hollis..."
        import urllib.parse

        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query).get("term", [""])[0]
        if query in db_results:
            return json.dumps({"results": [db_results[query]]})
        return json.dumps({"results": []})

    tracks = parse_tracks_from_lines(lines, conn=None, fetch=fetch)

    assert len(tracks) == 2
    assert tracks[0]["title"] == "Destroy Me"
    assert tracks[0]["artist"] == "2hollis"
    assert tracks[0]["album_art_url"] == "https://url600x600.jpg"
    assert tracks[0]["track_id"] == "12345"

    assert tracks[1]["title"] == "14"
    assert tracks[1]["artist"] == "Tana"
    assert tracks[1]["album_art_url"] == "https://tana600x600.jpg"
    assert tracks[1]["track_id"] == "67890"
