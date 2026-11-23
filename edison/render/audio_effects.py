"""Cache of the sound of clips with audio effects.

A reverberation or an echo depends on what came before, so it cannot be
computed block by block in the audio callback. The whole sound of the clip
is processed once, in a background thread, and kept here.
"""

import json
import threading
from collections import OrderedDict

import numpy as np

from edison.config import SAMPLE_RATE
from edison.effects import AUDIO, get_effect
from edison.media.audio import AudioStore
from edison.model.project import Clip, Project


def audio_effects(clip: Clip) -> list:
    """Return ``[(plugin, values)]`` for the known audio effects of a clip."""
    result = []
    for effect in clip.effects:
        plugin = get_effect(effect.type)
        if plugin is not None and plugin.kind == AUDIO:
            result.append((plugin, plugin.values(effect.params)))
    return result


class AudioEffectCache:
    """Processed sound of the clips having audio effects.

    Parameters
    ----------
    store : AudioStore
        Decoded audio of the media.
    """

    MAX_ENTRIES = 24

    def __init__(self, store: AudioStore):
        self._store = store
        self._results: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def _key(clip: Clip) -> tuple:
        effects = tuple((e.type, json.dumps(e.params, sort_keys=True)) for e in clip.effects)
        return clip.media_id, round(clip.in_point, 4), round(clip.duration, 4), effects

    def get(self, clip: Clip, compute: bool = False) -> np.ndarray | None:
        """Return the processed sound of a clip.

        Parameters
        ----------
        clip : Clip
            Audio clip with effects.
        compute : bool
            Compute it now if it is not ready (never in the audio callback: too slow).

        Returns
        -------
        numpy.ndarray or None
            Samples of the whole clip, or None if not computed yet.
        """
        key = self._key(clip)
        with self._lock:
            if key in self._results:
                self._results.move_to_end(key)
                return self._results[key]
        if not compute:
            return None
        result = self._compute(clip)
        if result is not None:
            with self._lock:
                self._results[key] = result
                while len(self._results) > self.MAX_ENTRIES:
                    self._results.popitem(last=False)
        return result

    def prepare(self, project: Project) -> None:
        """Compute the sound of every clip with audio effects (blocking)."""
        for _, clip in project.iter_clips():
            if audio_effects(clip):
                self.get(clip, compute=True)

    def clear(self) -> None:
        """Forget every result (when the project is closed)."""
        with self._lock:
            self._results.clear()

    def _compute(self, clip: Clip) -> np.ndarray | None:
        source = self._store.get(clip.media_id)
        if source is None:
            return None
        start = int(round(clip.in_point * SAMPLE_RATE))
        count = int(round(clip.duration * SAMPLE_RATE))
        samples = np.array(source[start:start + count], dtype=np.float32)
        for plugin, values in audio_effects(clip):
            samples = plugin.process(samples, values, SAMPLE_RATE)
        return np.clip(samples, -1.0, 1.0).astype(np.float32)
