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
    "west coast hip hop": "hip-hop", "experimental hip hop": "hip-hop",
    "g-funk": "hip-hop", "g funk": "hip-hop",
    # rage / opium scene
    "opium": "rage", "rage rap": "rage",
    # more trap (regional scenes + phonk/crunk all sit in the trap sound)
    "phonk": "trap", "detroit rap": "trap", "flint rap": "trap",
    "memphis rap": "trap", "crunk": "trap", "plugg & b": "plugg",
    # jazz/abstract rap -> boom bap lineage
    "jazz rap": "boom-bap", "abstract hip hop": "boom-bap",
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
    # electronic (cont.)
    "jersey club": "electronic", "digicore": "electronic",
    "glitchcore": "electronic", "drum and bass": "electronic",
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


# Last.fm tags are user-supplied and messy: many are locations, nationalities,
# decades, or meta labels rather than genres. We drop these before bucketing so a
# location-only artist stays 'unknown' (honest "no genre") instead of becoming a
# false 'other'. Note this is only applied to the Last.fm path — Spotify genres are
# already clean.
_NON_GENRE_TAGS: frozenset[str] = frozenset({
    # nationalities / countries
    "american", "british", "english", "canadian", "australian", "french",
    "german", "swedish", "norwegian", "italian", "japanese", "korean", "irish",
    "usa", "uk", "united states", "america", "canada", "australia", "england",
    # US regions / cities commonly tagged
    "detroit", "michigan", "flint", "atlanta", "atl", "chicago", "memphis",
    "new york", "new jersey", "california", "los angeles", "houston", "texas",
    "florida", "brooklyn", "compton", "the bronx", "bronx", "west coast",
    "east coast", "southern", "midwest", "uk rap scene",
    # meta / non-genre
    "seen live", "favorites", "favourites", "favorite", "favourite", "spotify",
    "beautiful", "love", "awesome", "amazing", "cool", "chill", "vibe", "vibes",
    "music", "male vocalists", "female vocalists", "under 2000 listeners",
})


def is_genre_noise(tag: str) -> bool:
    """True for Last.fm tags that are locations / decades / meta, not genres."""
    t = tag.strip().lower()
    if not t:
        return True
    if t in _NON_GENRE_TAGS:
        return True
    if "lidarr" in t or "add_to_" in t:  # known library-import junk tags
        return True
    # decades / years: "90s", "2010s", "1999", "10s"
    stripped = t[:-1] if t.endswith("s") else t
    if stripped.isdigit():
        return True
    return False
