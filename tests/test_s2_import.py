"""Sprint S2 — "Import fonctionnel"."""

import pytest

from edison.controller.project_controller import ProjectController
from edison.media.probe import UnsupportedMediaError, probe_media, video_thumbnail
from tests.conftest import SAMPLE_AUDIO, SAMPLE_VIDEO


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


def test_wrong_extension_is_refused(tmp_path):
    text = tmp_path / "notes.txt"
    text.write_text("hello")
    with pytest.raises(UnsupportedMediaError):
        probe_media(str(text))


def test_video_thumbnail_is_a_small_rgb_picture():
    picture = video_thumbnail(probe_media(str(SAMPLE_VIDEO)), max_width=160)
    assert picture is not None
    assert picture.shape == (90, 160, 3)


def test_audio_has_no_thumbnail():
    assert video_thumbnail(probe_media(str(SAMPLE_AUDIO))) is None


@pytest.fixture
def controller(qapp):
    controller = ProjectController()
    controller.create_project("Import")
    return controller


def test_import_files_adds_the_media_in_the_background(qtbot, controller):
    with qtbot.waitSignal(controller.message, timeout=5000,
                          check_params_cb=lambda text: "importé" in text):
        controller.import_files([str(SAMPLE_VIDEO), str(SAMPLE_AUDIO)])
    kinds = sorted(media.kind for media in controller.project.media)
    assert kinds == ["audio", "video"]
    video = next(m for m in controller.project.media if m.kind == "video")
    assert controller.previews[video.id] is not None
    assert not controller.is_importing


def test_import_errors_are_reported_together(qtbot, controller, tmp_path):
    broken = tmp_path / "broken.mp4"
    broken.write_text("not a video")
    text = tmp_path / "notes.txt"
    text.write_text("hello")
    with qtbot.waitSignal(controller.import_errors, timeout=5000) as blocker:
        controller.import_files([str(SAMPLE_AUDIO), str(broken), str(text)])
    names = sorted(name for name, _reason in blocker.args[0])
    assert names == ["broken.mp4", "notes.txt"]
    assert [m.kind for m in controller.project.media] == ["audio"]
