"""Frame accurate video decoding with PyAV (sprints S3-S4)."""

from collections import OrderedDict

import av
import numpy as np

CACHE_SIZE = 32  # converted pictures kept in memory (CDC: frame cache)
MAX_FORWARD_GAP = 2.0  # beyond this jump forward (seconds), seeking is faster than decoding


class VideoDecoder:
    """Return the picture of a video file at any time.

    A decoder keeps the file open; it must only be used by ONE thread
    (the preview thread and the export thread each open their own decoders).

    Parameters
    ----------
    path : str
        Video file.

    Raises
    ------
    av.error.FFmpegError, OSError
        If the file cannot be opened.

    Principle:
        * reading forward (playback): decode the next frames of the current stream;
        * jumping backward or far ahead: ``container.seek(...)`` goes to the previous key frame,
          then decode forward until the requested time;
        * the last converted pictures are kept in a small LRU cache.
    """

    def __init__(self, path: str):
        self.path = path
        self._container = av.open(path)
        try:
            self._stream = self._container.streams.video[0]
        except IndexError:
            self._container.close()
            raise
        self._stream.thread_type = "AUTO"
        rate = self._stream.average_rate
        self._frame_duration = 1.0 / float(rate) if rate else 1.0 / 25
        start = self._stream.start_time
        self._start = float(start * self._stream.time_base) if start is not None else 0.0
        self._frames = None  # iterator of decoded frames (None: seek needed)
        self._current = None  # last decoded frame displayed at or before the requested time
        self._pending = None  # first decoded frame after it (read again on the next call)
        self._cache: OrderedDict[tuple[int, int, int], np.ndarray] = OrderedDict()

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
            RGB picture ``(height, width, 3)``, uint8; None if nothing can be decoded.
        """
        time = max(0.0, time)
        key = (round(time / self._frame_duration), width, height)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        frame = self._decode(time)
        if frame is None:
            return None
        picture = frame.to_ndarray(format="rgb24", width=width, height=height)
        self._cache[key] = picture
        if len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)
        return picture

    def close(self) -> None:
        """Release the file."""
        self._frames = self._current = self._pending = None
        self._cache.clear()
        self._container.close()

    # ---------------------------------------------------------------- internals
    def _time(self, frame) -> float:
        """Time of a decoded frame, from the start of the file."""
        return frame.time - self._start

    def _seek(self, time: float) -> None:
        offset = int((time + self._start) / self._stream.time_base)
        self._container.seek(offset, stream=self._stream, backward=True, any_frame=False)
        self._frames = self._container.decode(self._stream)
        self._current = self._pending = None

    def _decode(self, time: float):
        """Return the frame displayed at ``time`` (the last one starting before it)."""
        current = self._time(self._current) if self._current is not None else None
        if self._frames is None or current is None or time < current or time > current + MAX_FORWARD_GAP:
            self._seek(time)
        target = time + self._frame_duration / 2  # tolerance for rounding of the timestamps
        while True:
            frame = self._pending if self._pending is not None else next(self._frames, None)
            self._pending = None
            if frame is None:  # end of the file: keep showing the last picture
                return self._current
            if frame.time is None:
                continue
            if self._time(frame) > target:
                self._pending = frame
                return self._current if self._current is not None else frame
            self._current = frame
