"""Slide output: full-quality PNG master plus lightweight WebP copies for the web."""

import os
import uuid
from pathlib import Path

from PIL import Image

PREVIEW_QUALITY = 95
THUMB_WIDTH = 540
THUMB_QUALITY = 85


def preview_paths(png_path: Path) -> tuple[Path, Path]:
    png_path = Path(png_path)
    return png_path.with_suffix(".webp"), png_path.with_name(png_path.stem + ".thumb.webp")


def _atomic_save(img: Image.Image, dest: Path, **kw) -> None:
    # Temp + replace so a concurrent reader never sees a half-written file.
    tmp = dest.with_name(f"{dest.name}.{uuid.uuid4().hex}.tmp")
    try:
        img.save(tmp, "WEBP", **kw)
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)


def write_previews(img: Image.Image, png_path: Path) -> None:
    preview, thumb = preview_paths(png_path)
    rgb = img.convert("RGB")
    _atomic_save(rgb, preview, quality=PREVIEW_QUALITY, method=4)
    small = rgb.copy()
    small.thumbnail((THUMB_WIDTH, small.height), Image.LANCZOS)
    _atomic_save(small, thumb, quality=THUMB_QUALITY, method=4)


def save_slide(img: Image.Image, png_path: Path) -> None:
    img.save(png_path)
    write_previews(img, png_path)
