"""Application-wide constants and paths (no Qt dependency).

Put here every value shared by several modules (formats, sizes, folders...),
instead of writing it in several places.
"""

import os
from pathlib import Path

APP_NAME = "Edison"
PROJECT_EXTENSION = ".edison"
PROJECT_FORMAT_VERSION = 1

# Formats accepted by the import (CDC "Onglet Import"): shown in the error message.
VIDEO_EXTENSIONS = (".mp4", ".mkv", ".mov", ".avi", ".webm")
AUDIO_EXTENSIONS = (".mp3", ".wav", ".ogg", ".flac", ".m4a")

# Every audio source will be decoded to this format so that clips can be mixed directly.
SAMPLE_RATE = 48_000
CHANNELS = 2

# Project size used until a first video is imported.
DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
DEFAULT_FPS = 30

# The preview is rendered in a box of this size (the export uses the real size).
PREVIEW_MAX_WIDTH = 960
PREVIEW_MAX_HEIGHT = 720

ASSETS_DIR = Path(__file__).parent / "assets"


def projects_dir() -> Path:
    """Return the default folder where new projects are saved.

    Returns
    -------
    Path
        ``~/Documents/Edison`` (created if needed). The tests use another folder
        through the ``EDISON_PROJECTS_DIR`` environment variable.
    """
    path = Path(os.environ.get("EDISON_PROJECTS_DIR", Path.home() / "Documents" / "Edison"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    """Return the folder for temporary data (decoded audio, thumbnails...).

    Returns
    -------
    Path
        Cache folder (created if needed), overridable with ``EDISON_CACHE_DIR``.
    """
    default = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".cache")) / "Edison" / "cache"
    path = Path(os.environ.get("EDISON_CACHE_DIR", default))
    path.mkdir(parents=True, exist_ok=True)
    return path
