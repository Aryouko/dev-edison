"""Analysis of a file at import (CDC "Onglet Import" > "Charger une vidéo (FFmpeg)")."""

from pathlib import Path

import av
import numpy as np

from edison.config import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS
from edison.model.project import AUDIO, VIDEO, Media, new_id


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


def _duration(container, stream) -> float:
    """Duration of the file in seconds (container first, then the stream as a fallback)."""
    if container.duration is not None:
        return container.duration / av.time_base
    if stream is not None and stream.duration is not None and stream.time_base is not None:
        return float(stream.duration * stream.time_base)
    return 0.0


def probe_media(path: str) -> Media:
    """Open a file with FFmpeg and read its properties.

    Parameters
    ----------
    path : str
        File to import.

    Returns
    -------
    Media
        New library entry (``id=new_id()``, absolute ``path``, kind, duration, fps...).

    Raises
    ------
    UnsupportedMediaError
        If the format is not accepted or the file cannot be read.
    """
    if not is_supported(path):
        raise UnsupportedMediaError("Format non pris en charge.")

    file_path = Path(path).resolve()
    extension = file_path.suffix.lower()
    try:
        with av.open(str(file_path)) as container:
            video = container.streams.video[0] if container.streams.video else None
            audio = container.streams.audio[0] if container.streams.audio else None

            if extension in VIDEO_EXTENSIONS and video is None:
                raise UnsupportedMediaError("Le fichier ne contient pas d'image vidéo.")
            if extension in AUDIO_EXTENSIONS and audio is None:
                raise UnsupportedMediaError("Le fichier ne contient pas de son.")

            duration = _duration(container, video or audio)
            if duration <= 0:
                raise UnsupportedMediaError("Durée du fichier illisible.")

            if video is not None:
                return Media(
                    id=new_id(),
                    path=str(file_path),
                    kind=VIDEO,
                    duration=duration,
                    has_audio=audio is not None,
                    width=video.codec_context.width,
                    height=video.codec_context.height,
                    fps=float(video.average_rate) if video.average_rate else 0.0,
                )
            return Media(id=new_id(), path=str(file_path), kind=AUDIO, duration=duration, has_audio=True)
    except UnsupportedMediaError:
        raise
    except (av.error.FFmpegError, OSError) as error:
        raise UnsupportedMediaError("Fichier illisible ou corrompu.") from error


def video_thumbnail(media: Media, max_width: int = 320) -> np.ndarray | None:
    """Return a small RGB picture of the video, drawn on its tile in the "Import" tab.

    The frame is taken at 10 % of the duration (1 s at most). Returns None for an audio
    media or if nothing can be decoded (a missing thumbnail must not prevent the import).
    """
    if media.kind != VIDEO or not media.width or not media.height:
        return None
    from edison.media.video_decoder import VideoDecoder

    width = min(max_width, media.width)
    height = max(1, round(width * media.height / media.width))
    try:
        decoder = VideoDecoder(media.path)
    except (av.error.FFmpegError, OSError, IndexError):
        return None
    try:
        return decoder.frame_at(min(media.duration * 0.1, 1.0), width, height)
    except av.error.FFmpegError:
        return None
    finally:
        decoder.close()
