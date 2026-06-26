from slideshow.art_resolve import resolve_art_url, _is_itunes_url


def _track(artist="ArtistName", title="TrackTitle", art=""):
    return {"artist": artist, "title": title, "album_art_url": art}


def test_use_stored_spotify_url():
    # Stored valid URL should be returned immediately
    valid_url = "https://i.scdn.co/image/abc"
    out = resolve_art_url(_track(art=valid_url))
    assert out == valid_url


def test_fallback_to_spotify_search(monkeypatch):
    # If stored url is a Last.fm url, it should trigger search_spotify_art
    called = []
    def mock_search(artist, title):
        called.append((artist, title))
        return "https://spotify/mock_image.jpg"

    import slideshow.art_resolve as ar
    monkeypatch.setattr(ar, "search_spotify_art", mock_search)

    out = resolve_art_url(_track(art="https://lastfm/300.jpg"))
    assert out == "https://spotify/mock_image.jpg"
    assert called == [("ArtistName", "TrackTitle")]


def test_empty_if_no_spotify_or_itunes_cover(monkeypatch):
    # When Spotify returns None and iTunes returns nothing, resolve_art_url returns ""
    import slideshow.art_resolve as ar
    monkeypatch.setattr(ar, "search_spotify_art", lambda a, t: None)
    # Pass a fetch mock that returns empty iTunes results
    empty_itunes = lambda url: '{"resultCount":0,"results":[]}'

    out = resolve_art_url(_track(art="https://lastfm/300.jpg"), fetch=empty_itunes)
    assert out == ""


def test_fallback_to_itunes_when_spotify_unavailable(monkeypatch):
    # When fetch is provided (simulating no Spotify), iTunes is tried and its URL returned
    itunes_response = (
        '{"resultCount":1,"results":[{"artworkUrl100":"https://is1-ssl.mzstatic.com/image/thumb/Music/ab/cd/ef/100x100bb.jpg"}]}'
    )
    fetch_mock = lambda url: itunes_response

    track = _track(art="https://lastfm/300.jpg")
    out = resolve_art_url(track, fetch=fetch_mock)
    # Should upgrade 100x100 to 1000x1000
    assert "1000x1000" in out
    assert _is_itunes_url(out)


def test_is_itunes_url():
    assert _is_itunes_url("https://is1-ssl.mzstatic.com/image/thumb/Music/1000x1000bb.jpg")
    assert not _is_itunes_url("https://i.scdn.co/image/abc")
    assert not _is_itunes_url("")


def test_cache_avoids_second_search(monkeypatch):
    called_count = 0
    def mock_search(artist, title):
        nonlocal called_count
        called_count += 1
        return "https://spotify/mock_image.jpg"

    import slideshow.art_resolve as ar
    monkeypatch.setattr(ar, "search_spotify_art", mock_search)

    cache = {}
    track = _track(art="")
    
    out1 = resolve_art_url(track, cache=cache)
    out2 = resolve_art_url(track, cache=cache)
    
    assert out1 == "https://spotify/mock_image.jpg"
    assert out2 == "https://spotify/mock_image.jpg"
    assert called_count == 1
