import json

from ingest.lastfm_client import get_top_tags

FAKE = json.dumps({
    "toptags": {"tag": [
        {"name": "Hip-Hop", "count": 100},
        {"name": "rage", "count": 40},
        {"name": "noise", "count": 2},
    ]}
})


def test_returns_lowercased_tags_above_threshold():
    captured = {}

    def fetch(url):
        captured["url"] = url
        return FAKE

    tags = get_top_tags("2hollis", "KEY", fetch=fetch, min_weight=10)
    assert tags == ["hip-hop", "rage"]  # 'noise' (2) dropped
    assert "artist.gettoptags" in captured["url"].lower()
    assert "api_key=KEY" in captured["url"]


def test_default_min_weight_keeps_low_weight_genre_tags():
    # Real genre tags can sit below the old hard floor of 10 (e.g. plugg=3);
    # the default threshold is now low enough to keep them.
    fake = json.dumps({"toptags": {"tag": [
        {"name": "Rap", "count": 100},
        {"name": "plugg", "count": 3},
    ]}})
    tags = get_top_tags("x", "KEY", fetch=lambda url: fake)  # default min_weight
    assert tags == ["rap", "plugg"]


def test_handles_missing_tags_gracefully():
    tags = get_top_tags("X", "KEY", fetch=lambda url: json.dumps({"toptags": {}}))
    assert tags == []


def test_handles_error_payload():
    err = json.dumps({"error": 6, "message": "not found"})
    tags = get_top_tags("X", "KEY", fetch=lambda url: err)
    assert tags == []


def test_non_numeric_count_does_not_raise():
    fake = json.dumps({"toptags": {"tag": [
        {"name": "trap", "count": "lots"},   # bogus count -> treated as 0
        {"name": "rap", "count": 50},
    ]}})
    tags = get_top_tags("X", "KEY", fetch=lambda url: fake, min_weight=10)
    assert tags == ["rap"]  # 'trap' dropped (weight 0), no exception
