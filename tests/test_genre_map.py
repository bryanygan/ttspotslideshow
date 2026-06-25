from ingest.genre_map import BUCKETS, bucket_for, is_genre_noise


def test_first_mapped_genre_wins():
    assert bucket_for(["rage", "atl hip hop"]) == "rage"


def test_expanded_catalog_mappings():
    assert bucket_for(["opium"]) == "rage"
    assert bucket_for(["detroit rap"]) == "trap"
    assert bucket_for(["phonk"]) == "trap"
    assert bucket_for(["jersey club"]) == "electronic"
    assert bucket_for(["jazz rap"]) == "boom-bap"


def test_is_genre_noise_flags_non_genre_tags():
    # locations, nationalities, decades, meta tags, and import junk are not genres
    for tag in ["detroit", "american", "usa", "united states", "michigan",
                "2010s", "10s", "seen live", "favorites",
                "funk_add_to_lidarr_batch_22"]:
        assert is_genre_noise(tag), tag


def test_is_genre_noise_keeps_real_genres():
    for tag in ["trap", "hip-hop", "rage", "detroit rap", "r&b", "plugg"]:
        assert not is_genre_noise(tag), tag


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
