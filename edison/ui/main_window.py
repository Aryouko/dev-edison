"""Main window: header with the "Fichier" menu, home page and editing page.

Navigation: home page --("+" card, name asked)--> editing page --(logo)--> home page.
The actions of the "Fichier" menu (CDC "Barre de menu en haut de la fenêtre") are all
present; the ones calling a ``todo(...)`` of the controller are still to be developed.
"""

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (QFileDialog, QGridLayout, QHBoxLayout, QLabel, QMainWindow, QMenu, QMenuBar,
                               QMessageBox, QStackedWidget, QToolButton, QWidget)

from edison.config import APP_NAME, ASSETS_DIR, PROJECT_EXTENSION, projects_dir
from edison.controller.player import Player
from edison.controller.project_controller import ProjectController
from edison.controller.recent import recent_projects
from edison.ui.dialogs import NameDialog
from edison.ui.editor_page import EditorPage
from edison.ui.home_page import HomePage
from edison.ui.preview import FullscreenOverlay

PROJECT_FILTER = f"Projets Edison (*{PROJECT_EXTENSION})"


class HeaderBar(QWidget):
    """Top bar: logo and project name (left), "Fichier" menu (centre), save status (right)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HeaderBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.logo = QToolButton()
        self.logo.setIcon(QIcon(str(ASSETS_DIR / "logo.png")))
        self.logo.setIconSize(QSize(30, 30))
        self.logo.setToolTip("Retour à l'accueil")
        self.logo.setCursor(Qt.CursorShape.PointingHandCursor)
        title = QLabel("EDISON")
        title.setObjectName("AppTitle")
        self.project_label = QLabel()
        self.project_label.setObjectName("ProjectLabel")
        self.menu_bar = QMenuBar()
        self.menu_bar.setNativeMenuBar(False)
        self.status_label = QLabel()
        self.status_label.setObjectName("Muted")
        left = QHBoxLayout()
        left.setSpacing(8)
        left.addWidget(self.logo)
        left.addWidget(title)
        left.addWidget(self.project_label)
        left.addStretch()
        # Three columns: the side columns share the free space equally, so the menu stays centred.
        layout = QGridLayout(self)
        layout.setContentsMargins(12, 6, 18, 6)
        layout.addLayout(left, 0, 0)
        layout.addWidget(self.menu_bar, 0, 1, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label, 0, 2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(2, 1)


class _Toast(QLabel):
    """Short message shown at the bottom of the window for a few seconds (``controller.message``)."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setWordWrap(True)
        self.setMaximumWidth(520)
        self._timer = QTimer(self, singleShot=True, interval=3500)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def show_message(self, text: str) -> None:
        self.setText(text)
        self.adjustSize()
        parent = self.parentWidget()
        self.move((parent.width() - self.width()) // 2, parent.height() - self.height() - 28)
        self.show()
        self.raise_()
        self._timer.start()


class MainWindow(QMainWindow):
    """Application window: creates the controller, the player and the two pages."""

    def __init__(self):
        super().__init__()
        self.controller = ProjectController(self)
        self.player = Player(self.controller, self)
        self.setWindowIcon(QIcon(str(ASSETS_DIR / "logo.png")))
        self.resize(1440, 880)
        self.setMinimumSize(1100, 700)

        self.header = HeaderBar()
        self.header.logo.clicked.connect(self.show_home)
        self.setMenuWidget(self.header)
        self._create_file_menu()

        self.home = HomePage()
        self.home.new_project_requested.connect(self.new_project)
        self.home.open_project_requested.connect(self.open_project)
        self.home.browse_requested.connect(self.open_project)
        self.home.delete_project_requested.connect(
            lambda _path, _name: self.controller.todo("Supprimer un projet", "S6"))
        self.editor = EditorPage(self.controller, self.player)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.home)
        self.stack.addWidget(self.editor)
        self.setCentralWidget(self.stack)

        self.fullscreen = FullscreenOverlay(self.player, self)
        self.editor.preview.fullscreen_requested.connect(self.fullscreen.open)
        self._toast = _Toast(self)
        self.controller.message.connect(self._toast.show_message)
        self.controller.dirty_changed.connect(self._update_header)
        self.controller.project_renamed.connect(self._update_header)
        self.controller.project_opened.connect(self._update_header)
        self._show_page(self.home)

    # ================================================================== menu
    def _create_file_menu(self) -> None:
        menu = self.header.menu_bar.addMenu("Fichier")
        self.rename_action = self._action(menu, "Renommer le projet…", "Ctrl+R", self.rename_project)
        menu.addSeparator()
        self._action(menu, "Nouveau projet…", QKeySequence.StandardKey.New, self.new_project)
        self._action(menu, "Ouvrir un projet…", QKeySequence.StandardKey.Open, self.open_project)
        self.recent_menu = QMenu("Projets récents", menu)
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        menu.addMenu(self.recent_menu)
        menu.addSeparator()
        self.save_action = self._action(menu, "Enregistrer", QKeySequence.StandardKey.Save, self.controller.save)
        self.save_as_action = self._action(menu, "Enregistrer sous…", "Ctrl+Shift+S", self.save_project_as)
        menu.addSeparator()
        self._action(menu, "Quitter", "Ctrl+Q", self.close)

    def _action(self, menu: QMenu, text: str, shortcut, slot) -> QAction:
        action = QAction(text, self)
        action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(lambda _checked=False: slot())
        menu.addAction(action)
        self.addAction(action)  # the shortcut works even when the menu is closed
        return action

    def _fill_recent_menu(self) -> None:
        self.recent_menu.clear()
        paths = recent_projects()  # TODO(S6) in controller/recent.py
        for path in paths:
            self.recent_menu.addAction(path, lambda p=path: self.open_project(p))
        if not paths:
            self.recent_menu.addAction("Aucun projet récent").setEnabled(False)

    # ================================================================= pages
    def _show_page(self, page: QWidget) -> None:
        self.stack.setCurrentWidget(page)
        in_editor = page is self.editor
        for action in (self.rename_action, self.save_action, self.save_as_action):
            action.setEnabled(in_editor)
        if not in_editor:
            self.home.refresh()
        self._update_header()

    def show_home(self) -> None:
        """Logo of the header: close the project (after confirmation) and go back to the home page."""
        if self.stack.currentWidget() is self.editor and self._confirm_discard():
            self.controller.close_project()
            self._show_page(self.home)

    def _update_header(self) -> None:
        """Project name in the header and in the window title, save status on the right."""
        project = self.controller.project
        if project is None or self.stack.currentWidget() is not self.editor:
            self.header.project_label.setText("")
            self.header.status_label.setText("")
            self.setWindowTitle(APP_NAME)
            return
        self.header.project_label.setText(f"/  {project.name}")
        dirty = self.controller.is_dirty
        # TODO(S6): show "Enregistré à HH:MM" after a save (time of the last save).
        self.header.status_label.setText("Modifications non enregistrées" if dirty else "")
        self.setWindowTitle(f"{project.name}{' *' if dirty else ''} — {APP_NAME}")

    # ========================================================= project files
    def _confirm_discard(self) -> bool:
        """Ask what to do with unsaved changes. Returns False if the user cancels."""
        if not self.controller.is_dirty:
            return True
        buttons = QMessageBox.StandardButton
        answer = QMessageBox.question(
            self, "Modifications non enregistrées",
            f"Voulez-vous enregistrer les modifications de « {self.controller.project.name} » ?",
            buttons.Save | buttons.Discard | buttons.Cancel, buttons.Save)
        if answer == buttons.Save:
            self.controller.save()
            return not self.controller.is_dirty  # False while saving is not implemented
        return answer == buttons.Discard

    def new_project(self) -> None:
        """Home page "+" card or "Nouveau projet": ask for a name, then open the editing page."""
        if not self._confirm_discard():
            return
        name = NameDialog.ask(self, "Nouveau projet", "Créer")
        if name:
            self.controller.create_project(name)
            self._show_page(self.editor)

    def open_project(self, path: str | None = None) -> None:
        """Open a project file (asks for it if ``path`` is not given)."""
        if not self._confirm_discard():
            return
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Ouvrir un projet", str(projects_dir()), PROJECT_FILTER)
            if not path:
                return
        self.controller.open_project(path)  # TODO(S6): catch ProjectFileError -> QMessageBox.critical
        if self.controller.project is not None:
            self._show_page(self.editor)

    def save_project_as(self) -> None:
        """"Enregistrer sous": choose a file, then save."""
        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer sous", str(projects_dir()), PROJECT_FILTER)
        if path:
            self.controller.save(path)

    def rename_project(self) -> None:
        """"Renommer le projet" (Ctrl+R)."""
        name = NameDialog.ask(self, "Renommer le projet", "Renommer", self.controller.project.name)
        if name:
            self.controller.rename(name)

    def closeEvent(self, event) -> None:
        """"Quitter" or the window cross: confirmation if there are unsaved changes."""
        if self.stack.currentWidget() is self.editor and not self._confirm_discard():
            event.ignore()
            return
        self.player.shutdown()
        self.controller.close_project()
        event.accept()
