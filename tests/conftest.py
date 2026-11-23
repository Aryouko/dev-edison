"""Shared test fixtures."""

import os
from pathlib import Path

import pytest

from edison.media.audio import AudioStore
from edison.media.probe import probe_media
from edison.model.project import Project

ASSETS = Path(__file__).parent / "assets"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # no window during the tests


@pytest.fixture(autouse=True)
def isolated_folders(tmp_path, monkeypatch):
    """Keep caches and projects of the tests out of the user folders."""
    monkeypatch.setenv("EDISON_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("EDISON_PROJECTS_DIR", str(tmp_path / "projects"))


@pytest.fixture
def video_media():
    """2 s video (320 x 180, 25 fps) with a 440 Hz sound."""
    return probe_media(str(ASSETS / "sample.mp4"))


@pytest.fixture
def audio_media():
    """1 s audio file (660 Hz)."""
    return probe_media(str(ASSETS / "tone.wav"))


@pytest.fixture
def project(video_media, audio_media):
    """Empty project whose library contains the two test media."""
    project = Project.create("Test")
    project.media.extend([video_media, audio_media])
    return project


@pytest.fixture
def audio_store(video_media, audio_media):
    """Decoded audio of the two test media."""
    store = AudioStore()
    store.load(video_media)
    store.load(audio_media)
    return store
