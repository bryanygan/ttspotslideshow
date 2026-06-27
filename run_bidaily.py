"""Automate the bi-daily pipeline.

Runs:
1. db.init_db() to ensure the schema is up to date.
2. (Optional) Spotify Recently Played logging.
3. (Optional) Last.fm API recent scrobble ingest.
4. slideshow selection + rendering to output/slides/<date>/.

This is intended to run as a scheduled task (e.g. via Windows Task Scheduler).
"""

import argparse
import logging
from pathlib import Path

import config
import db
from logger import log_recent_plays
from ingest.lastfm_import import import_recent_from_api
from ingest.enrich_popularity import enrich_all_popularity
from slideshow.builder import build_slideshow
from slideshow.cli import format_summary
from logsetup import setup_logging

LOG = logging.getLogger("run_bidaily")


def run_pipeline(
    skip_spotify: bool = False,
    skip_lastfm: bool = False,
    skip_popularity: bool = False,
    out_root: str = "output/slides",
) -> None:
    # 1. Ensure DB is migrated
    db.init_db()

    # 2. Ingest Spotify plays
    if not skip_spotify:
        try:
            config.assert_credentials()
            LOG.info("Fetching recently played tracks from Spotify...")
            spotify_added = log_recent_plays()
            LOG.info("Added %d new play(s) from Spotify.", spotify_added)
        except Exception as e:
            LOG.warning("Spotify ingest failed: %s", e)

    # 3. Ingest Last.fm plays
    if not skip_lastfm:
        if not config.LASTFM_API_KEY:
            LOG.warning("LAST_FM_API_KEY not set — skipping Last.fm API ingest.")
        else:
            username = config.get_lastfm_user()
            if not username:
                LOG.warning(
                    "Last.fm username not configured/detected — skipping Last.fm API ingest."
                )
            else:
                LOG.info("Fetching recent tracks for user '%s' from Last.fm API...", username)
                try:
                    with db.connect() as conn:
                        since_unix = db.latest_lastfm_played_at_unix(conn)
                        lastfm_added = import_recent_from_api(
                            conn,
                            api_key=config.LASTFM_API_KEY,
                            username=username,
                            since_unix=since_unix,
                        )
                        LOG.info("Added %d new play(s) from Last.fm API.", lastfm_added)
                except Exception as e:
                    LOG.warning("Last.fm ingest failed: %s", e)

    # 3.5 Enrich global popularity (Last.fm primary, ListenBrainz fallback).
    if not skip_popularity:
        try:
            LOG.info("Enriching track popularity...")
            with db.connect() as conn:
                pop_summary = enrich_all_popularity(
                    conn,
                    lastfm_api_key=config.LASTFM_API_KEY,
                    listenbrainz_token=config.LISTENBRAINZ_TOKEN,
                )
            LOG.info(
                "Popularity: processed=%d lastfm=%d listenbrainz=%d none=%d",
                pop_summary["processed"], pop_summary["lastfm"],
                pop_summary["listenbrainz"], pop_summary["none"],
            )
        except Exception as e:
            LOG.warning("Popularity enrichment failed: %s", e)

    # 4. Build slideshow
    LOG.info("Building slideshow...")
    out_path = Path(out_root)
    with db.connect() as conn:
        slide_summary = build_slideshow(conn, out_path)
    LOG.info(format_summary(slide_summary))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the bi-daily slideshow generation pipeline."
    )
    parser.add_argument(
        "--skip-spotify",
        action="store_true",
        help="skip pulling recently-played tracks from Spotify.",
    )
    parser.add_argument(
        "--skip-lastfm",
        action="store_true",
        help="skip pulling recent scrobbles from the Last.fm API.",
    )
    parser.add_argument(
        "--skip-popularity",
        action="store_true",
        help="skip global-popularity enrichment (Last.fm + ListenBrainz).",
    )
    parser.add_argument(
        "--out-dir",
        default="output/slides",
        help="root folder for dated slideshow outputs (default: output/slides).",
    )
    args = parser.parse_args()

    setup_logging("run_bidaily")
    run_pipeline(
        skip_spotify=args.skip_spotify,
        skip_lastfm=args.skip_lastfm,
        skip_popularity=args.skip_popularity,
        out_root=args.out_dir,
    )


if __name__ == "__main__":
    main()
