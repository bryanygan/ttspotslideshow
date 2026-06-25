"""Resolve the candidate track pool from a recent window, widening if thin."""

import time

import db

DAY_SECONDS = 86400


def resolve_window(conn, target=16, floor=12, steps=(2, 4, 7, 14, 30), now_unix=None):
    """Return (candidates, days_used). Try each window; stop at the first with
    >= target unique tracks, else return the largest (last step)."""
    if now_unix is None:
        now_unix = int(time.time())

    candidates: list = []
    days_used = steps[-1] if steps else 0
    for days in steps:
        start = now_unix - days * DAY_SECONDS
        candidates = db.window_track_candidates(conn, start)
        days_used = days
        if len(candidates) >= target:
            break
    return candidates, days_used
