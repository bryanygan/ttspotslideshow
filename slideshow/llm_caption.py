"""Local LLM caption generation via Ollama (llama3.2:1b).

This module generates only the *voice* of a caption — the short, personal
one-liner in Bryan's style — using a small local model with his past captions
(`data/captions.txt`) as few-shot examples. Hashtags are NOT produced here; the
caller (`slideshow.caption`) appends them deterministically so the "max 5
hashtags" rule can never be broken by the model.

Everything here is best-effort. Any failure (Ollama not running, timeout, junk
output) returns ``None`` so the caller falls back to the deterministic template
caption and a scheduled run never breaks.

No third-party dependencies: the Ollama HTTP API is called via stdlib urllib.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

# --- Configuration (all overridable via environment) -----------------------
# Host that runs Ollama. Default is the local daemon.
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
# Small, fast model chosen for a low-RAM mini PC that also runs Homebridge.
CAPTION_MODEL = os.environ.get("CAPTION_MODEL", "llama3.2:1b")
# keep_alive "0" => unload the model from RAM immediately after the call. This
# is deliberate: the host has little spare RAM and also runs Homebridge, so we
# never leave the model resident. Cold-start is ~7s on an Intel N95, which is
# fine for a bi-daily job. Set CAPTION_KEEP_ALIVE=5m on a roomier host to keep
# it warm for snappier interactive (dashboard) use.
KEEP_ALIVE = os.environ.get("CAPTION_KEEP_ALIVE", "0")
REQUEST_TIMEOUT = float(os.environ.get("CAPTION_TIMEOUT", "60"))

_CAPTIONS_FILE = Path(__file__).resolve().parent.parent / "data" / "captions.txt"

# Rotation-style captions are prioritized as few-shot examples because the
# slideshow is a "daily rotation" post. These substrings pick them out.
_ROTATION_HINTS = ("rotation", "listening", "nowadays", "genre", "leaning", "spin")

# Rotation-specific seed examples in Bryan's voice. His real archive
# (data/captions.txt) is mostly concert posts, so these guarantee the model
# always sees enough "daily rotation" examples to anchor the voice. Kept in code
# (not in captions.txt) so his archive stays a pure record of his actual posts.
# Deliberately genre-neutral so they don't bias the model toward any one genre.
_SEED_ROTATION_EXAMPLES = [
    "daily rotation, been leaning heavy into one sound this whole cycle lowk 🥹",
    "yet another rotation post, this batch has been carrying my commutes and gym sessions fr",
    "lowk switched up my whole palette lately, been digging some underrated stuff tbh",
    "current rotation running my entire week rn, so many bangers ngl",
]

# Lines the model sometimes emits that are commentary, not caption text.
_META_PREFIXES = (
    "this caption", "i hope", "let me know", "feel free", "here", "note:",
    "sure", "of course", "caption:", "hope this", "would you", "the caption",
)


def _strip_tags(text: str) -> str:
    """Remove hashtags and @mentions, leaving just the human text."""
    text = re.sub(r"[#@]\S+", "", text)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()


def _load_examples(max_examples: int = 7) -> list[str]:
    """Load past captions as text-only few-shot examples, rotation posts first."""
    try:
        raw = _CAPTIONS_FILE.read_text(encoding="utf-8")
    except OSError:
        return []

    blocks = [b.strip() for b in re.split(r"\n\s*\n", raw) if b.strip()]
    examples: list[str] = []
    for block in blocks:
        text = _strip_tags(block)
        if len(text) >= 15:  # skip tiny fragments left after stripping tags
            examples.append(text)

    # Rotation-flavored examples match the output use-case best; show them first,
    # then the seed rotation examples, then other captions for voice variety.
    rotation = [e for e in examples if any(h in e.lower() for h in _ROTATION_HINTS)]
    others = [e for e in examples if e not in rotation]

    ordered = rotation + _SEED_ROTATION_EXAMPLES + others
    seen: set[str] = set()
    deduped: list[str] = []
    for e in ordered:
        if e not in seen:
            seen.add(e)
            deduped.append(e)
    return deduped[:max_examples]


def _build_prompt(tracks: list[dict], examples: list[str], cover_title: str | None) -> str:
    genres: list[str] = []
    artists: list[str] = []
    for t in tracks:
        g = t.get("primary_bucket")
        if g and g.lower() not in ("unknown", "other") and g not in genres:
            genres.append(g)
        a = t.get("artist")
        if a and a not in artists:
            artists.append(a)

    genres_str = ", ".join(genres[:6]) or "a mix of genres"
    artists_str = ", ".join(artists[:8]) or "various artists"

    if examples:
        example_block = "\n".join(f"- {e}" for e in examples)
    else:
        example_block = "- daily music rotation, been listening to a lot more lately"

    title_line = f'\nThe post is titled "{cover_title}".' if cover_title else ""

    return f"""You write short TikTok captions for my music "daily rotation" slideshow, in MY voice.

Rules:
- all lowercase, casual and slangy (use words like lowk, ngl, tbf, tbh, man, lol when it feels natural)
- 1 to 2 short lines, just a quick personal thought about what i've been into lately
- mostly comment on the vibe, genres or mood — this is a rotation, NOT a concert recap
- do NOT name any specific song or album titles, and do NOT invent artists, tours or events. only name an artist if they are in the list below; otherwise just talk about the genres and vibe
- at most one emoji, and only from this set: 🥹 🫩 🥀 😭 (or no emoji). never use music-note emojis or 😊
- NO hashtags (those are added separately)
- under 140 characters

Here are real examples of my captions — study the voice, do not copy them:
{example_block}

This rotation leans on these genres: {genres_str}
(artists included, only use if it feels natural: {artists_str}).{title_line}

Write ONE new caption in my voice (text only, no hashtags):"""


def _call_ollama(prompt: str) -> str | None:
    payload = {
        "model": CAPTION_MODEL,
        "prompt": prompt,
        "stream": False,
        "keep_alive": KEEP_ALIVE,
        "options": {"temperature": 0.7, "top_p": 0.9, "num_predict": 90},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, OSError):
        # Connection refused (Ollama down), timeout, HTTP error, bad JSON.
        return None
    return (body.get("response") or "").strip()


def _tidy_line(ln: str) -> str:
    """Strip bullet markers, surrounding quotes, and hashtags from one line."""
    ln = re.sub(r"^[-*]\s*", "", ln).strip()
    ln = re.sub(r"[#@]\S+", "", ln)  # we add hashtags ourselves
    ln = ln.strip().strip('"').strip("“”").strip("'").strip()
    return re.sub(r"[ \t]+", " ", ln).strip()


def _clean_caption_text(text: str) -> str:
    """Sanitize raw model output into a caption body (no hashtags, <=2 lines).

    Small models often wrap the real caption in chatter, e.g.::

        here's a caption for your rotation:

        "lowk been deep in my edm bag lately 🫩"

    So we drop leading preamble lines (a lead-in ending in ":" or starting with
    a known meta phrase) and only stop at a meta line once we already have
    caption content — never discarding a good caption that follows a preamble.
    """
    if not text:
        return ""

    lines = [_tidy_line(ln) for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]

    # Drop leading preamble/lead-in lines ("here's a caption:", "caption:", ...).
    while lines:
        low = lines[0].lower()
        if low.endswith(":") or any(low.startswith(p) for p in _META_PREFIXES):
            lines.pop(0)
        else:
            break

    kept: list[str] = []
    for ln in lines:
        low = ln.lower()
        if kept and any(low.startswith(p) for p in _META_PREFIXES):
            break  # trailing explanation after the real caption
        kept.append(ln)
        if len(kept) >= 2:  # captions are at most 2 short lines
            break

    return "\n".join(kept).strip()


def generate_llm_caption(tracks: list[dict], cover_title: str | None = None) -> str | None:
    """Return an AI-generated caption body (no hashtags), or None on any failure.

    Args:
        tracks: track dicts with keys ``artist``, ``title``, ``primary_bucket``.
        cover_title: optional cover-slide title used as a soft hint.
    """
    if not tracks:
        return None
    examples = _load_examples()
    prompt = _build_prompt(tracks, examples, cover_title)
    raw = _call_ollama(prompt)
    if raw is None:
        return None
    text = _clean_caption_text(raw)
    if len(text) < 8:  # empty or junk response
        return None
    return text
