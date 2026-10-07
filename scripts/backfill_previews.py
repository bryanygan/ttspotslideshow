"""Generate WebP previews/thumbnails for slides rendered before they existed.

Usage:  .venv\\Scripts\\python.exe scripts\\backfill_previews.py
Safe to re-run: slides whose previews are already up to date are skipped.
"""

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

from render.export import preview_paths, write_previews  # noqa: E402

SLIDES_ROOT = Path(__file__).resolve().parent.parent / "output" / "slides"


def _needs_previews(png: Path) -> bool:
    mtime = png.stat().st_mtime
    return any(not p.exists() or p.stat().st_mtime < mtime for p in preview_paths(png))


def _backfill(png: Path) -> str | None:
    try:
        with Image.open(png) as im:
            write_previews(im, png)
        return None
    except Exception as e:
        return f"{png}: {e}"


def main() -> None:
    pngs = [p for p in SLIDES_ROOT.glob("*/*.png") if _needs_previews(p)]
    print(f"{len(pngs)} slide(s) need previews")
    with ProcessPoolExecutor() as pool:
        errors = [e for e in pool.map(_backfill, pngs, chunksize=4) if e]
    for e in errors:
        print("FAILED", e)
    print(f"done: {len(pngs) - len(errors)} ok, {len(errors)} failed")


if __name__ == "__main__":
    main()
