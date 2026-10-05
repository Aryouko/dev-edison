"""Access to the FFmpeg executable shipped with ``imageio-ffmpeg``.

Use :func:`ffmpeg_exe` for every FFmpeg command line (audio decoding, export):
the whole team then uses the same FFmpeg version, with the same encoders,
without installing FFmpeg by hand.
"""

import subprocess
import sys

import imageio_ffmpeg

# Pass ``creationflags=NO_WINDOW`` to subprocess: no console window pops up on Windows.
NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def ffmpeg_exe() -> str:
    """Return the path of the FFmpeg executable."""
    return imageio_ffmpeg.get_ffmpeg_exe()
