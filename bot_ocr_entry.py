"""Headless OCR -> slideshow entry point for remote callers (e.g. a Discord bot).

Takes a screenshot path, runs the OCR pipeline, builds a recap slideshow, and
prints a single JSON object to stdout describing the result. Designed to be
invoked as a subprocess from another project (the zreatsbot Discord bot) so the
two codebases stay decoupled and don't fight over the shared ``db`` module name.

Usage:
    python bot_ocr_entry.py <path_to_screenshot> [--min-tracks N]

Output (stdout, single line of JSON):
    {"ok": true, "out_dir": "...", "slides": ["abs/path/slide_1.png", ...],
     "track_count": 8, "caption": "..."}
  or
    {"ok": false, "error": "human-readable message", "code": "..."}
"""

import argparse
import json
import sys
from pathlib import Path


def _fail(message: str, code: str = "error", **extra) -> None:
    print(json.dumps({"ok": False, "error": message, "code": code, **extra}))
    sys.exit(0)  # exit 0: the JSON carries success/failure, not the exit code


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR a screenshot and build slides.")
    parser.add_argument("image_path", help="Path to the screenshot image.")
    parser.add_argument("--min-tracks", type=int, default=4,
                        help="Minimum identified tracks required (default 4).")
    parser.add_argument("--out-dir", default="output/slides",
                        help="Slides output root (default output/slides).")
    args = parser.parse_args()

    img_path = Path(args.image_path)
    if not img_path.exists():
        _fail(f"Screenshot file not found: {img_path}", code="no_file")

    import db
    from slideshow.ocr import run_ocr, parse_tracks_from_lines
    from slideshow.builder import (
        build_recap_slideshow, MissingCoverError, UnconfirmedCoverError,
    )

    lines = run_ocr(img_path)
    if not lines:
        _fail("No text detected in the screenshot.", code="no_text")

    db.init_db()
    with db.connect() as conn:
        tracks = parse_tracks_from_lines(lines, conn=conn)

    if len(tracks) < args.min_tracks:
        _fail(
            f"Only identified {len(tracks)} track(s); need at least {args.min_tracks}.",
            code="too_few", track_count=len(tracks),
        )

    try:
        with db.connect() as conn:
            # Headless flow: accept iTunes fallback covers (no UI to confirm them).
            summary = build_recap_slideshow(
                conn, Path(args.out_dir), tracks, allow_itunes_covers=True
            )
    except UnconfirmedCoverError as e:
        names = ", ".join(f"{t['title']} – {t['artist']}" for t in e.unconfirmed_tracks)
        _fail(f"Some covers need manual confirmation: {names}", code="unconfirmed_covers")
    except MissingCoverError as e:
        names = ", ".join(f"{t['title']} – {t['artist']}" for t in e.missing_tracks)
        _fail(f"Missing album cover art for: {names}", code="missing_covers")
    except Exception as e:  # pragma: no cover - defensive
        _fail(f"Slideshow generation failed: {e}", code="build_failed")

    out_dir = Path(summary["out_dir"])
    slides = [str((out_dir / f"slide_{i}.png").resolve())
              for i in range(1, summary["slide_count"] + 1)]

    print(json.dumps({
        "ok": True,
        "out_dir": str(out_dir.resolve()),
        "slides": slides,
        "track_count": summary.get("track_count", len(tracks)),
        "slide_count": summary.get("slide_count", 0),
        "caption": summary.get("caption", ""),
    }))


if __name__ == "__main__":
    main()
