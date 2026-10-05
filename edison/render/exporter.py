"""Export of the timeline to a file (sprint S6, CDC "Onglet Export").

The options offered by the export tab (formats, qualities) and the size estimate
are ready; :func:`export_project` is to be written.
"""

from dataclasses import dataclass

from edison.config import CHANNELS, SAMPLE_RATE
from edison.media.audio import AudioStore
from edison.model.project import Project


class ExportError(Exception):
    """Raised when the export fails. The message is shown to the user."""


class ExportCancelled(Exception):
    """Raised when the user clicks "Annuler" during the export."""


@dataclass(frozen=True)
class ExportFormat:
    """An output format of the export tab."""

    label: str
    extension: str
    audio_only: bool


FORMATS = {
    "mp4": ExportFormat("MP4 (H.264 + AAC)", ".mp4", False),
    "mkv": ExportFormat("MKV (H.264 + AAC)", ".mkv", False),
    "webm": ExportFormat("WebM (VP9 + Opus)", ".webm", False),
    "mp3": ExportFormat("MP3 (audio seul)", ".mp3", True),
    "wav": ExportFormat("WAV (audio seul)", ".wav", True),
}


@dataclass(frozen=True)
class Quality:
    """A quality level: video bits per pixel and audio bitrate."""

    label: str
    bits_per_pixel: float
    audio_kbps: int


QUALITIES = {
    "low": Quality("Basse", 0.04, 128),
    "medium": Quality("Moyenne", 0.08, 192),
    "high": Quality("Haute", 0.15, 256),
}


@dataclass
class ExportSettings:
    """Choices made in the export tab."""

    path: str
    format: str = "mp4"
    width: int = 1920
    height: int = 1080
    fps: int = 30
    quality: str = "medium"


def video_bitrate(settings: ExportSettings) -> int:
    """Video bitrate in bits per second (``-b:v`` of FFmpeg)."""
    return int(settings.width * settings.height * settings.fps * QUALITIES[settings.quality].bits_per_pixel)


def audio_bitrate(settings: ExportSettings) -> int:
    """Audio bitrate in bits per second (``-b:a`` of FFmpeg)."""
    if settings.format == "wav":
        return SAMPLE_RATE * CHANNELS * 16
    return QUALITIES[settings.quality].audio_kbps * 1000


def estimate_size(settings: ExportSettings, duration: float) -> int:
    """Approximate size of the exported file, in bytes ("estimation du poids")."""
    bitrate = audio_bitrate(settings)
    if not FORMATS[settings.format].audio_only:
        bitrate += video_bitrate(settings)
    return int(bitrate * duration / 8)


def export_project(project: Project, settings: ExportSettings, store: AudioStore,
                   on_progress=None, is_cancelled=None) -> None:
    """Export the timeline. Called from a worker thread (the interface stays usable).

    Parameters
    ----------
    project : Project
        A COPY of the project (it must not change during the export).
    settings : ExportSettings
        Output file and encoding options.
    store : AudioStore
        Decoded audio of the media.
    on_progress : callable, optional
        Called with ``(fraction, remaining_seconds or None)`` for the progress bar.
    is_cancelled : callable, optional
        Returns True when the user clicked "Annuler": raise :class:`ExportCancelled`.

    Raises
    ------
    ExportError
        Empty timeline, missing rights, full disk... (explicit message required by the CDC).

    TODO(S6) — principle:
        1. mix the whole sound with ``mix_audio`` into a temporary WAV file (module ``wave``);
        2. start FFmpeg (``ffmpeg_exe()``) reading raw pictures on its standard input:
           ``-f rawvideo -pix_fmt rgb24 -s WxH -r FPS -i -`` plus ``-i mix.wav``, the codecs
           (libx264 + aac for mp4/mkv, libvpx-vp9 + libopus for webm, libmp3lame, pcm_s16le)
           and the bitrates above;
        3. for each frame: ``render_frame(...)`` -> ``process.stdin.write(frame.tobytes())``;
        4. redirect FFmpeg errors to a file and turn them into a French message.
    """
    raise NotImplementedError("TODO(S6): export_project")
