import json
import pytest
from slideshow.ocr import is_valid_match, parse_tracks_from_lines, _is_duration


def test_is_duration_distinguishes_timestamps_from_titles():
    assert _is_duration("3:45")
    assert _is_duration("12:07")
    # Titles that merely contain a colon must NOT be treated as durations.
    assert not _is_duration("Re: Stacks")
    assert not _is_duration("Bonus: The Sequel")
    assert not _is_duration("destroy me")


def test_colon_titles_are_not_skipped():
    # "Re: Stacks" contains a colon but is a real title; it should be paired and
    # resolved, not dropped as a duration line.
    lines = ["Re: Stacks", "Bon Iver"]
    payload = {
        "trackName": "Re: Stacks",
        "artistName": "Bon Iver",
        "artworkUrl100": "https://x100x100.jpg",
        "trackId": 999,
    }
    fetch = lambda url: json.dumps({"results": [payload]})
    tracks = parse_tracks_from_lines(lines, conn=None, fetch=fetch)
    assert len(tracks) == 1
    assert tracks[0]["title"] == "Re: Stacks"
    assert tracks[0]["artist"] == "Bon Iver"


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
