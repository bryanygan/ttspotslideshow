"""Import Spotify Extended Streaming History JSON files from a zip archive."""

import argparse
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
import zipfile

import db
import config
from text_norm import normalize

def import_spotify_extended_history(conn: sqlite3.Connection, zip_path: Path, min_ms: int = 30000, dry_run: bool = False):
    print(f"Opening zip archive: {zip_path}")
    if not zip_path.exists():
        print(f"Error: Zip file {zip_path} does not exist.")
        return

    # 1. Warm up local caches from DB
    print("Warming up cache from database...")
    track_cache = {}  # track_id -> (artist_id, album_art_url, artist_genre)
    track_name_cache = {}  # (artist_norm, name_norm) -> (track_id, artist_id, album_art_url, artist_genre)
    artist_cache = {}  # artist_norm -> (artist_id, artist_genre)
    existing_spotify_plays = {}  # (artist_norm, name_norm) -> list of unix timestamps

    cursor = conn.cursor()
    
    # Cache existing Spotify play timestamps for deduplication
    print("Loading existing Spotify plays for deduplication...")
    rows = cursor.execute(
        "SELECT name, artist, played_at_unix FROM plays WHERE source = 'spotify'"
    ).fetchall()
    for r in rows:
        name_norm = normalize(r["name"])
        art_norm = normalize(r["artist"])
        unix = r["played_at_unix"]
        key = (art_norm, name_norm)
        if key not in existing_spotify_plays:
            existing_spotify_plays[key] = []
        existing_spotify_plays[key].append(unix)

    # Load track info from plays table to backfill metadata
    print("Loading existing track metadata...")
    rows = cursor.execute(
        "SELECT track_id, name, artist, artist_id, artist_genre, album_art_url FROM plays "
        "WHERE (track_id != '' OR album_art_url IS NOT NULL)"
    ).fetchall()
    
    for r in rows:
        t_id, name, artist, a_id, genre, art = r["track_id"], r["name"], r["artist"], r["artist_id"], r["artist_genre"], r["album_art_url"]
        art_norm = normalize(artist)
        name_norm = normalize(name)
        
        if t_id:
            if t_id not in track_cache or (not track_cache[t_id][1] and art):
                track_cache[t_id] = (a_id, art, genre)
        if art_norm and name_norm:
            key = (art_norm, name_norm)
            if key not in track_name_cache or (not track_name_cache[key][2] and art):
                track_name_cache[key] = (t_id, a_id, art, genre)
        if art_norm:
            if art_norm not in artist_cache or (not artist_cache[art_norm][0] and a_id):
                artist_cache[art_norm] = (a_id, genre)

    # Load from artist_genres
    genre_rows = cursor.execute(
        "SELECT artist_key, display_name, spotify_artist_id, primary_bucket FROM artist_genres"
    ).fetchall()
    for r in genre_rows:
        key, name, a_id, bucket = r["artist_key"], r["display_name"], r["spotify_artist_id"], r["primary_bucket"]
        if key not in artist_cache or (not artist_cache[key][0] and a_id):
            artist_cache[key] = (a_id, bucket)

    print(f"Cache warmed: {len(existing_spotify_plays)} tracks with existing Spotify plays, "
          f"{len(track_cache)} track IDs, {len(track_name_cache)} track name pairs, {len(artist_cache)} artists.")

    # 2. Iterate through zip and parse JSONs
    total_processed = 0
    total_inserted = 0
    total_skipped_short = 0
    total_skipped_no_meta = 0
    total_skipped_duplicate = 0

    with zipfile.ZipFile(zip_path) as z:
        filenames = sorted(
            [n for n in z.namelist() if "Streaming_History_Audio_" in n and n.endswith(".json")]
        )
        print(f"Found {len(filenames)} JSON files to process.")

        # Batch insert for speed
        insert_data = []

        for filename in filenames:
            print(f"Processing {filename}...")
            with z.open(filename) as f:
                try:
                    data = json.loads(f.read().decode("utf-8"))
                except Exception as e:
                    print(f"Error parsing JSON in {filename}: {e}")
                    continue

                for entry in data:
                    total_processed += 1
                    ts = entry.get("ts")
                    ms_played = entry.get("ms_played", 0)
                    track_name = entry.get("master_metadata_track_name")
                    artist_name = entry.get("master_metadata_album_artist_name")
                    spotify_uri = entry.get("spotify_track_uri")

                    if not track_name or not artist_name:
                        total_skipped_no_meta += 1
                        continue

                    # Filter short plays (< min_ms)
                    if ms_played < min_ms:
                        total_skipped_short += 1
                        continue

                    # Parse timestamp to unix
                    try:
                        played_at_unix = int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())
                    except Exception:
                        played_at_unix = int(datetime.now(timezone.utc).timestamp())

                    # Deduplicate in-memory against existing Spotify plays
                    art_norm = normalize(artist_name)
                    name_norm = normalize(track_name)
                    key = (art_norm, name_norm)

                    is_dup = False
                    if key in existing_spotify_plays:
                        for existing_unix in existing_spotify_plays[key]:
                            if abs(existing_unix - played_at_unix) <= 30:
                                is_dup = True
                                break
                    if is_dup:
                        total_skipped_duplicate += 1
                        continue

                    # Extract track ID
                    track_id = ""
                    if spotify_uri and spotify_uri.startswith("spotify:track:"):
                        track_id = spotify_uri.split(":")[-1]

                    # Lookup metadata from caches
                    artist_id = None
                    artist_genre = None
                    album_art_url = None

                    if track_id and track_id in track_cache:
                        artist_id, album_art_url, artist_genre = track_cache[track_id]
                    
                    if not album_art_url and key in track_name_cache:
                        fallback_tid, fallback_aid, fallback_art, fallback_genre = track_name_cache[key]
                        if not track_id:
                            track_id = fallback_tid
                        artist_id = fallback_aid
                        album_art_url = fallback_art
                        artist_genre = fallback_genre

                    if not artist_id and art_norm in artist_cache:
                        artist_id, artist_genre = artist_cache[art_norm]

                    insert_data.append((
                        track_id or "",
                        track_name,
                        artist_name,
                        artist_id,
                        artist_genre,
                        album_art_url,
                        ts,
                        played_at_unix
                    ))

                    # Track new inserts in memory so we don't insert duplicate plays from the file itself
                    if key not in existing_spotify_plays:
                        existing_spotify_plays[key] = []
                    existing_spotify_plays[key].append(played_at_unix)

        # 3. Perform database inserts in one transaction
        if insert_data:
            if dry_run:
                print(f"[DRY RUN] Would insert {len(insert_data)} plays.")
                total_inserted = len(insert_data)
            else:
                print(f"Inserting {len(insert_data)} plays into the database...")
                cursor.executemany(
                    """
                    INSERT OR IGNORE INTO plays
                        (track_id, name, artist, artist_id, artist_genre,
                         album_art_url, popularity, played_at, source, played_at_unix)
                    VALUES (?, ?, ?, ?, ?, ?, NULL, ?, 'spotify', ?)
                    """,
                    insert_data
                )
                conn.commit()
                # Find how many rows were actually written
                total_inserted = conn.total_changes
                print(f"Done. Successfully inserted {total_inserted} plays.")
        else:
            print("No new plays found to insert.")

    print("\nImport Summary:")
    print(f"Total entries processed: {total_processed}")
    print(f"Total inserted: {total_inserted}")
    print(f"Skipped (short plays < {min_ms/1000:.1f}s): {total_skipped_short}")
    print(f"Skipped (duplicate Spotify plays): {total_skipped_duplicate}")
    print(f"Skipped (missing metadata): {total_skipped_no_meta}")

def main():
    parser = argparse.ArgumentParser(description="Import Spotify Extended Streaming History zip file.")
    parser.add_argument("--zip", type=str, default="data/my_spotify_data.zip", help="Path to my_spotify_data.zip")
    parser.add_argument("--min-sec", type=int, default=30, help="Minimum listen duration in seconds to count as a play")
    parser.add_argument("--dry-run", action="store_true", help="Perform a dry run without committing database changes")
    args = parser.parse_args()

    zip_path = Path(args.zip)
    min_ms = args.min_sec * 1000

    # Ensure DB is migrated and ready
    db.init_db()

    with db.connect() as conn:
        import_spotify_extended_history(conn, zip_path, min_ms=min_ms, dry_run=args.dry_run)

if __name__ == "__main__":
    main()
