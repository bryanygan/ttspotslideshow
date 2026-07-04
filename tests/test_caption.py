from slideshow.caption import generate_caption, get_suggested_hashtags

TRACKS = [
    {"artist": "Kendrick Lamar", "title": "Song A", "primary_bucket": "Hip-Hop"},
    {"artist": "Travis Scott", "title": "Song B", "primary_bucket": "Hip-Hop"},
    {"artist": "SZA", "title": "Song C", "primary_bucket": "R&B"},
]


def test_generate_caption_empty_tracks():
    assert generate_caption([]) == ""


def test_generate_caption_default_no_style_profile():
    caption = generate_caption(TRACKS)
    assert "Kendrick Lamar" in caption
    assert "#hiphop" in caption
    assert "\U0001f3a7" in caption  # default emoji


def test_generate_caption_uses_style_profile_emoji():
    style_profile = {"top_emojis": ["\U0001f525"], "top_hashtags": []}
    caption = generate_caption(TRACKS, style_profile=style_profile)
    assert "\U0001f525" in caption
    assert "\U0001f3a7" not in caption


def test_generate_caption_uses_style_profile_hashtags_as_filler():
    style_profile = {"top_emojis": [], "top_hashtags": ["#bghyped", "#recap"]}
    caption = generate_caption(TRACKS, style_profile=style_profile)
    assert "#bghyped" in caption


def test_get_suggested_hashtags_falls_back_to_style_profile_when_no_genres():
    style_profile = {"top_hashtags": ["#bghyped", "#recap", "#weekly"]}
    tags = get_suggested_hashtags([{"artist": "X"}], max_tags=3, style_profile=style_profile)
    assert tags == ["#bghyped", "#recap", "#weekly"]


def test_get_suggested_hashtags_falls_back_to_filler_tags_without_profile():
    tags = get_suggested_hashtags([{"artist": "X"}], max_tags=3)
    assert tags == ["#nowplaying", "#music", "#fyp"]
