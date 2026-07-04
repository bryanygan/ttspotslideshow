"""One-off CLI to pull every caption off a public TikTok profile.

This must be run somewhere with real network access to tiktok.com. It will
NOT work inside a sandboxed/cloud dev environment that blocks that domain —
run it on your own machine instead:

    pip install yt-dlp
    python -m ingest.tiktok_caption_extract bghyped

Writes data/tiktok_captions.json (gitignored — it's your personal export)
with one entry per video: id, url, caption, hashtags, upload_date.

Feed that file into ingest/caption_style.py to build a style profile that
slideshow/caption.py can use when generating new captions.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_OUT = Path("data/tiktok_captions.json")
_HASHTAG_RE = re.compile(r"#(\w+)")


def extract_captions(handle: str) -> list[dict]:
    """Fetch every public video's caption for a TikTok handle via yt-dlp."""
    try:
        import yt_dlp
    except ImportError:
        print("yt-dlp is required: pip install yt-dlp", file=sys.stderr)
        raise

    handle = handle.lstrip("@")
    url = f"https://www.tiktok.com/@{handle}"

    ydl_opts = {
        "quiet": True,
        "extract_flat": False,
        "skip_download": True,
    }

    results: list[dict] = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        entries = (info or {}).get("entries", [])
        for entry in entries:
            if not entry:
                continue
            caption = entry.get("description") or entry.get("title") or ""
            results.append(
                {
                    "id": entry.get("id"),
                    "url": entry.get("webpage_url"),
                    "caption": caption,
                    "hashtags": _HASHTAG_RE.findall(caption),
                    "upload_date": entry.get("upload_date"),
                }
            )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("handle", help="TikTok handle, with or without @ (e.g. bghyped)")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output JSON path")
    args = parser.parse_args()

    captions = extract_captions(args.handle)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(captions, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(captions)} captions to {out_path}")


if __name__ == "__main__":
    main()
