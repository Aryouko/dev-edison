"""Picture and sound of the timeline at a given time (sprint S4).

CDC "Une seule fonction de rendu": :func:`render_frame` and :func:`mix_audio` are
used by the preview (player) AND by the export. Never write a second rendering
code elsewhere: this is what guarantees that what is seen is what is exported.
"""

import numpy as np

from edison.config import CHANNELS, PREVIEW_MAX_HEIGHT, PREVIEW_MAX_WIDTH
from edison.media.audio import AudioStore
from edison.media.video_decoder import VideoDecoder
from edison.model.project import Media, Project
from edison.utils import fit_size


class MediaSources:
    """Video decoders opened by ONE thread (a decoder cannot be shared between threads)."""

    def __init__(self):
        self._decoders: dict[str, VideoDecoder] = {}

    def decoder(self, media: Media) -> VideoDecoder | None:
        """Return the decoder of a media, opened on first use.

        TODO(S4): return None if the file is missing or unreadable (the clip is then black).
        """
        if media.id not in self._decoders:
            self._decoders[media.id] = VideoDecoder(media.path)
        return self._decoders[media.id]

    def close(self) -> None:
        """Close every decoder (end of the thread)."""
        for decoder in self._decoders.values():
            decoder.close()
        self._decoders.clear()


def preview_size(project: Project) -> tuple[int, int]:
    """Size of the preview pictures: aspect ratio of the project, reduced for speed."""
    return fit_size(project.width, project.height, PREVIEW_MAX_WIDTH, PREVIEW_MAX_HEIGHT)


def render_frame(project: Project, time: float, width: int, height: int, sources: MediaSources) -> np.ndarray:
    """Render the picture of the timeline at ``time``.

    Parameters
    ----------
    project : Project
        Rendered project.
    time : float
        Timeline position, in seconds.
    width, height : int
        Output size (small for the preview, real size for the export).
    sources : MediaSources
        Decoders of the calling thread.

    Returns
    -------
    numpy.ndarray
        RGB picture ``(height, width, 3)``, uint8.

    TODO(S4) "Fonction render_frame":
        1. the top-most video track having a clip at ``time`` gives the picture:
           ``sources.decoder(media).frame_at(clip.in_point + time - clip.start, w, h)``;
        2. fit it in the output with black bars (``fit_size``) if the aspect ratios differ;
    TODO(S5):
        3. apply the effects of that clip (``get_effect(e.type).apply(...)``);
        4. apply the effect blocks of the effect tracks active at ``time``.
    """
    return np.zeros((height, width, 3), dtype=np.uint8)


def mix_audio(project: Project, start: int, count: int, store: AudioStore) -> np.ndarray:
    """Mix the audio tracks between two sample positions.

    Parameters
    ----------
    project : Project
        Rendered project.
    start : int
        First sample (timeline position x ``SAMPLE_RATE``).
    count : int
        Number of samples.
    store : AudioStore
        Decoded audio of the media.

    Returns
    -------
    numpy.ndarray
        Float samples in ``[-1, 1]``, shape ``(count, CHANNELS)``.

    TODO(S4) "Lecture audio": for each audio clip overlapping ``[start, start + count[``,
    add its samples (``store.get(clip.media_id)``, starting at ``clip.in_point``) multiplied
    by its volume and its fade envelope; finish with ``np.clip(output, -1, 1)``.
    """
    return np.zeros((count, CHANNELS), dtype=np.float32)
