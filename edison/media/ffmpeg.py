"""Access to the FFmpeg executable shipped with ``imageio-ffmpeg``."""

import subprocess
import sys

import imageio_ffmpeg

# Prevents a console window from popping up for each FFmpeg call on Windows.
NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def ffmpeg_exe() -> str:
    """Return the path of the FFmpeg executable.

    Using the binary of ``imageio-ffmpeg`` guarantees that every member of the
    team uses the same FFmpeg version, with the same encoders.
    """
    return imageio_ffmpeg.get_ffmpeg_exe()
