"""CLI: fill the track_popularity cache (Last.fm primary, ListenBrainz fallback).

Resumable — by default only fetches tracks with no cached row. Use --refresh to
re-fetch all. Run: python -m ingest.enrich_popularity
"""

import logging
from datetime import datetime, timezone

import config
import db
from text_norm import normalize
from ingest.popularity import resolve_popularity
from logsetup import setup_logging

LOG = logging.getLogger("enrich_popularity")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _all_canonical_track_keys(conn) -> list:
    """Distinct canonical track_keys with their display artist/title."""
    seen = set()
    out = []
    for r in db.canonical_plays(conn):
        artist, title = r["artist"], r["name"]
        track_key = normalize(artist) + "\t" + normalize(title)
        if track_key in seen:
            continue
        seen.add(track_key)
        out.append((track_key, artist, title))
    return out


def enrich_all_popularity(conn, *, lastfm_api_key, listenbrainz_token,
                          fetch=None, sleep=None, progress=None,
                          refresh=False) -> dict:
    """Resolve + cache popularity for tracks. Resumable unless refresh=True."""
    targets = _all_canonical_track_keys(conn)
    if not refresh:
        missing = set(db.track_keys_missing_popularity(conn))
        targets = [t for t in targets if t[0] in missing]

    summary = {"lastfm": 0, "listenbrainz": 0, "none": 0, "processed": 0}
    total = len(targets)
    for i, (track_key, artist, title) in enumerate(targets):
        res = resolve_popularity(
            artist, title,
            lastfm_api_key=lastfm_api_key,
            listenbrainz_token=listenbrainz_token,
            fetch=fetch,
        )
        db.upsert_track_popularity(
            conn, track_key=track_key, listeners=res["listeners"],
            popularity=res["popularity"], source=res["source"],
            fetched_at=_now_iso(),
        )
        summary[res["source"]] += 1
        summary["processed"] += 1
        if progress:
            progress(i + 1, total)
        if sleep:
            sleep(0.25)  # be polite between network calls
    conn.commit()
    return summary


def build_parser():
    import argparse

    parser = argparse.ArgumentParser(
        description="Fill the track_popularity cache (Last.fm + ListenBrainz)."
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="re-fetch popularity for every track, not just uncached ones.",
    )
    return parser


def main() -> None:
    import time

    args = build_parser().parse_args()
    setup_logging("enrich_popularity")
    if not config.LASTFM_API_KEY:
        LOG.warning("LAST_FM_API_KEY not set — Last.fm popularity unavailable.")
    if not config.LISTENBRAINZ_TOKEN:
        LOG.warning("LISTENBRAINZ_TOKEN not set — ListenBrainz fallback disabled.")

    def progress(done, total):
        if done % 25 == 0 or done == total:
            LOG.info("  popularity: %d/%d", done, total)

    LOG.info("Enriching track popularity (%s, resumable)...",
             "refresh-all" if args.refresh else "missing-only")
    with db.connect() as conn:
        summary = enrich_all_popularity(
            conn,
            lastfm_api_key=config.LASTFM_API_KEY,
            listenbrainz_token=config.LISTENBRAINZ_TOKEN,
            sleep=time.sleep, progress=progress, refresh=args.refresh,
        )
    LOG.info("Done. processed=%d lastfm=%d listenbrainz=%d none=%d",
             summary["processed"], summary["lastfm"],
             summary["listenbrainz"], summary["none"])


if __name__ == "__main__":
    main()
