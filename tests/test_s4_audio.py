"""Sprint S4 — audio decoding at import (``AudioStore``).

Remove the ``pytestmark`` line when ``AudioStore`` is implemented.
"""

import numpy as np
import pytest

from edison.config import CHANNELS, SAMPLE_RATE, cache_dir
from edison.controller.project_controller import ProjectController
from edison.media.audio import AudioStore
from edison.media.probe import probe_media
from edison.model.project import Media, new_id
from tests.conftest import SAMPLE_AUDIO, SAMPLE_VIDEO

pytestmark = pytest.mark.skip(reason="TODO(S4): AudioStore")


def test_load_decodes_an_audio_file():
    store = AudioStore()
    media = probe_media(str(SAMPLE_AUDIO))
    assert store.get(media.id) is None
    samples = store.load(media)
    assert samples.shape[1] == CHANNELS
    assert samples.shape[0] == pytest.approx(SAMPLE_RATE * 1.0, rel=0.02)
    assert np.abs(samples).max() > 0.01  # a tone, not silence
    assert store.get(media.id) is samples


def test_load_decodes_the_sound_of_a_video():
    media = probe_media(str(SAMPLE_VIDEO))
    samples = AudioStore().load(media)
    assert samples.shape[0] == pytest.approx(SAMPLE_RATE * 2.0, rel=0.02)


def test_the_decoded_sound_is_reused_from_the_cache():
    first = AudioStore().load(probe_media(str(SAMPLE_AUDIO)))
    files = list(cache_dir().glob("audio_*.f32"))
    second = AudioStore().load(probe_media(str(SAMPLE_AUDIO)))  # new import of the same file
    assert list(cache_dir().glob("audio_*.f32")) == files
    assert np.array_equal(first, second)


def test_clear_forgets_every_media():
    store = AudioStore()
    media = probe_media(str(SAMPLE_AUDIO))
    store.load(media)
    store.clear()
    assert store.get(media.id) is None


def test_undecodable_sound_is_refused(tmp_path):
    broken = tmp_path / "broken.wav"
    broken.write_text("not a sound")
    with pytest.raises(Exception):  # replace by your own error class
        AudioStore().load(Media(id=new_id(), path=str(broken), kind="audio", duration=1.0, has_audio=True))
    assert not list(cache_dir().glob("*.part"))


def test_import_stores_the_sound(qtbot, qapp):
    controller = ProjectController()
    controller.create_project("Audio")
    with qtbot.waitSignal(controller.message, timeout=10000,
                          check_params_cb=lambda text: "importé" in text):
        controller.import_files([str(SAMPLE_VIDEO), str(SAMPLE_AUDIO)])
    ids = [media.id for media in controller.project.media]
    assert len(ids) == 2
    assert all(controller.audio_store.get(media_id) is not None for media_id in ids)
    controller.close_project()
    assert all(controller.audio_store.get(media_id) is None for media_id in ids)
