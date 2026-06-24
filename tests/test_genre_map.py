from ingest.genre_map import BUCKETS, bucket_for


def test_first_mapped_genre_wins():
    assert bucket_for(["rage", "atl hip hop"]) == "rage"


def test_skips_unmapped_then_matches():
    assert bucket_for(["canadian hip hop", "rap"]) == "hip-hop"


def test_subgenre_mapping():
    assert bucket_for(["pluggnb"]) == "plugg"
    assert bucket_for(["uk drill"]) == "drill"
    assert bucket_for(["contemporary r&b"]) == "r&b"


def test_other_when_nonempty_but_unmapped():
    assert bucket_for(["polka", "yodeling"]) == "other"


def test_unknown_when_empty():
    assert bucket_for([]) == "unknown"


def test_all_mapped_values_are_valid_buckets():
    from ingest.genre_map import GENRE_TO_BUCKET
    assert set(GENRE_TO_BUCKET.values()) <= set(BUCKETS)
