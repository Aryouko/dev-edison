"""Editing page: Import/Export tabs, render area and timeline."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QSplitter, QStackedWidget,
                               QVBoxLayout, QWidget)

from edison.ui.export_panel import ExportPanel
from edison.ui.import_panel import ImportPanel
from edison.ui.preview import PreviewPanel
from edison.ui.timeline import TimelinePanel


class _Toast(QLabel):
    """Short message shown at the bottom of the page for a few seconds."""

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


class _SidePanel(QFrame):
    """Top left area with the "Import" and "Export" tabs."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.import_panel = ImportPanel(controller)
        self.export_panel = ExportPanel(controller)
        stack = QStackedWidget()
        stack.addWidget(self.import_panel)
        stack.addWidget(self.export_panel)
        tab_bar = QFrame()
        tab_bar.setObjectName("TabBar")
        tabs = QHBoxLayout(tab_bar)
        tabs.setContentsMargins(4, 4, 4, 4)
        tabs.setSpacing(4)
        group = QButtonGroup(self)
        for index, name in enumerate(("Import", "Export")):
            button = QPushButton(name)
            button.setObjectName("Tab")
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            group.addButton(button, index)
            tabs.addWidget(button)
        group.idClicked.connect(stack.setCurrentIndex)
        top = QHBoxLayout()
        top.addWidget(tab_bar)
        top.addStretch()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(10)
        layout.addLayout(top)
        layout.addWidget(stack, 1)


class EditorPage(QWidget):
    """Editing page."""

    def __init__(self, controller, player, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self._player = player
        self.side_panel = _SidePanel(controller)
        self.side_panel.setMinimumWidth(300)
        preview_frame = QFrame()
        preview_frame.setObjectName("Panel")
        self.preview = PreviewPanel(controller, player)
        frame_layout = QVBoxLayout(preview_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.addWidget(self.preview)

        top = QSplitter(Qt.Orientation.Horizontal)
        top.addWidget(self.side_panel)
        top.addWidget(preview_frame)
        top.setStretchFactor(1, 1)
        top.setSizes([380, 900])
        top.setChildrenCollapsible(False)

        timeline_frame = QFrame()
        timeline_frame.setObjectName("Panel")
        self.timeline_panel = TimelinePanel(controller, player)
        timeline_layout = QVBoxLayout(timeline_frame)
        timeline_layout.setContentsMargins(0, 0, 0, 0)
        timeline_layout.addWidget(self.timeline_panel)

        main = QSplitter(Qt.Orientation.Vertical)
        main.addWidget(top)
        main.addWidget(timeline_frame)
        main.setStretchFactor(0, 3)
        main.setStretchFactor(1, 2)
        main.setSizes([520, 380])
        main.setChildrenCollapsible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(main)

        self._toast = _Toast(self)
        controller.message.connect(self._toast.show_message)
        self._add_shortcut(Qt.Key.Key_Space, player.toggle)
        self._add_shortcut(Qt.Key.Key_Left, lambda: player.step_frame(-1))
        self._add_shortcut(Qt.Key.Key_Right, lambda: player.step_frame(1))

    def _add_shortcut(self, key, slot) -> None:
        action = QAction(self)
        action.setShortcut(QKeySequence(key))
        action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        action.triggered.connect(slot)
        self.addAction(action)

    @property
    def export_panel(self) -> "ExportPanel":
        return self.side_panel.export_panel

    @property
    def import_panel(self) -> "ImportPanel":
        return self.side_panel.import_panel
