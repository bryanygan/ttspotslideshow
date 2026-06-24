from text_norm import normalize


def test_lowercases_and_strips():
    assert normalize("  Playboi CARTI ") == "playboi carti"


def test_collapses_internal_whitespace():
    assert normalize("Lil   Uzi\tVert") == "lil uzi vert"


def test_trims_remaster_suffix():
    assert normalize("Bohemian Rhapsody - 2011 Remaster") == "bohemian rhapsody"
    assert normalize("Song - Single Version") == "song"


def test_does_not_merge_distinct_titles():
    assert normalize("Location") != normalize("Locations")


def test_empty_safe():
    assert normalize("") == ""


def test_does_not_strip_version_when_more_segments_follow():
    # "Acoustic Version" here is meaningful, not a remaster tag, because a
    # further " - Live" segment follows — must NOT be stripped.
    assert normalize("Song - Acoustic Version - Live") == "song - acoustic version - live"
