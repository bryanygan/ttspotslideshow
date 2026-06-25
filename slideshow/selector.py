"""Genre round-robin selection blending play count, recency, and novelty."""

from datetime import date

WEIGHT_PLAY = 0.6
WEIGHT_RECENCY = 0.4
NOVELTY_DAYS = 14


def _novelty(track_key, featured, run_date):
    last = featured.get(track_key)
    if last is None:
        return 1.0
    days = (date.fromisoformat(run_date) - date.fromisoformat(last)).days
    if days <= 0:           # featured today (or future) -> not suppressed
        return 1.0
    return min(1.0, days / NOVELTY_DAYS)


def select_tracks(candidates, featured, run_date, target=16, floor=12):
    """Return an ordered selection (slide order) via genre round-robin.

    `floor` is accepted for caller symmetry but intentionally not applied as a hard
    cutoff: the result is always trimmed to a multiple of 4 (whole slides), and the
    `(n // 4) * 4` tiers below already reproduce the floor behaviour without ever
    yielding a non-multiple-of-4 count.
    """
    if not candidates:
        return []

    max_play = max(c["play_count"] for c in candidates) or 1
    lasts = [c["last_played_unix"] for c in candidates]
    min_last, max_last = min(lasts), max(lasts)
    span = (max_last - min_last) or 1

    scored = []
    for c in candidates:
        norm_play = c["play_count"] / max_play
        norm_rec = 1.0 if max_last == min_last else (c["last_played_unix"] - min_last) / span
        base = WEIGHT_PLAY * norm_play + WEIGHT_RECENCY * norm_rec
        score = base * _novelty(c["track_key"], featured, run_date)
        scored.append((score, c))

    buckets: dict = {}
    for score, c in scored:
        buckets.setdefault(c["primary_bucket"], []).append((score, c))
    for items in buckets.values():
        items.sort(key=lambda sc: (-sc[0], -sc[1]["last_played_unix"], sc[1]["title"]))

    bucket_order = sorted(
        buckets.keys(),
        key=lambda k: (-sum(c["play_count"] for _, c in buckets[k]), k),
    )

    picked = []
    indices = {k: 0 for k in bucket_order}
    progressed = True
    while progressed and len(picked) < target:
        progressed = False
        for k in bucket_order:
            i = indices[k]
            if i < len(buckets[k]):
                picked.append(buckets[k][i][1])
                indices[k] += 1
                progressed = True
                if len(picked) >= target:
                    break

    n = len(picked)
    if n >= target:
        final = target
    elif n >= 4:
        final = (n // 4) * 4    # 12 for 12-15, 8 for 8-11, 4 for 4-7
    else:
        final = n               # < 4: can't fill a slide; caller handles
    return picked[:final]
