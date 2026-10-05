"""Analysis of a file at import (CDC "Onglet Import" > "Charger une vidéo (FFmpeg)")."""

from pathlib import Path

import numpy as np

from edison.config import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS
from edison.model.project import Media


class UnsupportedMediaError(Exception):
    """Raised when a file cannot be imported. The message is shown to the user."""


def accepted_formats_text() -> str:
    """Return the accepted formats, for the error message required by the CDC."""
    video = ", ".join(ext[1:] for ext in VIDEO_EXTENSIONS)
    audio = ", ".join(ext[1:] for ext in AUDIO_EXTENSIONS)
    return f"Vidéo : {video}\nAudio : {audio}"


def is_supported(path: str) -> bool:
    """Return True if the extension of ``path`` is accepted."""
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS + AUDIO_EXTENSIONS


def probe_media(path: str) -> Media:
    """Open a file with FFmpeg and read its properties.

    Parameters
    ----------
    path : str
        File to import.

    Returns
    -------
    Media
        New library entry (``id=new_id()``, absolute ``path``, kind, duration, size, fps...).

    Raises
    ------
    UnsupportedMediaError
        If the format is not accepted or the file cannot be read.

    TODO(S2) "Import fonctionnel" — with PyAV::

        container = av.open(path)            # raises av.error.FFmpegError if unreadable
        video = container.streams.video[0]   # if container.streams.video is not empty
        audio = container.streams.audio[0]   # if container.streams.audio is not empty
        duration = container.duration / av.time_base
        width, height = video.codec_context.width, video.codec_context.height
        fps = float(video.average_rate)

    A file with a video extension must have a video stream; an audio file must have sound.
    """
    if not is_supported(path):
        raise UnsupportedMediaError("Format non pris en charge.")
    raise NotImplementedError("TODO(S2): probe_media")


def video_thumbnail(media: Media, max_width: int = 320) -> np.ndarray | None:
    """Return a small RGB picture of the video, drawn on its tile in the "Import" tab.

    TODO(S2): decode one frame near the beginning (e.g. at 10 % of the duration, 1 s at most)
    with :class:`edison.media.video_decoder.VideoDecoder`.
    """
    raise NotImplementedError("TODO(S2): video_thumbnail")
