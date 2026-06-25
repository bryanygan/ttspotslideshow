"""CLI: migrate + import Last.fm history + enrich genres, then print a summary.

Run: python -m ingest.enrich_cli
"""

import config
import db
from ingest.lastfm_import import import_scrobbles
from ingest.genres import enrich_all
from spotify_client import get_client


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


def main() -> None:
    import argparse
    import time

    parser = argparse.ArgumentParser(description="Import Last.fm history + enrich genres.")
    parser.add_argument(
        "--lastfm-only", action="store_true",
        help="resolve genres from Last.fm only (use when Spotify is blocked).",
    )
    parser.add_argument(
        "--refresh", action="store_true",
        help="re-enrich non-Spotify artists, upgrading them to Spotify genres.",
    )
    args = parser.parse_args()

    config.assert_credentials()
    xml_path = config.resolve_export_path()
    if not config.LASTFM_API_KEY:
        print("Warning: LAST_FM_API_KEY not set — Last.fm genres unavailable.")

    def progress(done, total):
        print(f"  enriching artists: {done}/{total}", flush=True)

    mode = ("Last.fm-only" if args.lastfm_only
            else "refresh non-Spotify" if args.refresh else "Spotify-primary")
    print(f"Importing scrobbles + enriching artist genres ({mode}, "
          "resumable — safe to re-run if interrupted)...", flush=True)
    with db.connect() as conn:
        summary = run_ingest(
            conn, xml_path, get_client(), config.LASTFM_API_KEY,
            sleep=time.sleep, progress=progress,
            skip_spotify=args.lastfm_only, refresh=args.refresh,
        )

    print(f"Imported {summary['imported']} scrobbles "
          f"(skipped {summary['skipped']}).")
    print(f"Plays by source: {summary['by_source']}")
    enriched = summary["enriched"]
    print(f"Artists enriched: spotify={enriched['spotify']} "
          f"lastfm={enriched['lastfm']} none={enriched['none']} "
          f"skipped={enriched['skipped']} deferred={enriched['deferred']}")
    if enriched["stopped_early"]:
        print("  NOTE: stopped early — Spotify is rate-limiting. The import and "
              "enriched artists are saved; re-run later to fill in the deferred "
              "artists (it resumes automatically).")
    print(f"Canonical (deduped) plays: {summary['canonical_plays']}")
    print("Bucket distribution:")
    for bucket, count in summary["buckets"].items():
        print(f"  {bucket:<12} {count}")


if __name__ == "__main__":
    main()
