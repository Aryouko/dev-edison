"""Sprint S5 — effects. Every registered effect is tested automatically.

The two first tests already run on the example effect ``Negative``; they will check
every new effect too. Remove the ``skip`` of the last test when ``add_effect`` and the
effects in ``render_frame`` are implemented.
"""

import numpy as np
import pytest

from edison.config import SAMPLE_RATE
from edison.effects import AUDIO, VIDEO, effects_of
from edison.model import editing
from edison.model.project import Clip


@pytest.fixture
def picture():
    return np.random.default_rng(0).integers(0, 255, (90, 160, 3), dtype=np.uint8)


@pytest.mark.parametrize("effect", effects_of(VIDEO), ids=lambda e: e.type_id)
def test_every_video_effect_keeps_the_picture_format(effect, picture):
    result = effect.apply(picture.copy(), 0.4, effect.defaults(), 3.0)
    assert result.shape == picture.shape and result.dtype == np.uint8


@pytest.mark.parametrize("effect", effects_of(AUDIO), ids=lambda e: e.type_id)
def test_every_audio_effect_keeps_the_length(effect):
    time = np.arange(SAMPLE_RATE) / SAMPLE_RATE
    tone = np.stack([np.sin(2 * np.pi * 440 * time)] * 2, axis=1).astype(np.float32) * 0.5
    result = effect.process(tone, effect.defaults(), SAMPLE_RATE)
    assert result.shape == tone.shape and np.abs(result).max() <= 1.0


@pytest.mark.skip(reason="TODO(S5): editing.add_effect")
def test_add_effect_to_a_clip(project):
    clip = Clip("c1", "m1", 0.0, 0.0, 2.0)
    project.tracks[0].clips.append(clip)
    editing.add_effect(project, {clip.id}, "negative", {})
    assert [effect.type for effect in clip.effects] == ["negative"]
