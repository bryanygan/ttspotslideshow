"""Central configuration. Loads settings from the .env file once, on import.

Everything that touches credentials or file paths should import from here so we
have a single source of truth.
"""

from pathlib import Path

from dotenv import load_dotenv
import os

# Load .env from the project root into environment variables.
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

# --- Spotify credentials (read by spotipy via these exact env var names) ---
CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback")

# OAuth scopes we need:
#   user-read-recently-played -> the logger (last 50 plays)
#   user-top-read             -> top tracks/artists (used in later phases)
SCOPES = "user-read-recently-played user-top-read"

# --- Local file paths ---
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "plays.db"

# Where spotipy caches the OAuth token so you only log in once.
TOKEN_CACHE_PATH = PROJECT_ROOT / ".spotify_cache"


def ensure_dirs() -> None:
    """Create local directories that must exist before we read/write data."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def assert_credentials() -> None:
    """Fail fast with a clear message if .env isn't set up yet."""
    missing = [
        name
        for name, value in (
            ("SPOTIPY_CLIENT_ID", CLIENT_ID),
            ("SPOTIPY_CLIENT_SECRET", CLIENT_SECRET),
        )
        if not value
    ]
    if missing:
        raise SystemExit(
            "Missing Spotify credentials: "
            + ", ".join(missing)
            + "\nCopy .env.example to .env and fill in your values "
            "(see README.md, Phase 0)."
        )
