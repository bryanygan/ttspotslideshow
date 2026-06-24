"""Map Spotify/Last.fm micro-genres into a curated hybrid bucket set.

Buckets split hip-hop into meaningful subgenres (the bulk of the catalog) while
keeping broad buckets for everything else, so "across different genres" yields
real variety. The map is a starting set, extend it as new genres appear.
"""

BUCKETS: tuple[str, ...] = (
    "rage", "trap", "drill", "plugg", "boom-bap", "melodic-rap", "hip-hop",
    "pop", "r&b", "rock", "electronic", "indie", "country", "latin",
    "other", "unknown",
)

GENRE_TO_BUCKET: dict[str, str] = {
    # rage
    "rage": "rage",
    # plugg
    "plugg": "plugg", "pluggnb": "plugg",
    # drill
    "drill": "drill", "uk drill": "drill", "chicago drill": "drill",
    "brooklyn drill": "drill", "bronx drill": "drill",
    # melodic / emo / cloud
    "melodic rap": "melodic-rap", "emo rap": "melodic-rap",
    "cloud rap": "melodic-rap", "sad rap": "melodic-rap",
    # trap
    "trap": "trap", "dark trap": "trap", "atl trap": "trap",
    "atl hip hop": "trap", "southern hip hop": "trap", "gangster rap": "trap",
    # boom bap / old school
    "boom bap": "boom-bap", "old school hip hop": "boom-bap",
    "east coast hip hop": "boom-bap", "golden age hip hop": "boom-bap",
    "hardcore hip hop": "boom-bap", "conscious hip hop": "boom-bap",
    # generic rap
    "rap": "hip-hop", "hip hop": "hip-hop", "hip-hop": "hip-hop",
    "pop rap": "hip-hop", "underground hip hop": "hip-hop",
    "west coast hip hop": "hip-hop",
    # r&b
    "r&b": "r&b", "contemporary r&b": "r&b", "alternative r&b": "r&b",
    "neo soul": "r&b", "soul": "r&b",
    # pop
    "pop": "pop", "dance pop": "pop", "electropop": "pop", "art pop": "pop",
    "indie pop": "pop",
    # rock
    "rock": "rock", "alternative rock": "rock", "classic rock": "rock",
    "hard rock": "rock", "punk": "rock", "metal": "rock", "grunge": "rock",
    # electronic
    "edm": "electronic", "electronic": "electronic", "house": "electronic",
    "dubstep": "electronic", "techno": "electronic", "future bass": "electronic",
    "hyperpop": "electronic",
    # indie
    "indie": "indie", "indie rock": "indie", "bedroom pop": "indie",
    "indietronica": "indie",
    # country
    "country": "country", "country rap": "country", "contemporary country": "country",
    # latin
    "latin": "latin", "reggaeton": "latin", "latin trap": "latin",
    "trap latino": "latin", "rap latina": "latin",
}


def bucket_for(genres: list[str]) -> str:
    """Return the bucket of the first genre that maps; 'other'/'unknown' otherwise."""
    for genre in genres:
        bucket = GENRE_TO_BUCKET.get(genre.strip().lower())
        if bucket:
            return bucket
    return "other" if genres else "unknown"
