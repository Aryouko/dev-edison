"""Application-wide constants and paths (no Qt dependency)."""

import os
from pathlib import Path

APP_NAME = "Edison"
PROJECT_EXTENSION = ".edison"
PROJECT_FORMAT_VERSION = 1

VIDEO_EXTENSIONS = (".mp4", ".mkv", ".mov", ".avi", ".webm")
AUDIO_EXTENSIONS = (".mp3", ".wav", ".ogg", ".flac", ".m4a")

# Every audio source is decoded to this format so clips can be mixed directly.
SAMPLE_RATE = 48_000
CHANNELS = 2

DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
DEFAULT_FPS = 30

# Loudness values per second kept for the waveforms drawn on the audio clips
WAVEFORM_RATE = 100

# The preview is rendered in a box of this size (the export uses the real size).
PREVIEW_MAX_WIDTH = 960
PREVIEW_MAX_HEIGHT = 720

ASSETS_DIR = Path(__file__).parent / "assets"


def projects_dir() -> Path:
    """Return the default folder where new projects are saved.

    Returns
    -------
    Path
        ``~/Documents/Edison`` (created if needed).
    """
    path = Path(os.environ.get("EDISON_PROJECTS_DIR", Path.home() / "Documents" / "Edison"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    """Return the folder holding decoded audio files.

    Returns
    -------
    Path
        Cache folder (created if needed).
    """
    default = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".cache")) / "Edison" / "cache"
    path = Path(os.environ.get("EDISON_CACHE_DIR", default))
    path.mkdir(parents=True, exist_ok=True)
    return path
