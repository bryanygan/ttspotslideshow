"""Export slideshow PNG slides to an MP4 video."""

import logging
from pathlib import Path

log = logging.getLogger(__name__)


def export_video(
    slide_paths: list[str | Path],
    output_path: str | Path,
    duration_per_slide: float = 3.0,
    crossfade_duration: float = 0.5,
) -> Path | None:
    """Combine rendered slide images into an MP4 video.

    Each slide is displayed for *duration_per_slide* seconds at 30 fps.
    If ``imageio[ffmpeg]`` is not installed, logs a warning and returns ``None``.

    Returns the output path on success, ``None`` on failure.
    """
    try:
        import imageio
    except ImportError:
        log.warning(
            "imageio[ffmpeg] is not installed -- skipping video export. "
            "Install it with: pip install 'imageio[ffmpeg]'"
        )
        return None

    slide_paths = [Path(p) for p in slide_paths]
    output_path = Path(output_path)

    if not slide_paths:
        log.warning("No slide images provided for video export.")
        return None

    fps = 30
    frames_per_slide = int(fps * duration_per_slide)

    try:
        writer = imageio.get_writer(str(output_path), fps=fps, codec="libx264")
        for slide_path in slide_paths:
            img = imageio.imread(str(slide_path))
            for _ in range(frames_per_slide):
                writer.append_data(img)
        writer.close()
        log.info("Video exported to %s (%d slides, %.1fs each)", output_path, len(slide_paths), duration_per_slide)
        return output_path
    except Exception as exc:
        log.warning("Video export failed: %s", exc)
        return None
