"""CLI: migrate + import Last.fm history + enrich genres, then print a summary.

Run: python -m ingest.enrich_cli
"""

import config
import db
from ingest.lastfm_import import import_scrobbles
from ingest.genres import enrich_all
from spotify_client import get_client


def run_ingest(conn, xml_path, spotify_client, lastfm_api_key, fetch=None,
               sleep=None, progress=None) -> dict:
    """Migrate, import, and enrich against an open connection. Returns a summary."""
    db.migrate(conn)
    imported, skipped = import_scrobbles(conn, xml_path)
    conn.commit()  # persist the import before the long (resumable) enrichment
    enriched = enrich_all(
        conn, spotify_client, lastfm_api_key, fetch=fetch, sleep=sleep,
        progress=progress,
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
    config.assert_credentials()
    xml_path = config.resolve_export_path()
    if not config.LASTFM_API_KEY:
        print("Warning: LAST_FM_API_KEY not set — genre fallback disabled.")

    import time

    def progress(done, total):
        print(f"  enriching artists: {done}/{total}", flush=True)

    print("Importing scrobbles + enriching artist genres "
          "(resumable — safe to re-run if interrupted)...", flush=True)
    with db.connect() as conn:
        summary = run_ingest(
            conn, xml_path, get_client(), config.LASTFM_API_KEY,
            sleep=time.sleep, progress=progress,
        )

    print(f"Imported {summary['imported']} scrobbles "
          f"(skipped {summary['skipped']}).")
    print(f"Plays by source: {summary['by_source']}")
    print(f"Artists enriched: {summary['enriched']}")
    print(f"Canonical (deduped) plays: {summary['canonical_plays']}")
    print("Bucket distribution:")
    for bucket, count in summary["buckets"].items():
        print(f"  {bucket:<12} {count}")


if __name__ == "__main__":
    main()
