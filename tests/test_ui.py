"""Interface tests with pytest-qt: the main interface opens and the navigation works."""

import pytest
from PySide6.QtCore import QSettings

from edison.ui import theme
from edison.ui.main_window import MainWindow


@pytest.fixture
def window(qtbot, qapp, tmp_path):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)  # settings of the tests in a temporary folder
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    qapp.setStyleSheet(theme.stylesheet())
    main_window = MainWindow()
    yield main_window
    main_window.controller.close_project()  # otherwise closing asks to save the changes
    main_window.close()


def test_application_starts_on_the_home_page(window):
    assert window.stack.currentWidget() is window.home


def test_new_project_opens_the_editing_page(window):
    window.controller.create_project("Essai")
    window._show_page(window.editor)
    assert window.stack.currentWidget() is window.editor
    assert window.header.project_label.text().endswith("Essai")


def test_features_not_developed_yet_show_a_message(qtbot, window):
    window.controller.create_project("Essai")
    with qtbot.waitSignal(window.controller.message, timeout=1000) as blocker:
        window.controller.cut(1.0)  # editing.cut_clips still raises NotImplementedError
    assert "À implémenter" in blocker.args[0]
