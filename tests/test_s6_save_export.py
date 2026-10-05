"""Sprint S6 — saving / loading ``.edison`` files and export (CDC "export d'un court montage lisible").

Remove the ``pytestmark`` line when these features are implemented.
"""

import pytest

from edison.media.audio import AudioStore
from edison.media.probe import probe_media
from edison.model import editing
from edison.model.project import load_project, save_project
from edison.render.exporter import ExportError, ExportSettings, export_project
from tests.conftest import SAMPLE_VIDEO

pytestmark = pytest.mark.skip(reason="TODO(S6): save / load / export")


def test_project_file_round_trip(tmp_path, project):
    media = probe_media(str(SAMPLE_VIDEO))
    project.media.append(media)
    editing.add_media(project, media, 1.0)
    path = tmp_path / "test.edison"
    save_project(project, path)
    assert load_project(path).to_dict() == project.to_dict()


def test_export_of_a_short_montage_is_readable(tmp_path, project):
    media = probe_media(str(SAMPLE_VIDEO))
    project.media.append(media)
    store = AudioStore()
    store.load(media)
    editing.add_media(project, media, 0.0)
    output = tmp_path / "montage.mp4"
    export_project(project, ExportSettings(str(output), width=320, height=180, fps=24), store)
    exported = probe_media(str(output))
    assert exported.duration == pytest.approx(2.0, abs=0.1)
    assert exported.has_audio


def test_export_of_an_empty_timeline_fails(tmp_path, project):
    with pytest.raises(ExportError):
        export_project(project, ExportSettings(str(tmp_path / "empty.mp4")), AudioStore())
