"""CLI: migrate + import Last.fm history + enrich genres, then print a summary.

Run: python -m ingest.enrich_cli
"""

import logging

import config
import db
from ingest.lastfm_import import import_scrobbles
from ingest.genres import enrich_all
from spotify_client import get_client
from logsetup import setup_logging

LOG = logging.getLogger("enrich")


def run_ingest(conn, xml_path, spotify_client, lastfm_api_key, fetch=None,
               sleep=None, progress=None, skip_spotify=False, refresh=False) -> dict:
    """Migrate, import, and enrich against an open connection. Returns a summary."""
    db.migrate(conn)
    imported, skipped = import_scrobbles(conn, xml_path)
    conn.commit()  # persist the import before the long (resumable) enrichment
    enriched = enrich_all(
        conn, spotify_client, lastfm_api_key, fetch=fetch, sleep=sleep,
        progress=progress, skip_spotify=skip_spotify, refresh=refresh,
    )
    return {
        "imported": imported,
        "skipped": skipped,
        "by_source": db.play_count_by_source(conn),
        "enriched": enriched,
        "buckets": db.bucket_distribution(conn),
        "canonical_plays": len(db.canonical_plays(conn)),
    }


def build_parser():
    import argparse

    parser = argparse.ArgumentParser(description="Import Last.fm history + enrich genres.")
    parser.add_argument(
        "--lastfm-only", action="store_true",
        help="resolve genres from Last.fm only (use when Spotify is blocked).",
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="re-enrich non-Spotify artists, upgrading them to Spotify genres.",
    )
    parser.add_argument(
        "--lastfm-refresh", action="store_true",
        help="re-do Last.fm genres for non-Spotify artists with the current "
             "tag rules (no Spotify calls); use after tuning the genre map.",
    )
    return parser


def resolve_modes(args) -> tuple[bool, bool]:
    """Map CLI args to (skip_spotify, refresh) for enrich_all."""
    if args.lastfm_refresh:
        return True, True  # re-process non-Spotify rows, Last.fm only
    return args.lastfm_only, args.refresh


def main() -> None:
    import time

    args = build_parser().parse_args()
    skip_spotify, refresh = resolve_modes(args)

    setup_logging("enrich")
    config.assert_credentials()
    xml_path = config.resolve_export_path()
    if not config.LASTFM_API_KEY:
        LOG.warning("LAST_FM_API_KEY not set — Last.fm genres unavailable.")

    def progress(done, total):
        LOG.info("  enriching artists: %d/%d", done, total)

    mode = ("Last.fm-refresh" if args.lastfm_refresh
            else "Last.fm-only" if args.lastfm_only
            else "refresh non-Spotify" if args.refresh else "Spotify-primary")
    LOG.info("Importing scrobbles + enriching artist genres (%s, "
             "resumable — safe to re-run if interrupted)...", mode)
    with db.connect() as conn:
        summary = run_ingest(
            conn, xml_path, get_client(), config.LASTFM_API_KEY,
            sleep=time.sleep, progress=progress,
            skip_spotify=skip_spotify, refresh=refresh,
        )

    LOG.info("Imported %d scrobbles (skipped %d).",
             summary["imported"], summary["skipped"])
    LOG.info("Plays by source: %s", summary["by_source"])
    enriched = summary["enriched"]
    LOG.info("Artists enriched: spotify=%d lastfm=%d none=%d skipped=%d deferred=%d",
             enriched["spotify"], enriched["lastfm"], enriched["none"],
             enriched["skipped"], enriched["deferred"])
    if enriched["stopped_early"]:
        LOG.warning("Stopped early — Spotify is rate-limiting. The import and "
                    "enriched artists are saved; re-run later to fill in the "
                    "deferred artists (it resumes automatically).")
    LOG.info("Canonical (deduped) plays: %d", summary["canonical_plays"])
    LOG.info("Bucket distribution:")
    for bucket, count in summary["buckets"].items():
        LOG.info("  %-12s %d", bucket, count)


if __name__ == "__main__":
    main()
