"""Learn a style profile from an account's existing TikTok captions.

Feed the output of ``ingest/tiktok_caption_extract.py`` into
``analyze_captions`` to build a profile, then pass it to
``slideshow.caption.generate_caption(..., style_profile=profile)`` so
auto-generated captions favor the same emoji and hashtags the account
already uses.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

_HASHTAG_RE = re.compile(r"#(\w+)")
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]"
)
_FIRST_WORD_RE = re.compile(r"[^\s#@]+")


def load_captions(path: str | Path) -> list[str]:
    """Load caption strings from a JSON export.

    Accepts a JSON list of plain strings, or a list of dicts each holding a
    "caption" or "description" key (the shape tiktok_caption_extract.py
    produces).
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    captions: list[str] = []
    for item in data:
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            text = item.get("caption") or item.get("description") or ""
        else:
            continue
        if text:
            captions.append(text)
    return captions


def analyze_captions(captions: list[str], top_n: int = 10) -> dict:
    """Compute a style profile (lengths, hashtags, emoji, openers) from raw captions."""
    if not captions:
        return {
            "sample_size": 0,
            "avg_length": 0,
            "avg_hashtag_count": 0,
            "top_hashtags": [],
            "top_emojis": [],
            "common_openers": [],
        }

    lengths = [len(c) for c in captions]
    hashtag_counts_per_caption = []
    hashtag_counter: Counter[str] = Counter()
    emoji_counter: Counter[str] = Counter()
    opener_counter: Counter[str] = Counter()

    for caption in captions:
        tags = _HASHTAG_RE.findall(caption)
        hashtag_counts_per_caption.append(len(tags))
        for tag in tags:
            hashtag_counter[f"#{tag.lower()}"] += 1

        for ch in _EMOJI_RE.findall(caption):
            emoji_counter[ch] += 1

        match = _FIRST_WORD_RE.search(caption)
        if match:
            opener_counter[match.group(0).lower()] += 1

    return {
        "sample_size": len(captions),
        "avg_length": round(sum(lengths) / len(lengths), 1),
        "avg_hashtag_count": round(
            sum(hashtag_counts_per_caption) / len(captions), 1
        ),
        "top_hashtags": [tag for tag, _ in hashtag_counter.most_common(top_n)],
        "top_emojis": [e for e, _ in emoji_counter.most_common(top_n)],
        "common_openers": [w for w, _ in opener_counter.most_common(top_n)],
    }


def save_style_profile(profile: dict, path: str | Path) -> None:
    Path(path).write_text(json.dumps(profile, indent=2), encoding="utf-8")


def load_style_profile(path: str | Path) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "captions_json", help="Path to a tiktok_caption_extract.py JSON export"
    )
    parser.add_argument(
        "--out", default="data/caption_style_profile.json", help="Output profile path"
    )
    args = parser.parse_args()

    captions = load_captions(args.captions_json)
    profile = analyze_captions(captions)
    save_style_profile(profile, args.out)
    print(f"Analyzed {profile['sample_size']} captions -> {args.out}")
    print(json.dumps(profile, indent=2))


if __name__ == "__main__":
    _main()
