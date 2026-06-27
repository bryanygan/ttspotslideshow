"""Resolve a track's global popularity: Last.fm primary, ListenBrainz fallback.

Raw listener counts are log-normalized into a 0-100 score so the dashboard's
"underrated" ratio (play_count / popularity) is meaningful again after Spotify
removed track.popularity.
"""

import json
import math
import urllib.parse
from datetime import datetime, timezone
from typing import Callable, Optional

from webutil import fetch_text

POPULARITY_CEIL = 5_000_000  # ~ a megahit's Last.fm listener count -> score 100

_LASTFM = "https://ws.audioscrobbler.com/2.0/"
_LB_LOOKUP = "https://api.listenbrainz.org/1/metadata/lookup/"
_LB_POPULARITY = "https://api.listenbrainz.org/1/popularity/recording"


def normalize_listeners(listeners: Optional[int]) -> int:
    """Log-scale a raw listener count into a 0-100 popularity score."""
    if not listeners or listeners < 0:
        return 0
    score = 100 * math.log10(listeners + 1) / math.log10(POPULARITY_CEIL + 1)
    return max(0, min(100, round(score)))
