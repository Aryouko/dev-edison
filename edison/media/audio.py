"""Audio decoding: every audio stream is converted once to raw samples on disk.

The decoded file is opened with ``numpy.memmap``: samples are read from disk
on demand, so long files do not fill the memory, and several threads (playback,
export) can read them at the same time.
"""

import hashlib
import os
import subprocess
import threading
from pathlib import Path

import numpy as np

from edison.config import CHANNELS, SAMPLE_RATE, cache_dir
from edison.media.ffmpeg import NO_WINDOW, ffmpeg_exe
from edison.model.project import Media


class AudioDecodeError(Exception):
    """Raised when FFmpeg cannot decode the audio of a file."""


def decode_to_cache(path: str) -> Path:
    """Decode the audio of a file to raw 32-bit float samples.

    Parameters
    ----------
    path : str
        Audio or video file.

    Returns
    -------
    Path
        Cache file (reused while the source file is unchanged).
    """
    stat = os.stat(path)
    key = hashlib.sha1(f"{os.path.abspath(path)}|{stat.st_size}|{stat.st_mtime_ns}".encode()).hexdigest()
    target = cache_dir() / f"{key}.f32"
    if target.exists():
        return target
    partial = target.with_suffix(".part")
    command = [ffmpeg_exe(), "-v", "error", "-y", "-i", path, "-vn",
               "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE), "-f", "f32le", str(partial)]
    result = subprocess.run(command, capture_output=True, creationflags=NO_WINDOW)
    if result.returncode != 0:
        partial.unlink(missing_ok=True)
        message = result.stderr.decode(errors="replace").strip().splitlines()
        raise AudioDecodeError(message[-1] if message else "Décodage audio impossible.")
    os.replace(partial, target)
    return target


def open_samples(path: Path) -> np.ndarray:
    """Open a decoded cache file as an array of shape ``(samples, CHANNELS)``."""
    frame_bytes = 4 * CHANNELS
    count = path.stat().st_size // frame_bytes
    if count == 0:
        return np.zeros((0, CHANNELS), dtype=np.float32)
    return np.memmap(path, dtype=np.float32, mode="r", shape=(count, CHANNELS))


class AudioStore:
    """Decoded samples of every media of the project, shared between threads."""

    def __init__(self):
        self._samples: dict[str, np.ndarray] = {}
        self._lock = threading.Lock()

    def get(self, media_id: str) -> np.ndarray | None:
        """Return the samples of a media if they are already decoded."""
        return self._samples.get(media_id)

    def load(self, media: Media) -> np.ndarray:
        """Decode (or reuse) the audio of a media. Blocking: call it from a worker thread."""
        with self._lock:
            if media.id in self._samples:
                return self._samples[media.id]
        samples = open_samples(decode_to_cache(media.path))
        with self._lock:
            self._samples[media.id] = samples
        return samples

    def discard(self, media_id: str) -> None:
        """Forget the samples of a media."""
        with self._lock:
            self._samples.pop(media_id, None)

    def clear(self) -> None:
        """Forget every media (when the project is closed)."""
        with self._lock:
            self._samples.clear()


def waveform_peaks(samples: np.ndarray, bins: int) -> np.ndarray:
    """Return ``bins`` normalised peak values, used to draw a waveform.

    Parameters
    ----------
    samples : numpy.ndarray
        Samples of shape ``(n, CHANNELS)``.
    bins : int
        Number of values to return.
    """
    if len(samples) == 0:
        return np.zeros(bins, dtype=np.float32)
    step = max(1, len(samples) // (bins * 64))  # sub-sampling is enough for a drawing
    mono = np.abs(np.asarray(samples[::step, 0]))
    if len(mono) < bins:
        mono = np.pad(mono, (0, bins - len(mono)))
    usable = len(mono) // bins * bins
    peaks = mono[:usable].reshape(bins, -1).max(axis=1)
    top = float(peaks.max())
    return (peaks / top if top > 0 else peaks).astype(np.float32)
