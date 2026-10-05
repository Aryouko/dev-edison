"""Sprint S2 — "Import fonctionnel".

Remove the ``pytestmark`` line when ``probe_media`` is implemented.
"""

import pytest

from edison.media.probe import UnsupportedMediaError, probe_media
from tests.conftest import SAMPLE_AUDIO, SAMPLE_VIDEO

pytestmark = pytest.mark.skip(reason="TODO(S2): probe_media")


def test_probe_reads_the_video_properties():
    media = probe_media(str(SAMPLE_VIDEO))
    assert media.kind == "video"
    assert (media.width, media.height) == (320, 180)
    assert media.duration == pytest.approx(2.0, abs=0.1)
    assert media.has_audio


def test_probe_reads_an_audio_file():
    media = probe_media(str(SAMPLE_AUDIO))
    assert media.kind == "audio"
    assert media.duration == pytest.approx(1.0, abs=0.05)


def test_unreadable_file_is_refused(tmp_path):
    fake = tmp_path / "broken.mp4"
    fake.write_text("not a video")
    with pytest.raises(UnsupportedMediaError):
        probe_media(str(fake))
