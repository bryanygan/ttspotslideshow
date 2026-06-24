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


def test_handles_missing_tags_gracefully():
    tags = get_top_tags("X", "KEY", fetch=lambda url: json.dumps({"toptags": {}}))
    assert tags == []


def test_handles_error_payload():
    err = json.dumps({"error": 6, "message": "not found"})
    tags = get_top_tags("X", "KEY", fetch=lambda url: err)
    assert tags == []
