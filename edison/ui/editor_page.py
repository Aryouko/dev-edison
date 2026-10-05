"""Editing page (CDC "Page edition"), laid out as on the mock-up:

    +---------------------------+-------------------------------+
    | Import / Export tabs      | Render area                   |
    | (side panel)              | (preview + playback controls) |
    +---------------------------+-------------------------------+
    | Timeline (toolbar + tracks)                               |
    +-----------------------------------------------------------+

The three areas are separated by splitters: the user can resize them.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QPushButton, QSplitter, QStackedWidget,
                               QVBoxLayout, QWidget)

from edison.ui.export_panel import ExportPanel
from edison.ui.import_panel import ImportPanel
from edison.ui.preview import PreviewPanel
from edison.ui.timeline import TimelinePanel


def _panel(widget: QWidget) -> QFrame:
    """Put a widget in a rounded dark frame (style ``QFrame#Panel`` of the theme)."""
    frame = QFrame()
    frame.setObjectName("Panel")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(widget)
    return frame


class _SidePanel(QFrame):
    """Top left area with the "Import" and "Export" tabs (CDC: only these two tabs)."""

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
    """Editing page: side panel, render area and timeline."""

    def __init__(self, controller, player, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.side_panel = _SidePanel(controller)
        self.side_panel.setMinimumWidth(300)
        self.preview = PreviewPanel(controller, player)
        self.timeline_panel = TimelinePanel(controller, player)

        top = QSplitter(Qt.Orientation.Horizontal)
        top.addWidget(self.side_panel)
        top.addWidget(_panel(self.preview))
        top.setStretchFactor(1, 1)
        top.setSizes([380, 900])
        top.setChildrenCollapsible(False)

        main = QSplitter(Qt.Orientation.Vertical)
        main.addWidget(top)
        main.addWidget(_panel(self.timeline_panel))
        main.setStretchFactor(0, 3)
        main.setStretchFactor(1, 2)
        main.setSizes([520, 380])
        main.setChildrenCollapsible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(main)

        # Keyboard shortcuts of the page (inactive while typing in a text field)
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
    def import_panel(self) -> ImportPanel:
        return self.side_panel.import_panel

    @property
    def export_panel(self) -> ExportPanel:
        return self.side_panel.export_panel
