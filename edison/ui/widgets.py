"""Standard widgets that ignore the mouse wheel.

In a scrollable panel, a combo box or a slider under the mouse would catch the
wheel and change its value instead of scrolling the panel. These versions pass
the wheel to their parent, so the panel scrolls.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QSlider


class ComboBox(QComboBox):
    """Combo box whose value is only changed by clicking."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        event.ignore()


class Slider(QSlider):
    """Slider whose value is only changed by dragging or with the keyboard."""

    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        event.ignore()
