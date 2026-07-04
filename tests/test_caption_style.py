import json

from ingest.caption_style import (
    analyze_captions,
    load_captions,
    load_style_profile,
    save_style_profile,
)


def test_analyze_captions_empty():
    profile = analyze_captions([])
    assert profile["sample_size"] == 0
    assert profile["top_hashtags"] == []
    assert profile["top_emojis"] == []


def test_analyze_captions_counts_hashtags_and_emoji():
    captions = [
        "weekly recap \U0001f3a7 #fyp #hiphop #fyp",
        "another one \U0001f3a7 #fyp #rap",
    ]
    profile = analyze_captions(captions)
    assert profile["sample_size"] == 2
    assert profile["top_hashtags"][0] == "#fyp"
    assert "#hiphop" in profile["top_hashtags"]
    assert profile["top_emojis"][0] == "\U0001f3a7"
    assert profile["avg_hashtag_count"] == 2.5


def test_analyze_captions_common_openers():
    captions = ["weekly recap one", "weekly recap two", "different opener"]
    profile = analyze_captions(captions)
    assert profile["common_openers"][0] == "weekly"


def test_load_captions_accepts_plain_strings(tmp_path):
    path = tmp_path / "captions.json"
    path.write_text(json.dumps(["hello #fyp", "world #fyp"]), encoding="utf-8")
    assert load_captions(path) == ["hello #fyp", "world #fyp"]


def test_load_captions_accepts_extract_script_shape(tmp_path):
    path = tmp_path / "captions.json"
    path.write_text(
        json.dumps(
            [
                {"id": "1", "caption": "hello #fyp"},
                {"id": "2", "description": "world #fyp"},
                {"id": "3", "caption": ""},
            ]
        ),
        encoding="utf-8",
    )
    assert load_captions(path) == ["hello #fyp", "world #fyp"]


def test_save_and_load_style_profile_roundtrip(tmp_path):
    path = tmp_path / "profile.json"
    profile = analyze_captions(["hello #fyp \U0001f3a7"])
    save_style_profile(profile, path)
    loaded = load_style_profile(path)
    assert loaded == profile


def test_load_style_profile_missing_file_returns_none(tmp_path):
    assert load_style_profile(tmp_path / "missing.json") is None
