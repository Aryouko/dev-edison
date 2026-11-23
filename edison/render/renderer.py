"""Picture and sound of the timeline at a given time.

:func:`render_frame` and :func:`mix_audio` are used both by the preview and by
the export, which guarantees that what is seen is what is exported.
"""

import logging
import os

import numpy as np

from edison.config import CHANNELS, PREVIEW_MAX_HEIGHT, PREVIEW_MAX_WIDTH, SAMPLE_RATE
from edison.media.audio import AudioStore
from edison.media.video_decoder import VideoDecoder
from edison.effects import get_effect
from edison.model.project import AUDIO, EFFECT, VIDEO, Clip, Media, Project
from edison.render.audio_effects import AudioEffectCache, audio_effects
from edison.utils import fit_size

logger = logging.getLogger(__name__)


class MediaSources:
    """Video decoders opened by one thread (a decoder cannot be shared)."""

    def __init__(self):
        self._decoders: dict[str, VideoDecoder | None] = {}

    def decoder(self, media: Media) -> VideoDecoder | None:
        """Return the decoder of a media, opened on first use (None if the file is unreadable)."""
        if media.id not in self._decoders:
            decoder = None
            if os.path.exists(media.path):
                try:
                    decoder = VideoDecoder(media.path)
                except Exception:  # an unreadable file must not stop the rendering
                    logger.exception("Cannot open %s", media.path)
            self._decoders[media.id] = decoder
        return self._decoders[media.id]

    def close(self) -> None:
        """Close every decoder."""
        for decoder in self._decoders.values():
            if decoder is not None:
                decoder.close()
        self._decoders.clear()


def preview_size(project: Project) -> tuple[int, int]:
    """Size of the preview pictures (project aspect ratio, reduced for speed)."""
    return fit_size(project.width, project.height, PREVIEW_MAX_WIDTH, PREVIEW_MAX_HEIGHT)


def render_frame(project: Project, time: float, width: int, height: int, sources: MediaSources) -> np.ndarray:
    """Render the picture of the timeline at ``time``.

    The top-most video track having a clip at ``time`` is displayed, fitted in
    the output with black bars if the aspect ratios differ. The effects of that
    clip are applied, then the effect blocks of the effect tracks.

    Parameters
    ----------
    project : Project
        Rendered project.
    time : float
        Timeline position, in seconds.
    width, height : int
        Output size.
    sources : MediaSources
        Decoders of the calling thread.

    Returns
    -------
    numpy.ndarray
        RGB picture of shape ``(height, width, 3)``.
    """
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    for track in project.tracks_of(VIDEO):
        clip = track.clip_at(time)
        media = project.get_media(clip.media_id) if clip else None
        decoder = sources.decoder(media) if media else None
        if decoder is None:
            continue
        fitted_width, fitted_height = fit_size(media.width, media.height, width, height)
        picture = decoder.frame_at(clip.in_point + time - clip.start, fitted_width, fitted_height)
        if picture is None:
            continue
        top, left = (height - fitted_height) // 2, (width - fitted_width) // 2
        frame[top:top + fitted_height, left:left + fitted_width] = picture
        frame = apply_video_effects(frame, clip, time)
        break
    for track in project.tracks_of(EFFECT):
        block = track.clip_at(time)
        if block is not None:
            frame = apply_video_effects(frame, block, time)
    return frame


def apply_video_effects(frame: np.ndarray, clip: Clip, time: float) -> np.ndarray:
    """Apply the video effects of a clip, in order (unknown effects are ignored)."""
    for effect in clip.effects:
        plugin = get_effect(effect.type)
        if plugin is None or plugin.kind != VIDEO:
            continue
        try:
            frame = plugin.apply(frame, time - clip.start, plugin.values(effect.params), clip.duration)
        except Exception:  # a failing effect must not stop the playback or the export
            logger.exception("Effect %s failed", effect.type)
    return np.ascontiguousarray(frame, dtype=np.uint8)


def mix_audio(project: Project, start: int, count: int, store: AudioStore,
              effects: AudioEffectCache | None = None, compute: bool = False) -> np.ndarray:
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
    effects : AudioEffectCache, optional
        Processed sound of the clips with audio effects.
    compute : bool
        Compute the processed sound when missing (export). During playback, a clip
        whose processing is not finished yet is played without its effects.

    Returns
    -------
    numpy.ndarray
        Float samples in ``[-1, 1]``, shape ``(count, CHANNELS)``.
    """
    output = np.zeros((count, CHANNELS), dtype=np.float32)
    stop = start + count
    for track in project.tracks_of(AUDIO):
        for clip in track.clips:
            clip_start = int(round(clip.start * SAMPLE_RATE))
            clip_stop = clip_start + int(round(clip.duration * SAMPLE_RATE))
            first, last = max(start, clip_start), min(stop, clip_stop)
            samples = store.get(clip.media_id) if first < last else None
            if samples is None:
                continue
            source_first = int(round(clip.in_point * SAMPLE_RATE)) + first - clip_start
            processed = effects.get(clip, compute) if effects is not None and audio_effects(clip) else None
            if processed is not None:  # the processed sound starts at the beginning of the clip
                samples, source_first = processed, first - clip_start
            chunk = np.asarray(samples[source_first:source_first + last - first])
            if len(chunk) == 0:
                continue
            gain = gain_envelope(clip, (np.arange(len(chunk)) + first - clip_start) / SAMPLE_RATE)
            output[first - start:first - start + len(chunk)] += chunk * gain[:, None]
    np.clip(output, -1.0, 1.0, out=output)
    return output


def gain_envelope(clip: Clip, positions: np.ndarray) -> np.ndarray:
    """Volume envelope of a clip (volume and fades) at positions inside the clip."""
    gain = np.full(len(positions), clip.volume, dtype=np.float32)
    if clip.fade_in > 0:
        gain *= np.clip(positions / clip.fade_in, 0.0, 1.0)
    if clip.fade_out > 0:
        gain *= np.clip((clip.duration - positions) / clip.fade_out, 0.0, 1.0)
    return gain
