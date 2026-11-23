"""Integration tests: import, render_frame, audio mix and export."""

import numpy as np
import pytest

from edison.config import SAMPLE_RATE
from edison.media.probe import UnsupportedMediaError, probe_media
from edison.model import editing
from edison.render.exporter import ExportError, ExportSettings, export_project
from edison.render.renderer import MediaSources, mix_audio, render_frame


def test_probe_reads_the_video_properties(video_media):
    assert video_media.kind == "video"
    assert (video_media.width, video_media.height) == (320, 180)
    assert video_media.duration == pytest.approx(2.0, abs=0.1)
    assert video_media.has_audio


def test_unsupported_file_is_refused(tmp_path):
    fake = tmp_path / "notes.txt"
    fake.write_text("not a media")
    with pytest.raises(UnsupportedMediaError):
        probe_media(str(fake))


def test_render_frame_shows_the_top_clip(project, video_media):
    editing.add_media(project, video_media, 1.0)
    sources = MediaSources()
    try:
        empty = render_frame(project, 0.5, 160, 90, sources)
        frame = render_frame(project, 1.5, 160, 90, sources)
    finally:
        sources.close()
    assert frame.shape == (90, 160, 3)
    assert empty.max() == 0
    assert frame.mean() > 20


def test_mix_applies_volume(project, video_media, audio_store):
    video, audio = editing.add_media(project, video_media, 0.0)
    loud = mix_audio(project, 0, SAMPLE_RATE // 2, audio_store)
    editing.set_volume(project, {audio.id}, 0.5)
    quiet = mix_audio(project, 0, SAMPLE_RATE // 2, audio_store)
    assert np.abs(loud).max() > 0.1
    assert np.abs(quiet).max() == pytest.approx(np.abs(loud).max() / 2, rel=0.05)


def test_export_of_a_short_montage_is_readable(tmp_path, project, video_media, audio_media, audio_store):
    clips = editing.add_media(project, video_media, 0.0)
    editing.cut_clips(project, {c.id for c in clips}, 1.0)
    editing.add_media(project, audio_media, 0.5)
    output = tmp_path / "montage.mp4"
    progress = []
    export_project(project, ExportSettings(str(output), width=320, height=180, fps=24), audio_store,
                   on_progress=lambda fraction, _remaining: progress.append(fraction))
    exported = probe_media(str(output))
    assert exported.duration == pytest.approx(2.0, abs=0.1)
    assert exported.has_audio
    assert progress[-1] == pytest.approx(1.0)


def test_export_of_an_empty_timeline_fails(tmp_path, project, audio_store):
    with pytest.raises(ExportError):
        export_project(project, ExportSettings(str(tmp_path / "empty.mp4")), audio_store)
