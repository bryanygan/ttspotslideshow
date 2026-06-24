from slideshow.selector import select_tracks


def _cand(track_key, bucket, play_count, last_unix, title=None):
    return {
        "track_key": track_key,
        "primary_bucket": bucket,
        "play_count": play_count,
        "last_played_unix": last_unix,
        "title": title or track_key,
        "artist": "a",
        "track_id": "",
        "album_art_url": "",
    }


def test_round_robin_interleaves_genres():
    cands = [
        _cand("r1", "rage", 10, 100), _cand("r2", "rage", 9, 100),
        _cand("t1", "trap", 8, 100), _cand("p1", "pop", 7, 100),
    ]
    out = select_tracks(cands, {}, "2026-06-24", target=4, floor=4)
    # First pass takes one from each bucket before a second rage track.
    assert [c["primary_bucket"] for c in out][:3] == ["rage", "trap", "pop"]
    assert out[-1]["track_key"] == "r2"  # second rage track comes last


def test_recently_featured_is_suppressed_vs_unfeatured_peer():
    cands = [
        _cand("hot", "rage", 10, 100),   # higher plays but featured yesterday
        _cand("fresh", "rage", 8, 100),  # fewer plays, never featured
    ]
    featured = {"hot": "2026-06-23"}     # 1 day before run_date
    out = select_tracks(cands, featured, "2026-06-24", target=1, floor=1)
    assert out[0]["track_key"] == "fresh"


def test_featured_today_not_suppressed_same_day_determinism():
    cands = [_cand("hot", "rage", 10, 100), _cand("fresh", "rage", 8, 100)]
    featured = {"hot": "2026-06-24"}     # featured TODAY -> novelty 1.0
    out = select_tracks(cands, featured, "2026-06-24", target=1, floor=1)
    assert out[0]["track_key"] == "hot"  # plays win; today's feature isn't penalized


def test_recency_lifts_newer_play():
    cands = [
        _cand("old", "rage", 10, 100),
        _cand("new", "rage", 10, 999),   # equal plays, more recent
    ]
    out = select_tracks(cands, {}, "2026-06-24", target=1, floor=1)
    assert out[0]["track_key"] == "new"


def test_count_resolution_to_multiple_of_four():
    cands = [_cand(f"k{i}", "rage" if i % 2 else "trap", 5, 100 + i) for i in range(14)]
    out = select_tracks(cands, {}, "2026-06-24", target=16, floor=12)
    assert len(out) == 12  # 14 available -> largest multiple of 4 >= floor


def test_deterministic_repeat():
    cands = [_cand(f"k{i}", "rage", 5, 100 + i) for i in range(6)]
    a = select_tracks(cands, {}, "2026-06-24", target=16, floor=12)
    b = select_tracks(cands, {}, "2026-06-24", target=16, floor=12)
    assert [c["track_key"] for c in a] == [c["track_key"] for c in b]
