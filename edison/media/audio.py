"""Audio decoding (sprint S4 "lecture audio").

Suggested approach: decode the sound of each media ONCE, at import, to raw
float samples (48 kHz stereo, see config.py) stored in ``cache_dir()``; then open
the file with ``numpy.memmap``: samples are read from the disk only when needed,
and several threads (playback, export) can read them at the same time.

FFmpeg command line that does the conversion::

    [ffmpeg_exe(), "-v", "error", "-y", "-i", path, "-vn",
     "-ac", "2", "-ar", "48000", "-f", "f32le", output_file]
"""

import numpy as np

from edison.model.project import Media


class AudioStore:
    """Decoded samples of every media of the project, shared between threads.

    TODO(S4): a dictionary ``media_id -> numpy array (samples, CHANNELS)`` protected by a
    ``threading.Lock`` (the import threads add entries while the audio thread reads them).
    """

    def get(self, media_id: str) -> np.ndarray | None:
        """Return the samples of a media if they are already decoded (never blocks)."""
        return None  # TODO(S4)

    def load(self, media: Media) -> np.ndarray:
        """Decode (or reuse) the audio of a media. Slow: call it from a worker thread."""
        raise NotImplementedError("TODO(S4): AudioStore.load")

    def clear(self) -> None:
        """Forget every media (when the project is closed)."""
        # TODO(S4)


def waveform_peaks(samples: np.ndarray, bins: int) -> np.ndarray:
    """Return ``bins`` loudness values between 0 and 1, to draw a waveform.

    Used for the tile of an audio file in the "Import" tab and for the waveform drawn
    on the audio clips of the timeline.

    TODO(S4): cut the samples in ``bins`` slices and keep the maximum of ``abs()`` of each
    slice (``reshape(bins, -1).max(axis=1)``), then divide by the global maximum.
    """
    raise NotImplementedError("TODO(S4): waveform_peaks")
