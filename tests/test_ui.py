"""Interface tests with pytest-qt."""

from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from edison.ui import import_panel, theme
from edison.ui.main_window import MainWindow

ASSETS = Path(__file__).parent / "assets"


@pytest.fixture
def window(qtbot, qapp, tmp_path):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    qapp.setStyleSheet(theme.stylesheet())
    main_window = MainWindow()
    yield main_window
    main_window.controller.close_project()  # otherwise closing asks to save the changes
    main_window.close()


def test_create_import_and_undo(qtbot, window):
    controller = window.controller
    controller.create_project("Essai")
    window._show_page(window.editor)
    assert Path(controller.path).exists()

    controller.import_files([str(ASSETS / "sample.mp4"), str(ASSETS / "tone.wav")])
    qtbot.waitUntil(lambda: len(controller.project.media) == 2 and controller.pending_imports == 0, timeout=10000)

    video = next(m for m in controller.project.media if m.kind == "video")
    controller.add_media_clip(video.id, 0.0)
    assert controller.project.duration == pytest.approx(video.duration)
    assert controller.is_dirty

    controller.undo_stack.undo()
    assert controller.project.duration == 0
    controller.undo_stack.redo()
    assert controller.project.duration == pytest.approx(video.duration)


def test_refused_format_is_reported(qtbot, window, tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr(import_panel.QMessageBox, "warning", lambda *args: shown.append(args[2]))
    window.controller.create_project("Formats")
    fake = tmp_path / "document.pdf"
    fake.write_text("x")
    window.controller.import_files([str(fake)])
    assert "document.pdf" in shown[0]
    assert "mp4" in shown[0]  # the message lists the accepted formats
