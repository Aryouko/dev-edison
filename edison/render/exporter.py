"""Export of the timeline to a video or audio file.

Frames produced by :func:`render_frame` are sent to FFmpeg through a pipe;
the sound mixed by :func:`mix_audio` is written to a temporary WAV file first.
"""

import math
import os
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from edison.config import CHANNELS, SAMPLE_RATE
from edison.media.audio import AudioStore
from edison.media.ffmpeg import NO_WINDOW, ffmpeg_exe
from edison.model.project import Project
from edison.render.audio_effects import AudioEffectCache
from edison.render.renderer import MediaSources, mix_audio, render_frame


class ExportError(Exception):
    """Raised when the export fails. The message is shown to the user."""


class ExportCancelled(Exception):
    """Raised when the user cancels the export."""


@dataclass(frozen=True)
class ExportFormat:
    """An output format offered in the export tab."""

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
    """Video bitrate in bits per second."""
    return int(settings.width * settings.height * settings.fps * QUALITIES[settings.quality].bits_per_pixel)


def audio_bitrate(settings: ExportSettings) -> int:
    """Audio bitrate in bits per second."""
    if settings.format == "wav":
        return SAMPLE_RATE * CHANNELS * 16
    return QUALITIES[settings.quality].audio_kbps * 1000


def estimate_size(settings: ExportSettings, duration: float) -> int:
    """Approximate size of the exported file, in bytes."""
    bitrate = audio_bitrate(settings)
    if not FORMATS[settings.format].audio_only:
        bitrate += video_bitrate(settings)
    return int(bitrate * duration / 8)


def _codec_arguments(settings: ExportSettings) -> list[str]:
    video, audio = str(video_bitrate(settings)), str(audio_bitrate(settings))
    if settings.format in ("mp4", "mkv"):
        arguments = ["-c:v", "libx264", "-preset", "veryfast", "-b:v", video,
                     "-maxrate", str(int(video_bitrate(settings) * 1.5)), "-bufsize", str(video_bitrate(settings) * 2),
                     "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", audio]
        return arguments + (["-movflags", "+faststart"] if settings.format == "mp4" else [])
    if settings.format == "webm":
        return ["-c:v", "libvpx-vp9", "-b:v", video, "-deadline", "realtime", "-cpu-used", "8", "-row-mt", "1",
                "-pix_fmt", "yuv420p", "-c:a", "libopus", "-b:a", audio]
    if settings.format == "mp3":
        return ["-c:a", "libmp3lame", "-b:a", audio]
    return ["-c:a", "pcm_s16le"]


def export_project(project: Project, settings: ExportSettings, store: AudioStore,
                   on_progress=None, is_cancelled=None, effects: AudioEffectCache | None = None) -> None:
    """Export the timeline.

    Parameters
    ----------
    project : Project
        Exported project (a copy: it must not change during the export).
    settings : ExportSettings
        Output file and encoding options.
    store : AudioStore
        Decoded audio of the media.
    on_progress : callable, optional
        Called with ``(fraction, remaining_seconds or None)``.
    is_cancelled : callable, optional
        Returns True when the user asks to stop.
    effects : AudioEffectCache, optional
        Processed sound of the clips with audio effects (a new cache if not given).

    Raises
    ------
    ExportError
        If the timeline is empty or the file cannot be written.
    ExportCancelled
        If ``is_cancelled`` returned True.
    """
    duration = project.duration
    if duration <= 0:
        raise ExportError("La trame est vide : ajoutez au moins un clip avant d'exporter.")
    output = Path(settings.path)
    if not output.parent.is_dir():
        raise ExportError("Le dossier de destination n'existe pas.")
    if not os.access(output.parent, os.W_OK):
        raise ExportError("Droits insuffisants pour écrire dans ce dossier.")

    started = time.perf_counter()

    def report(fraction: float) -> None:
        if on_progress:
            elapsed = time.perf_counter() - started
            remaining = elapsed / fraction * (1 - fraction) if fraction > 0.02 else None
            on_progress(min(fraction, 1.0), remaining)

    def check_cancelled() -> None:
        if is_cancelled and is_cancelled():
            raise ExportCancelled()

    effects = effects or AudioEffectCache(store)
    audio_only = FORMATS[settings.format].audio_only
    audio_share = 0.9 if audio_only else 0.1  # part of the progress bar used by the audio mix
    with tempfile.TemporaryDirectory(prefix="edison-export-") as folder:
        mix_path, log_path = Path(folder) / "mix.wav", Path(folder) / "ffmpeg.log"
        try:
            _write_mix(project, duration, store, effects, mix_path, lambda f: report(f * audio_share),
                       check_cancelled)
            if audio_only:
                command = [ffmpeg_exe(), "-y", "-v", "error", "-i", str(mix_path), *_codec_arguments(settings),
                           str(output)]
                with open(log_path, "wb") as log:
                    code = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=log,
                                          creationflags=NO_WINDOW).returncode
            else:
                code = _encode_video(project, settings, duration, mix_path, log_path,
                                     lambda f: report(audio_share + f * (1 - audio_share)), check_cancelled)
        except ExportCancelled:
            output.unlink(missing_ok=True)
            raise
        except OSError as error:
            output.unlink(missing_ok=True)
            raise ExportError(_explain(str(error))) from error
        if code != 0:
            output.unlink(missing_ok=True)
            raise ExportError(_explain(log_path.read_text(errors="replace")))
    report(1.0)


def _write_mix(project, duration, store, effects, path, report, check_cancelled) -> None:
    """Write the mixed sound of the whole timeline to a 16-bit WAV file."""
    total = int(round(duration * SAMPLE_RATE))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        position = 0
        while position < total:
            check_cancelled()
            count = min(SAMPLE_RATE, total - position)
            block = mix_audio(project, position, count, store, effects, compute=True)
            wav.writeframes((block * 32767).astype("<i2").tobytes())
            position += count
            report(position / total)


def _encode_video(project, settings, duration, mix_path, log_path, report, check_cancelled) -> int:
    """Send every frame to FFmpeg. Returns the FFmpeg exit code."""
    width, height, fps = settings.width, settings.height, settings.fps
    frame_count = max(1, math.ceil(duration * fps - 1e-9))
    command = [ffmpeg_exe(), "-y", "-v", "error",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
               "-i", str(mix_path), "-map", "0:v:0", "-map", "1:a:0", *_codec_arguments(settings),
               settings.path]
    sources = MediaSources()
    with open(log_path, "wb") as log:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log,
                                   creationflags=NO_WINDOW)
        try:
            for index in range(frame_count):
                check_cancelled()
                frame = render_frame(project, index / fps, width, height, sources)
                try:
                    process.stdin.write(np.ascontiguousarray(frame).tobytes())
                except OSError:  # FFmpeg stopped: its log explains why
                    break
                report((index + 1) / frame_count * 0.99)
            try:
                process.stdin.close()
            except OSError:
                pass
            return process.wait()
        finally:
            sources.close()
            if process.poll() is None:
                process.kill()
                process.wait()


def _explain(log: str) -> str:
    """Turn an FFmpeg or system error into a message for the user."""
    lowered = log.lower()
    if "no space left" in lowered or "errno 28" in lowered:
        return "Espace disque insuffisant pour écrire le fichier."
    if "permission denied" in lowered or "errno 13" in lowered:
        return "Droits insuffisants pour écrire ce fichier (il est peut-être ouvert dans un autre logiciel)."
    lines = [line for line in log.strip().splitlines() if line.strip()]
    return "L'encodage a échoué :\n" + "\n".join(lines[-3:]) if lines else "L'encodage a échoué."
