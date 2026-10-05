"""Frame accurate video decoding with PyAV (sprints S3-S4)."""

import numpy as np


class VideoDecoder:
    """Return the picture of a video file at any time.

    A decoder keeps the file open; it must only be used by ONE thread
    (the preview thread and the export thread each open their own decoders).

    Parameters
    ----------
    path : str
        Video file.

    TODO(S3) — principle:
        * ``self._container = av.open(path)``, ``self._stream = self._container.streams.video[0]``,
          ``self._stream.thread_type = "AUTO"`` (multi-threaded decoding);
        * reading forward (playback): decode the next frames with ``self._container.decode(stream)``;
        * jumping backward or far ahead (seeking with the cursor): ``container.seek(...)`` goes
          to the previous key frame, then decode forward until the requested time;
        * keep the last converted pictures in a small cache (``collections.OrderedDict``):
          the CDC asks for a frame cache.
    """

    def __init__(self, path: str):
        self.path = path
        # TODO(S3): open the file with PyAV.

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
            Hint: ``frame.to_ndarray(format="rgb24", width=width, height=height)``.
        """
        raise NotImplementedError("TODO(S3): VideoDecoder.frame_at")

    def close(self) -> None:
        """Release the file."""
        # TODO(S3): self._container.close()
