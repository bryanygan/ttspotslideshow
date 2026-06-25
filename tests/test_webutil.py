import json

from webutil import is_placeholder, itunes_search, DEFAULT_ART_HASH


def test_is_placeholder():
    assert is_placeholder(None) is True
    assert is_placeholder("") is True
    assert is_placeholder(f"https://x/{DEFAULT_ART_HASH}.png") is True
    assert is_placeholder("https://x/real.jpg") is False


def test_itunes_search_returns_results_list():
    payload = json.dumps({"results": [{"trackName": "Song", "artistName": "Artist"}]})
    out = itunes_search("song artist", fetch=lambda url: payload)
    assert out and out[0]["trackName"] == "Song"


def test_itunes_search_builds_term_query():
    captured = {}

    def fetch(url):
        captured["url"] = url
        return json.dumps({"results": []})

    itunes_search("destroy me 2hollis", fetch=fetch)
    assert "term=destroy+me+2hollis" in captured["url"]
    assert "entity=song" in captured["url"]


def test_itunes_search_swallows_errors():
    def boom(url):
        raise OSError("network down")
    assert itunes_search("x", fetch=boom) == []
    assert itunes_search("x", fetch=lambda url: "not json {[") == []
