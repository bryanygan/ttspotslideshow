from ingest.popularity import normalize_listeners


def test_zero_and_none_are_zero():
    assert normalize_listeners(0) == 0
    assert normalize_listeners(None) == 0
    assert normalize_listeners(-5) == 0


def test_monotonic_and_bounded():
    small = normalize_listeners(300)
    mid = normalize_listeners(50_000)
    big = normalize_listeners(5_000_000)
    assert 0 < small < mid < big <= 100
    assert big == 100  # at the ceiling


def test_huge_clamps_to_100():
    assert normalize_listeners(50_000_000) == 100
