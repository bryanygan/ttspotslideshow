"""OCR Entry point: read a queue/playlist screenshot using Windows OCR,

fuzzy-match tracks against iTunes, and generate slideshow slides.

Usage:
    python -m slideshow.ocr <path_to_screenshot> [--skip-render]
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

import db
from slideshow.builder import build_recap_slideshow
from text_norm import normalize
from webutil import itunes_search

# A track duration like "3:45" or "12:07" — used to skip timestamp lines without
# also dropping titles that merely contain a colon (e.g. "Re: Stacks").
_DURATION_RE = re.compile(r"^\d{1,2}:\d{2}$")


def _is_duration(line: str) -> bool:
    return bool(_DURATION_RE.match(line.strip()))


def run_windows_ocr(image_path: Path) -> list[str]:
    """Execute native Windows OCR via a PowerShell subprocess."""
    # Escape single quotes for PowerShell
    escaped_path = str(image_path.resolve()).replace("'", "''")
    script = f"""
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    [Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType=WindowsRuntime] | Out-Null
    [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime] | Out-Null
    [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime] | Out-Null
    [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage, ContentType=WindowsRuntime] | Out-Null
    [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime] | Out-Null

    $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {{ 
        $_.Name -eq 'AsTask' -and 
        $_.GetParameters().Count -eq 1 -and 
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' 
    }})[0]

    function Get-WinRTResult {{
        param($AsyncOp, $ResultType)
        $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
        $netTask = $asTask.Invoke($null, @($AsyncOp))
        $netTask.Wait(-1) | Out-Null
        return $netTask.Result
    }}

    $path = '{escaped_path}'
    if (-not (Test-Path $path)) {{
        Write-Error "File not found: $path"
        exit 1
    }}
    
    $file = Get-WinRTResult -AsyncOp ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) -ResultType ([Windows.Storage.StorageFile])
    $stream = Get-WinRTResult -AsyncOp ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) -ResultType ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Get-WinRTResult -AsyncOp ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) -ResultType ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Get-WinRTResult -AsyncOp ($decoder.GetSoftwareBitmapAsync()) -ResultType ([Windows.Graphics.Imaging.SoftwareBitmap])

    [Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime] | Out-Null

    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if ($null -eq $engine) {{
        $lang = [Windows.Globalization.Language]::new('en-US')
        $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
    }}
    if ($null -eq $engine) {{
        Write-Error "Failed to initialize OCR Engine."
        exit 1
    }}
    $result = Get-WinRTResult -AsyncOp ($engine.RecognizeAsync($bitmap)) -ResultType ([Windows.Media.Ocr.OcrResult])
    $result.Lines | ForEach-Object {{ $_.Text }}
    """

    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            check=True,
        )
        lines = [
            line.strip() for line in res.stdout.splitlines() if line.strip()
        ]
        return lines
    except Exception as e:
        print(f"Error running native Windows OCR: {e}", file=sys.stderr)
        return []


def search_itunes(query: str, fetch: Optional[Callable[[str], str]] = None) -> Optional[dict]:
    """Query the iTunes Search API for a song query. Returns the first result, or None."""
    results = itunes_search(query, fetch=fetch)
    return results[0] if results else None


def is_valid_match(line1: str, line2: str, result: dict) -> bool:
    """Verify that the iTunes result is a close match for the parsed lines."""
    res_title = normalize(result.get("trackName", ""))
    res_artist = normalize(result.get("artistName", ""))

    n_line1 = normalize(line1)
    n_line2 = normalize(line2)

    # Check direct pairing: L1 is title, L2 is artist
    if res_title in n_line1 and res_artist in n_line2:
        return True

    # Check reverse pairing: L1 is artist, L2 is title
    if res_artist in n_line1 and res_title in n_line2:
        return True

    # Allow combined overlap (e.g. OCR merged columns)
    combined = n_line1 + n_line2
    if res_title in combined and res_artist in combined:
        return True

    return False


def clean_ocr_line(line: str) -> str:
    """Clean common OCR noise, badges, and formatting artifacts from a line."""
    # 1. Remove leading explicit/playing badges: "a ", "_f ", ". ", "a  "
    line = re.sub(r"^(?:[a_.\-\d\s]|_f)\s+\b", "", line, flags=re.IGNORECASE)
    # 2. Remove standalone badges like "Video", "Lyrics", "Explicit", "Audio", "Official"
    line = re.sub(r"\b(Video|Lyrics|Audio|Explicit|Official)\b\s*", "", line, flags=re.IGNORECASE)
    # 3. Clean up leading/trailing punctuation and multiple spaces
    line = re.sub(r"^[^a-zA-Z0-9\"'\(]+|[^a-zA-Z0-9\"'\)]+$", "", line)
    return line.strip()


def search_spotify(query: str) -> Optional[dict]:
    """Query Spotify Web API for a track query. Returns track dict in similar shape to iTunes."""
    try:
        from spotify_client import get_client
        sp = get_client()
        results = sp.search(q=query, type="track", limit=1)
        items = results.get("tracks", {}).get("items", [])
        if items:
            track = items[0]
            album = track.get("album", {})
            images = album.get("images", [])
            art_url = images[0].get("url") if images else ""
            return {
                "trackName": track.get("name", ""),
                "artistName": ", ".join(a.get("name", "") for a in track.get("artists", [])),
                "artworkUrl100": art_url,
                "trackId": track.get("id", ""),
            }
    except Exception:
        pass
    return None


def parse_tracks_from_lines(
    lines: list[str],
    conn=None,
    fetch: Optional[Callable[[str], str]] = None,
) -> list[dict]:
    """Pair consecutive lines and resolve them into track metadata via iTunes/Spotify search."""
    tracks = []
    seen_keys = set()

    i = 0
    while i < len(lines) - 1:
        line1 = lines[i]
        line2 = lines[i + 1]

        # Ignore duration lines (e.g., "3:45"), consecutive numbers, and stubs.
        if (
            _is_duration(line1)
            or _is_duration(line2)
            or (line1.isdigit() and line2.isdigit())
            or len(line1) < 2
            or len(line2) < 2
        ):
            i += 1
            continue

        c_line1 = clean_ocr_line(line1)
        c_line2 = clean_ocr_line(line2)

        if len(c_line1) < 2 or len(c_line2) < 2:
            i += 1
            continue

        query = f"{c_line1} {c_line2}"
        # 1. Search iTunes
        result = search_itunes(query, fetch=fetch)
        # 2. Fallback to Spotify Search if iTunes failed or returned mismatch
        if not result or not is_valid_match(c_line1, c_line2, result):
            result = search_spotify(query)

        if result and is_valid_match(c_line1, c_line2, result):
            title = result.get("trackName", "")
            artist = result.get("artistName", "")
            art_url = result.get("artworkUrl100", "").replace(
                "100x100", "600x600"
            )

            artist_key = normalize(artist)
            track_key = artist_key + "\t" + normalize(title)

            if track_key not in seen_keys:
                seen_keys.add(track_key)

                # Fetch genre bucket from local DB if available
                bucket = "unknown"
                if conn:
                    try:
                        row = db.get_artist_genre(conn, artist_key)
                        if row:
                            bucket = row["primary_bucket"]
                    except Exception:
                        pass

                tracks.append(
                    {
                        "track_key": track_key,
                        "track_id": str(result.get("trackId", "")),
                        "title": title,
                        "artist": artist,
                        "album_art_url": art_url,
                        "primary_bucket": bucket,
                    }
                )
                print(
                    f"  [OK] Identified: \"{title}\" by {artist} (Bucket: {bucket})"
                )

            # Successfully paired L1 and L2, skip next index
            i += 2
        else:
            i += 1

    return tracks


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract songs from screenshot and generate slideshow."
    )
    parser.add_argument(
        "image_path", help="Path to the screenshot image file."
    )
    parser.add_argument(
        "--skip-render",
        "-s",
        action="store_true",
        help="print identified tracks without building slideshow.",
    )
    parser.add_argument(
        "--out-dir",
        default="output/slides",
        help="slides output root folder (default: output/slides).",
    )
    args = parser.parse_args()

    img_path = Path(args.image_path)
    if not img_path.exists():
        print(f"Error: Screenshot file does not exist: {img_path}")
        sys.exit(1)

    print(f"Running native Windows OCR on: {img_path}...")
    lines = run_windows_ocr(img_path)
    print(f"Extracted {len(lines)} raw text lines.")

    if not lines:
        print("No text detected. Exiting.")
        sys.exit(0)

    print("Resolving tracks via iTunes Search API...")
    # Initialize connection to query local genre cache
    try:
        db.init_db()
        conn = sqlite3_connect_helper()
    except Exception:
        conn = None

    try:
        tracks = parse_tracks_from_lines(lines, conn=conn)
    finally:
        if conn:
            conn.close()

    print(f"\nSuccessfully identified {len(tracks)} unique track(s).")

    if not tracks:
        print("No matches confirmed. Exiting.")
        sys.exit(0)

    if args.skip_render:
        print("\nIdentified Tracks:")
        for idx, t in enumerate(tracks, 1):
            print(f"  {idx}. {t['title']} - {t['artist']}")
        return

    # Check if we have at least 4 tracks to make a slide
    if len(tracks) < 4:
        print(
            f"Warning: Need at least 4 tracks to render a slide. Only have {len(tracks)}."
        )
        sys.exit(0)

    print(f"\nGenerating slideshow ({len(tracks) // 4} slide(s))...")
    with db.connect() as conn:
        summary = build_recap_slideshow(conn, Path(args.out_dir), tracks)

    print(f"Wrote {summary['slide_count']} slide(s) to: {summary['out_dir']}")


def sqlite3_connect_helper():
    import sqlite3

    c = sqlite3.connect(db.DB_PATH)
    c.row_factory = sqlite3.Row
    return c


if __name__ == "__main__":
    main()
