import json

from slideshow.art_resolve import resolve_art_url

ITUNES_HIT = json.dumps({
    "results": [{"artworkUrl100": "https://is1.example/abc/100x100bb.jpg"}]
})


def _track(artist="2hollis", title="destroy me", art="https://lastfm/300.jpg"):
    return {"artist": artist, "title": title, "album_art_url": art}


def test_itunes_hit_rewritten_to_600():
    out = resolve_art_url(_track(), fetch=lambda url: ITUNES_HIT)
    assert out == "https://is1.example/abc/600x600bb.jpg"


def test_no_results_falls_back_to_lastfm():
    out = resolve_art_url(_track(), fetch=lambda url: json.dumps({"results": []}))
    assert out == "https://lastfm/300.jpg"


def test_error_falls_back_then_empty():
    def boom(url):
        raise OSError("network down")
    assert resolve_art_url(_track(), fetch=boom) == "https://lastfm/300.jpg"
    assert resolve_art_url(_track(art=""), fetch=boom) == ""


def test_malformed_json_falls_back_to_lastfm():
    out = resolve_art_url(_track(), fetch=lambda url: "not json {[")
    assert out == "https://lastfm/300.jpg"


def test_cache_avoids_second_fetch():
    calls = []

    def fetch(url):
        calls.append(url)
        return ITUNES_HIT

    cache = {}
    resolve_art_url(_track(), fetch=fetch, cache=cache)
    resolve_art_url(_track(), fetch=fetch, cache=cache)
    assert len(calls) == 1
