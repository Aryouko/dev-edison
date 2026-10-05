"""Shared test fixtures (pytest loads this file automatically)."""

import os
from pathlib import Path

import pytest

from edison.model.project import Project

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # no window opens during the tests

ASSETS = Path(__file__).parent / "assets"
SAMPLE_VIDEO = ASSETS / "sample.mp4"  # 2 s, 320 x 180, 25 fps, 440 Hz sound
SAMPLE_AUDIO = ASSETS / "tone.wav"  # 1 s, 660 Hz


@pytest.fixture(autouse=True)
def isolated_folders(tmp_path, monkeypatch):
    """Keep the caches and the projects of the tests out of the user folders."""
    monkeypatch.setenv("EDISON_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("EDISON_PROJECTS_DIR", str(tmp_path / "projects"))


@pytest.fixture
def project():
    """Empty project (one video, one audio and one effect track)."""
    return Project.create("Test")
