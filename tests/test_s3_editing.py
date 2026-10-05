"""Sprint S3 — timeline editing operations (``edison/model/editing.py``).

Remove the ``pytestmark`` line when the operations are implemented, then add a test
for each new operation (they run without any window: fast and simple).
"""

import pytest

from edison.model import editing
from edison.model.editing import EditError
from edison.model.project import AUDIO, VIDEO, Media

pytestmark = pytest.mark.skip(reason="TODO(S3): editing operations")


@pytest.fixture
def video():
    """A 4 s video with sound, already in the library."""
    return Media("v1", "C:/video.mp4", VIDEO, 4.0, has_audio=True, width=1920, height=1080, fps=30)


@pytest.fixture
def placed(project, video):
    project.media.append(video)
    return editing.add_media(project, video, 0.0)


def test_video_with_sound_creates_two_linked_clips(project, placed):
    video_clip, audio_clip = placed
    assert project.find_clip(video_clip.id)[0].kind == VIDEO
    assert project.find_clip(audio_clip.id)[0].kind == AUDIO
    assert video_clip.link_id is not None and video_clip.link_id == audio_clip.link_id


def test_occupied_place_is_refused(project, video, placed):
    with pytest.raises(EditError):
        editing.add_media(project, video, 1.0, project.tracks_of(VIDEO)[0].id)


def test_cut_then_merge(project, placed):
    editing.cut_clips(project, {clip.id for clip in placed}, 1.5)
    track = project.tracks_of(VIDEO)[0]
    left, right = track.clips
    assert (left.duration, right.start, right.in_point) == pytest.approx((1.5, 1.5, 1.5))
    editing.merge_clips(project, track.id, left.id, right.id)
    assert len(track.clips) == 1 and track.clips[0].duration == pytest.approx(4.0)


def test_trim_cannot_go_beyond_the_media(project, placed):
    video_clip = placed[0]
    editing.trim_clip(project, video_clip.id, "end", 10.0)
    assert video_clip.duration == pytest.approx(4.0)
