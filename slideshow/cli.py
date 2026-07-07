"""CLI: build the bi-daily slideshow into output/slides/<date>/.

Run: python -m slideshow.cli
"""

import sys
from pathlib import Path

import db
from slideshow.builder import build_slideshow


def format_summary(summary: dict) -> str:
    """Render a run summary as human-readable text."""
    if summary["track_count"] == 0:
        return (f"No tracks available to render (empty window or DB) — "
                f"nothing written. (widened to {summary['days_used']} days)")
    lines = [
        f"Wrote {summary['slide_count']} slide(s) -> {summary['out_dir']}",
        f"Window: last {summary['days_used']} days; "
        f"{summary['track_count']} tracks",
        "Genre spread: " + ", ".join(
            f"{b}={n}" for b, n in summary["genre_spread"].items()
        ),
    ]
    if summary.get("caption"):
        lines.append("\nCaption:\n" + summary["caption"])
    return "\n".join(lines)


def main() -> None:
    # Captions can contain emoji; keep printing safe on a cp1252 Windows console.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    out_root = Path("output") / "slides"
    with db.connect() as conn:
        summary = build_slideshow(conn, out_root)
    print(format_summary(summary))


if __name__ == "__main__":
    main()
