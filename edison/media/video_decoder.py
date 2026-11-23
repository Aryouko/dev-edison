"""Frame accurate video decoding with PyAV."""

from collections import OrderedDict

import av
import numpy as np


class VideoDecoder:
    """Return the picture of a video file at any time.

    Reading forward (playback) decodes frames one after the other; jumping
    backward or far ahead seeks to the previous key frame first. The last
    converted pictures are kept in a small cache for scrubbing.

    A decoder must only be used by one thread.

    Parameters
    ----------
    path : str
        Video file.
    """

    CACHE_SIZE = 32
    MAX_FORWARD_DECODE = 2.0  # seconds; beyond this, seeking is faster

    def __init__(self, path: str):
        self._container = av.open(path)
        self._stream = self._container.streams.video[0]
        self._stream.thread_type = "AUTO"
        rate = self._stream.average_rate or self._stream.guessed_rate or 30
        self._frame_duration = 1.0 / float(rate)
        start_time = self._stream.start_time
        self._offset = float(start_time * self._stream.time_base) if start_time is not None else 0.0
        self._frames = None
        self._current = None  # last decoded frame whose time is <= requested time
        self._pending = None  # next decoded frame, not displayed yet
        self._cache: OrderedDict = OrderedDict()

    def close(self) -> None:
        """Release the file."""
        self._container.close()

    def frame_at(self, time: float, width: int, height: int) -> np.ndarray | None:
        """Return the picture displayed at ``time``.

        Parameters
        ----------
        time : float
            Time in the source file, in seconds.
        width, height : int
            Size of the returned picture.

        Returns
        -------
        numpy.ndarray or None
            RGB picture of shape ``(height, width, 3)``, None if nothing can be decoded.
        """
        key = (int(time / self._frame_duration + 1e-6), width, height)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        frame = self._decode_at(time)
        if frame is None:
            return None
        picture = frame.to_ndarray(format="rgb24", width=width, height=height)
        self._cache[key] = picture
        if len(self._cache) > self.CACHE_SIZE:
            self._cache.popitem(last=False)
        return picture

    def _time_of(self, frame) -> float:
        if frame.pts is None:
            return frame.time or 0.0
        return float(frame.pts * frame.time_base) - self._offset

    def _decode_at(self, time: float):
        tolerance = self._frame_duration / 2
        current = self._time_of(self._current) if self._current is not None else None
        if current is None or time < current - tolerance or time > current + self.MAX_FORWARD_DECODE:
            self._seek(time)
        self._advance_to(time + tolerance)
        return self._current if self._current is not None else self._pending

    def _seek(self, time: float) -> None:
        target = int(max(time + self._offset, 0.0) / self._stream.time_base)
        self._container.seek(target, stream=self._stream, backward=True, any_frame=False)
        self._frames = self._container.decode(self._stream)
        self._current = None
        self._pending = None

    def _advance_to(self, limit: float) -> None:
        """Decode frames until the next one starts after ``limit``."""
        while True:
            if self._pending is None:
                try:
                    self._pending = next(self._frames)
                except (StopIteration, av.error.EOFError):
                    return
            if self._time_of(self._pending) <= limit:
                self._current, self._pending = self._pending, None
            else:
                return
