"""Reading the properties of an imported file."""

from pathlib import Path

import av
import numpy as np

from edison.config import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS
from edison.media.video_decoder import VideoDecoder
from edison.model.project import AUDIO, VIDEO, Media, new_id
from edison.utils import fit_size


class UnsupportedMediaError(Exception):
    """Raised when a file cannot be imported. The message is shown to the user."""


def accepted_formats_text() -> str:
    """Return the list of accepted formats, shown in error messages."""
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
        New library entry.

    Raises
    ------
    UnsupportedMediaError
        If the format is not accepted or the file cannot be read.
    """
    if not is_supported(path):
        raise UnsupportedMediaError("Format non pris en charge.")
    is_video_file = Path(path).suffix.lower() in VIDEO_EXTENSIONS
    try:
        container = av.open(path)
    except (av.error.FFmpegError, OSError) as error:
        raise UnsupportedMediaError("Fichier illisible ou corrompu.") from error
    with container:
        video = container.streams.video[0] if container.streams.video else None
        audio = container.streams.audio[0] if container.streams.audio else None
        if is_video_file and video is None:
            raise UnsupportedMediaError("Le fichier ne contient pas d'image vidéo.")
        if not is_video_file and audio is None:
            raise UnsupportedMediaError("Le fichier ne contient pas de son.")
        duration = _duration(container, video if is_video_file else audio)
        if duration <= 0:
            raise UnsupportedMediaError("Durée du fichier inconnue.")
        media = Media(id=new_id(), path=str(Path(path).resolve()), kind=VIDEO if is_video_file else AUDIO,
                      duration=duration, has_audio=audio is not None)
        if is_video_file:
            media.width = video.codec_context.width
            media.height = video.codec_context.height
            media.fps = float(video.average_rate or video.guessed_rate or 30)
    return media


def _duration(container, stream) -> float:
    if stream.duration is not None and stream.time_base is not None:
        return float(stream.duration * stream.time_base)
    if container.duration is not None:
        return container.duration / av.time_base
    return 0.0


def video_thumbnail(media: Media, max_width: int = 320) -> np.ndarray | None:
    """Return a picture of the video (at 10 % of its duration, 1 s at most)."""
    width, height = fit_size(media.width, media.height, max_width, max_width)
    decoder = VideoDecoder(media.path)
    try:
        return decoder.frame_at(min(1.0, media.duration * 0.1), width, height)
    finally:
        decoder.close()
