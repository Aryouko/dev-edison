"""Small dialogs: project name (new project, rename) and clip volume (menu "Volume", S4)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSlider, QVBoxLayout, QWidget


class _Dialog(QDialog):
    """Dialog with a title, a content and "Annuler" / confirmation buttons."""

    def __init__(self, parent: QWidget, title: str, confirm_text: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(380)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(24, 22, 24, 20)
        self._layout.setSpacing(14)
        heading = QLabel(title)
        heading.setObjectName("DialogTitle")
        self._layout.addWidget(heading)
        self.content = QVBoxLayout()
        self.content.setSpacing(10)
        self._layout.addLayout(self.content)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Annuler")
        cancel.clicked.connect(self.reject)
        self.confirm_button = QPushButton(confirm_text)
        self.confirm_button.setObjectName("Primary")
        self.confirm_button.setDefault(True)
        self.confirm_button.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(self.confirm_button)
        self._layout.addSpacing(6)
        self._layout.addLayout(buttons)


class NameDialog(_Dialog):
    """Ask for a project name."""

    def __init__(self, parent, title: str, confirm_text: str, name: str = ""):
        super().__init__(parent, title, confirm_text)
        label = QLabel("Nom du projet")
        label.setObjectName("Muted")
        self.edit = QLineEdit(name)
        self.edit.setPlaceholderText("Mon super montage")
        self.edit.selectAll()
        self.edit.textChanged.connect(lambda text: self.confirm_button.setEnabled(bool(text.strip())))
        self.confirm_button.setEnabled(bool(name.strip()))
        self.content.addWidget(label)
        self.content.addWidget(self.edit)

    @classmethod
    def ask(cls, parent, title: str, confirm_text: str, name: str = "") -> str | None:
        """Show the dialog and return the name, or None if cancelled."""
        dialog = cls(parent, title, confirm_text, name)
        return dialog.edit.text().strip() if dialog.exec() == QDialog.DialogCode.Accepted else None


class VolumeDialog(_Dialog):
    """Choose the volume of audio clips (0 to 200 %)."""

    def __init__(self, parent, volume: float):
        super().__init__(parent, "Volume", "Appliquer")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 200)
        self.slider.setValue(round(volume * 100))
        value = QLabel()
        value.setMinimumWidth(48)
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.slider.valueChanged.connect(lambda v: value.setText(f"{v} %"))
        value.setText(f"{self.slider.value()} %")
        row = QHBoxLayout()
        row.addWidget(self.slider)
        row.addWidget(value)
        hint = QLabel("100 % correspond au volume d'origine.")
        hint.setObjectName("Muted")
        self.content.addLayout(row)
        self.content.addWidget(hint)

    @classmethod
    def ask(cls, parent, volume: float) -> float | None:
        """Show the dialog and return the volume (1.0 = 100 %), or None if cancelled."""
        dialog = cls(parent, volume)
        return dialog.slider.value() / 100 if dialog.exec() == QDialog.DialogCode.Accepted else None
