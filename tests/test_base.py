"""Tests of what the base already provides (they must always pass)."""

import pytest

from edison.effects import VIDEO, effects_of, get_effect
from edison.effects.base import Param
from edison.model import editing
from edison.model.project import AUDIO, EFFECT, Clip
from edison.utils import fit_size, format_time


def test_new_project_has_one_track_of_each_kind(project):
    assert [track.kind for track in project.tracks] == [VIDEO, AUDIO, EFFECT]
    assert project.duration == 0


def test_clip_position(project):
    clip = Clip("c1", "m1", start=2.0, in_point=0.0, duration=3.0)
    project.tracks[0].clips.append(clip)
    assert clip.end == 5.0
    assert project.tracks[0].clip_at(4.9) is clip
    assert project.tracks[0].clip_at(5.0) is None
    assert project.duration == 5.0
    assert editing.overlaps(project.tracks[0], 4.0, 6.0)
    assert not editing.overlaps(project.tracks[0], 5.0, 6.0)


def test_helpers():
    assert format_time(83.5) == "01:23.50"
    assert format_time(3700, precise=False) == "1:01:40"
    assert fit_size(1920, 1080, 960, 720) == (960, 540)


def test_effect_registry():
    negative = get_effect("negative")
    assert negative in effects_of(VIDEO)
    assert get_effect("does-not-exist") is None


def test_param_clamp():
    param = Param("strength", "Intensité", 40, 0, 100)
    assert param.clamp(150) == 100
    assert param.clamp("abc") == 40
    assert Param("color", "Couleur", "gold", choices=(("gold", "Or"),)).clamp("red") == "gold"


@pytest.mark.parametrize("module", ["edison.media.probe", "edison.render.exporter", "edison.ui.main_window"])
def test_modules_import(module):
    __import__(module)
