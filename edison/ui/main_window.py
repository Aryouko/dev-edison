"""Main window: header with the "Fichier" menu, home page and editing page."""

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (QFileDialog, QGridLayout, QHBoxLayout, QLabel, QMainWindow, QMenu, QMenuBar, QMessageBox,
                               QStackedWidget, QToolButton, QWidget)

from edison.config import APP_NAME, ASSETS_DIR, PROJECT_EXTENSION, projects_dir
from edison.controller.player import Player
from edison.controller.project_controller import ProjectController
from edison.controller.recent import delete_project, recent_projects
from edison.model.project import ProjectFileError
from edison.ui.dialogs import NameDialog
from edison.ui.editor_page import EditorPage
from edison.ui.home_page import HomePage
from edison.ui.preview import FullscreenOverlay

PROJECT_FILTER = f"Projets Edison (*{PROJECT_EXTENSION})"


class HeaderBar(QWidget):
    """Top bar: logo and project name, "Fichier" menu, save status."""

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
        # Three columns: the two side columns share the free space equally,
        # so the menu stays in the middle of the bar (as on the mock-up).
        layout = QGridLayout(self)
        layout.setContentsMargins(12, 6, 18, 6)
        layout.addLayout(left, 0, 0)
        layout.addWidget(self.menu_bar, 0, 1, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label, 0, 2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(2, 1)


class MainWindow(QMainWindow):
    """Application window."""

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
        self.home.delete_project_requested.connect(self.delete_project)
        self.home.browse_requested.connect(self.open_project)
        self.editor = EditorPage(self.controller, self.player)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.home)
        self.stack.addWidget(self.editor)
        self.setCentralWidget(self.stack)
        self.fullscreen = FullscreenOverlay(self.player, self)
        self.editor.preview.fullscreen_requested.connect(self.fullscreen.open)

        self.controller.dirty_changed.connect(self._update_header)
        self.controller.project_renamed.connect(self._update_header)
        self.controller.project_opened.connect(self._update_header)
        self.controller.missing_media.connect(self._warn_missing_media)
        self._show_page(self.home)

    # ================================================================= menu
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
        self.save_action = self._action(menu, "Enregistrer", QKeySequence.StandardKey.Save, self.save_project)
        self.save_as_action = self._action(menu, "Enregistrer sous…", "Ctrl+Shift+S", self.save_project_as)
        menu.addSeparator()
        self.delete_action = self._action(menu, "Supprimer le projet…", None, self.delete_current_project)
        menu.addSeparator()
        self._action(menu, "Quitter", "Ctrl+Q", self.close)

    def _action(self, menu: QMenu, text: str, shortcut, slot) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        menu.addAction(action)
        self.addAction(action)  # shortcut active even when the menu is closed
        return action

    def _fill_recent_menu(self) -> None:
        self.recent_menu.clear()
        paths = recent_projects()
        for path in paths:
            self.recent_menu.addAction(Path(path).stem, lambda p=path: self.open_project(p)).setToolTip(path)
        if not paths:
            self.recent_menu.addAction("Aucun projet récent").setEnabled(False)

    # ================================================================ pages
    def _show_page(self, page: QWidget) -> None:
        self.stack.setCurrentWidget(page)
        in_editor = page is self.editor
        for action in (self.rename_action, self.save_action, self.save_as_action, self.delete_action):
            action.setEnabled(in_editor)
        if not in_editor:
            self.home.refresh()
        self._update_header()

    def show_home(self) -> None:
        """Close the project (after confirmation) and go back to the home page."""
        if self.stack.currentWidget() is self.editor and self._confirm_discard():
            self.controller.close_project()
            self._show_page(self.home)

    def _update_header(self) -> None:
        project = self.controller.project
        if project is None or self.stack.currentWidget() is not self.editor:
            self.header.project_label.setText("")
            self.header.status_label.setText("")
            self.setWindowTitle(APP_NAME)
            return
        file_name = self.controller.path.name if self.controller.path else ""
        self.header.project_label.setText(f"/  {project.name}   ·   {file_name}")
        if self.controller.is_dirty:
            self.header.status_label.setText("Modifications non enregistrées")
        elif self.controller.last_saved:
            self.header.status_label.setText(f"Enregistré à {self.controller.last_saved:%H:%M}")
        self.setWindowTitle(f"{project.name}{' *' if self.controller.is_dirty else ''} — {APP_NAME}")

    # ======================================================= project files
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
            return self.save_project()
        return answer == buttons.Discard

    def new_project(self) -> None:
        """Ask for a name and create a project."""
        if not self._confirm_discard():
            return
        name = NameDialog.ask(self, "Nouveau projet", "Créer")
        if not name:
            return
        try:
            self.controller.create_project(name)
        except OSError as error:
            QMessageBox.critical(self, "Création impossible", f"Le projet n'a pas pu être créé :\n{error}")
            return
        self._show_page(self.editor)

    def open_project(self, path: str | None = None) -> None:
        """Open a project file (asks for it if ``path`` is not given)."""
        if not self._confirm_discard():
            return
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Ouvrir un projet", str(projects_dir()), PROJECT_FILTER)
            if not path:
                return
        try:
            self.controller.open_project(path)
        except ProjectFileError as error:
            QMessageBox.critical(self, "Ouverture impossible", str(error))
            return
        self._show_page(self.editor)

    def save_project(self) -> bool:
        """Save the project. Returns True on success."""
        try:
            self.controller.save()
        except OSError as error:
            QMessageBox.critical(self, "Enregistrement impossible", f"Le projet n'a pas pu être enregistré :\n{error}")
            return False
        return True

    def save_project_as(self) -> bool:
        """Save the project to a new file."""
        start = str(self.controller.path or projects_dir() / f"{self.controller.project.name}{PROJECT_EXTENSION}")
        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer sous", start, PROJECT_FILTER)
        if not path:
            return False
        path = str(Path(path).with_suffix(PROJECT_EXTENSION))
        try:
            self.controller.save(path)
        except OSError as error:
            QMessageBox.critical(self, "Enregistrement impossible", f"Le projet n'a pas pu être enregistré :\n{error}")
            return False
        self._update_header()
        return True

    def rename_project(self) -> None:
        """Rename the project."""
        name = NameDialog.ask(self, "Renommer le projet", "Renommer", self.controller.project.name)
        if name:
            self.controller.rename(name)

    def _confirm_delete(self, name: str) -> bool:
        answer = QMessageBox.question(
            self, "Supprimer le projet",
            f"Supprimer le projet « {name} » ?\n\nLe fichier sera placé dans la corbeille. "
            "Les vidéos et les sons importés ne sont pas supprimés.")
        return answer == QMessageBox.StandardButton.Yes

    def _move_to_trash(self, path: str) -> None:
        try:
            delete_project(path)
        except OSError as error:
            QMessageBox.critical(self, "Suppression impossible", str(error))

    def delete_project(self, path: str, name: str) -> None:
        """Delete a project of the home page (after confirmation)."""
        if self._confirm_delete(name):
            self._move_to_trash(path)
            self.home.refresh()

    def delete_current_project(self) -> None:
        """"Fichier > Supprimer le projet": delete the open project and go back to the home page."""
        path, name = str(self.controller.path), self.controller.project.name
        if self._confirm_delete(name):
            self.controller.close_project()
            self._move_to_trash(path)
            self._show_page(self.home)

    def _warn_missing_media(self, names: list) -> None:
        lines = "\n".join(f"• {name}" for name in names)
        QMessageBox.warning(self, "Médias introuvables",
                            f"Ces fichiers ont été déplacés ou supprimés :\n\n{lines}\n\n"
                            "Leurs clips restent dans la trame mais apparaissent en rouge.")

    def closeEvent(self, event) -> None:
        if self.stack.currentWidget() is self.editor and not self._confirm_discard():
            event.ignore()
            return
        self.editor.export_panel.cancel_and_wait()
        self.player.shutdown()
        self.controller.close_project()  # while every view still exists to receive the signals
        event.accept()
