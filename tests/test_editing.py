"""Timeline editing operations."""

import pytest

from edison.model import editing
from edison.model.editing import EditError
from edison.model.project import AUDIO, VIDEO, Project, load_project, save_project


def test_video_with_sound_creates_linked_clips(project, video_media):
    clips = editing.add_media(project, video_media, 0.0)
    assert [project.find_clip(c.id)[0].kind for c in clips] == [VIDEO, AUDIO]
    assert clips[0].link_id is not None and clips[0].link_id == clips[1].link_id


def test_audio_goes_to_a_free_track_when_the_first_one_is_busy(project, video_media, audio_media):
    editing.add_media(project, video_media, 0.0)
    editing.add_media(project, audio_media, 0.5)
    assert len(project.tracks_of(AUDIO)) == 2


def test_drop_on_an_occupied_track_is_refused(project, video_media):
    editing.add_media(project, video_media, 0.0)
    with pytest.raises(EditError):
        editing.add_media(project, video_media, 1.0, project.tracks_of(VIDEO)[0].id)


def test_cut_then_merge_restores_the_clip(project, video_media):
    video, audio = editing.add_media(project, video_media, 0.0)
    assert editing.cut_clips(project, {video.id, audio.id}, 0.8) == 2
    track = project.tracks_of(VIDEO)[0]
    left, right = track.clips
    assert (left.duration, right.start, right.in_point) == pytest.approx((0.8, 0.8, 0.8))
    assert editing.can_merge(left, right)
    editing.merge_clips(project, track.id, left.id, right.id)
    assert [len(t.clips) for t in project.tracks_of(VIDEO) + project.tracks_of(AUDIO)] == [1, 1]
    assert project.tracks_of(VIDEO)[0].clips[0].duration == pytest.approx(video_media.duration)


def test_merge_of_non_consecutive_parts_is_refused(project, audio_media):
    editing.add_media(project, audio_media, 0.0)
    editing.add_media(project, audio_media, audio_media.duration)
    track = project.tracks_of(AUDIO)[0]
    with pytest.raises(EditError):  # same media, but the second clip starts again at 0 s
        editing.merge_clips(project, track.id, track.clips[0].id, track.clips[1].id)


def test_move_refuses_overlaps_and_moves_linked_clips(project, video_media):
    first = editing.add_media(project, video_media, 0.0)
    second = editing.add_media(project, video_media, 5.0)
    ids = {c.id for c in second}
    assert not editing.can_move(project, ids, -4.0)
    editing.move_clips(project, ids, -3.0)
    assert [c.start for c in second] == pytest.approx([2.0, 2.0])
    assert first[0].start == 0.0


def test_trim_is_limited_by_the_media_and_the_neighbours(project, video_media):
    video, audio = editing.add_media(project, video_media, 0.0)
    assert editing.trim_clip(project, video.id, "end", 10.0) == pytest.approx(0.0)  # media is only 2 s long
    editing.trim_clip(project, video.id, "start", 0.5)
    assert (video.start, video.in_point, video.duration) == pytest.approx((0.5, 0.5, 1.5))
    assert (audio.start, audio.duration) == pytest.approx((0.5, 1.5))


def test_duplicate_places_copies_after_the_group(project, video_media):
    clips = editing.add_media(project, video_media, 0.0)
    copies = editing.duplicate_clips(project, {c.id for c in clips})
    starts = [project.find_clip(copy_id)[1].start for copy_id in copies]
    assert starts == pytest.approx([2.0, 2.0])


def test_unlink_separates_audio_and_video(project, video_media):
    video, audio = editing.add_media(project, video_media, 0.0)
    editing.unlink_clips(project, video.id)
    assert video.link_id is None and audio.link_id is None
    assert editing.expand_links(project, {video.id}) == {video.id}


def test_project_file_round_trip(tmp_path, project, video_media):
    editing.add_media(project, video_media, 1.0)
    path = tmp_path / "test.edison"
    save_project(project, path)
    loaded = load_project(path)
    assert loaded.to_dict() == project.to_dict()
    assert isinstance(loaded, Project)
