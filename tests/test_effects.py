"""Effect plugins, effect editing and rendering with effects."""

import numpy as np
import pytest

from edison.config import SAMPLE_RATE
from edison.effects import AUDIO, VIDEO, effects_of, get_effect
from edison.effects.audio import FADE
from edison.model import editing
from edison.model.editing import EditError
from edison.model.project import EFFECT, load_project, save_project
from edison.render.audio_effects import AudioEffectCache
from edison.render.renderer import MediaSources, mix_audio, render_frame


@pytest.fixture
def picture():
    rng = np.random.default_rng(0)
    return rng.integers(0, 255, (90, 160, 3), dtype=np.uint8)


@pytest.mark.parametrize("effect", effects_of(VIDEO), ids=lambda e: e.type_id)
def test_every_video_effect_keeps_the_picture_format(effect, picture):
    result = effect.apply(picture.copy(), 0.4, effect.defaults(), 3.0)
    assert result.shape == picture.shape
    assert result.dtype == np.uint8


@pytest.mark.parametrize("effect", effects_of(AUDIO), ids=lambda e: e.type_id)
def test_every_audio_effect_keeps_the_length(effect):
    time = np.arange(SAMPLE_RATE) / SAMPLE_RATE
    tone = np.stack([np.sin(2 * np.pi * 440 * time)] * 2, axis=1).astype(np.float32) * 0.5
    result = effect.process(tone, effect.defaults(), SAMPLE_RATE)
    assert result.shape == tone.shape
    assert np.abs(result).max() <= 1.0


def test_values_are_completed_and_clamped():
    blur = get_effect("blur")
    assert blur.values({}) == {"strength": 40}
    assert blur.values({"strength": 500}) == {"strength": 100}


def test_negative_and_black_and_white(picture):
    assert np.array_equal(get_effect("negative").apply(picture, 0, {}, 1), 255 - picture)
    gray = get_effect("black_and_white").apply(picture, 0, {"strength": 100}, 1).astype(int)
    assert np.abs(gray[..., 0] - gray[..., 1]).max() <= 1


def test_boing_zooms_in_and_out_over_time(picture):
    boing = get_effect("boing")
    values = boing.values({"amplitude": 30, "frequency": 1.0})
    low = boing.apply(picture, 0.75, values, 2.0)  # bottom of the bounce: no zoom
    high = boing.apply(picture, 0.25, values, 2.0)  # top of the bounce: zoomed in
    assert np.array_equal(low, picture)
    assert not np.array_equal(high, picture)


def test_pitch_shift_raises_the_frequency():
    time = np.arange(SAMPLE_RATE) / SAMPLE_RATE
    tone = np.stack([np.sin(2 * np.pi * 440 * time)] * 2, axis=1).astype(np.float32) * 0.5
    shifted = get_effect("pitch").process(tone, {"semitones": 12}, SAMPLE_RATE)
    middle = shifted[SAMPLE_RATE // 4: 3 * SAMPLE_RATE // 4, 0]
    spectrum = np.abs(np.fft.rfft(middle))
    peak = np.argmax(spectrum) * SAMPLE_RATE / len(middle)
    assert peak == pytest.approx(880, rel=0.03)  # one octave higher


def test_effect_on_a_clip_is_rendered_saved_and_copied_on_cut(tmp_path, project, video_media):
    video, _audio = editing.add_media(project, video_media, 0.0)
    editing.add_effect(project, {video.id}, "negative", {})
    sources = MediaSources()
    try:
        plain_project = type(project).from_dict(project.to_dict())
        plain_project.tracks_of("video")[0].clips[0].effects.clear()
        plain = render_frame(plain_project, 0.5, 160, 90, sources)
        inverted = render_frame(project, 0.5, 160, 90, sources)
    finally:
        sources.close()
    assert np.abs(inverted.astype(int) - (255 - plain.astype(int))).max() <= 2
    editing.cut_clips(project, {video.id}, 1.0)
    left, right = project.tracks_of("video")[0].clips
    assert right.effects[0].type == "negative" and right.effects[0] is not left.effects[0]
    path = tmp_path / "effects.edison"
    save_project(project, path)
    assert load_project(path).to_dict() == project.to_dict()


def test_effect_block_goes_on_an_effect_track_and_can_be_extended(project):
    block = editing.add_effect_block(project, 2.0, "blur", {"strength": 50})
    assert project.find_clip(block.id)[0].kind == EFFECT
    editing.trim_clip(project, block.id, "end", 10.0)  # no source media: only neighbours limit it
    assert block.duration == pytest.approx(13.0)
    editing.remove_effect(project, block.id, block.effects[0].id)
    assert project.find_clip(block.id) is None


def test_fade_is_stored_on_the_clip(project, audio_media):
    (clip,) = editing.add_media(project, audio_media, 0.0)
    editing.add_effect(project, {clip.id}, FADE, {"fade_in": 0.3, "fade_out": 0.2})
    assert (clip.fade_in, clip.fade_out, clip.effects) == (0.3, 0.2, [])


def test_update_of_a_removed_effect_fails(project, audio_media):
    (clip,) = editing.add_media(project, audio_media, 0.0)
    with pytest.raises(EditError):
        editing.update_effect(project, clip.id, "missing", {})


def test_audio_effect_is_heard_in_the_mix(project, audio_media, audio_store):
    (clip,) = editing.add_media(project, audio_media, 0.0)
    cache = AudioEffectCache(audio_store)
    dry = mix_audio(project, 0, SAMPLE_RATE // 2, audio_store, cache, compute=True)
    editing.add_effect(project, {clip.id}, "pitch", {"semitones": -12})
    assert mix_audio(project, 0, 100, audio_store, cache) is not None  # not computed yet: played dry
    wet = mix_audio(project, 0, SAMPLE_RATE // 2, audio_store, cache, compute=True)
    assert not np.allclose(dry, wet, atol=1e-3)
