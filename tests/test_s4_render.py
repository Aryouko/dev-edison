"""Sprint S4 — ``render_frame`` and ``mix_audio`` (CDC "Tests d'intégration": render_frame sur un projet simple).

Remove the ``pytestmark`` line when the rendering is implemented.
"""

import numpy as np
import pytest

from edison.config import SAMPLE_RATE
from edison.media.audio import AudioStore
from edison.media.probe import probe_media
from edison.model import editing
from edison.render.renderer import MediaSources, mix_audio, render_frame
from tests.conftest import SAMPLE_VIDEO

pytestmark = pytest.mark.skip(reason="TODO(S4): render_frame / mix_audio")


def test_render_frame_shows_the_clip(project):
    media = probe_media(str(SAMPLE_VIDEO))
    project.media.append(media)
    editing.add_media(project, media, 1.0)
    sources = MediaSources()
    try:
        before = render_frame(project, 0.5, 160, 90, sources)  # nothing on the timeline yet
        during = render_frame(project, 1.5, 160, 90, sources)
    finally:
        sources.close()
    assert during.shape == (90, 160, 3)
    assert before.max() == 0
    assert during.mean() > 20


def test_mix_audio_plays_the_sound(project):
    media = probe_media(str(SAMPLE_VIDEO))
    project.media.append(media)
    store = AudioStore()
    store.load(media)
    editing.add_media(project, media, 0.0)
    block = mix_audio(project, 0, SAMPLE_RATE // 2, store)
    assert block.shape == (SAMPLE_RATE // 2, 2)
    assert np.abs(block).max() > 0.1
