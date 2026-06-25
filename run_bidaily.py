"""Automate the bi-daily pipeline.

Runs:
1. db.init_db() to ensure the schema is up to date.
2. (Optional) Spotify Recently Played logging.
3. (Optional) Last.fm API recent scrobble ingest.
4. slideshow selection + rendering to output/slides/<date>/.

This is intended to run as a scheduled task (e.g. via Windows Task Scheduler).
"""

import argparse
import sys
from pathlib import Path

import config
import db
from logger import log_recent_plays
from ingest.lastfm_import import import_recent_from_api
from slideshow.builder import build_slideshow
from slideshow.cli import format_summary


def run_pipeline(
    skip_spotify: bool = False,
    skip_lastfm: bool = False,
    out_root: str = "output/slides",
) -> None:
    # 1. Ensure DB is migrated
    db.init_db()

    # 2. Ingest Spotify plays
    if not skip_spotify:
        try:
            config.assert_credentials()
            print("Fetching recently played tracks from Spotify...")
            spotify_added = log_recent_plays()
            print(f"Added {spotify_added} new play(s) from Spotify.")
        except Exception as e:
            print(f"Warning: Spotify ingest failed: {e}", file=sys.stderr)

    # 3. Ingest Last.fm plays
    if not skip_lastfm:
        if not config.LASTFM_API_KEY:
            print(
                "Warning: LAST_FM_API_KEY not set — skipping Last.fm API ingest.",
                file=sys.stderr,
            )
        else:
            username = config.get_lastfm_user()
            if not username:
                print(
                    "Warning: Last.fm username not configured/detected — skipping Last.fm API ingest.",
                    file=sys.stderr,
                )
            else:
                print(
                    f"Fetching recent tracks for user '{username}' from Last.fm API..."
                )
                try:
                    with db.connect() as conn:
                        since_unix = db.latest_lastfm_played_at_unix(conn)
                        lastfm_added = import_recent_from_api(
                            conn,
                            api_key=config.LASTFM_API_KEY,
                            username=username,
                            since_unix=since_unix,
                        )
                        print(f"Added {lastfm_added} new play(s) from Last.fm API.")
                except Exception as e:
                    print(f"Warning: Last.fm ingest failed: {e}", file=sys.stderr)

    # 4. Build slideshow
    print("Building slideshow...")
    out_path = Path(out_root)
    with db.connect() as conn:
        slide_summary = build_slideshow(conn, out_path)
    print(format_summary(slide_summary))


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
        "--out-dir",
        default="output/slides",
        help="root folder for dated slideshow outputs (default: output/slides).",
    )
    args = parser.parse_args()

    run_pipeline(
        skip_spotify=args.skip_spotify,
        skip_lastfm=args.skip_lastfm,
        out_root=args.out_dir,
    )


if __name__ == "__main__":
    main()
