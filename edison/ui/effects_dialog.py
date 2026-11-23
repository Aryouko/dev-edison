"""Effects pop-up: list of effects, generated settings and live preview."""

import copy

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QDialog, QFormLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from edison.config import ASSETS_DIR
from edison.effects import VIDEO, Param, effects_of, get_effect
from edison.ui import icons
from edison.ui.widgets import ComboBox, Slider

PREVIEW_DELAY_MS = 40  # groups the changes made while a slider is dragged


class _ParamEditor(QWidget):
    """Control generated from a :class:`Param` declaration: a slider or a list of choices."""

    changed = Signal()

    def __init__(self, param: Param, value, parent=None):
        super().__init__(parent)
        self._param = param
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if param.choices:
            self._combo = ComboBox()
            for choice, label in param.choices:
                self._combo.addItem(label, choice)
            self._combo.setCurrentIndex(max(0, self._combo.findData(value)))
            self._combo.currentIndexChanged.connect(self.changed)
            layout.addWidget(self._combo)
            return
        self._decimals = 0 if param.step >= 1 else len(f"{param.step:g}".split(".")[1])
        self._slider = Slider()
        self._slider.setRange(0, round((param.maximum - param.minimum) / param.step))
        self._slider.setValue(round((float(value) - param.minimum) / param.step))
        self._label = QLabel()
        self._label.setMinimumWidth(64)
        self._label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._slider.valueChanged.connect(self._on_slider)
        layout.addWidget(self._slider, 1)
        layout.addWidget(self._label)
        self._on_slider()

    def value(self):
        """Current value of the parameter."""
        if self._param.choices:
            return self._combo.currentData()
        value = self._param.minimum + self._slider.value() * self._param.step
        return round(value, self._decimals)

    def _on_slider(self) -> None:
        text = f"{self.value():.{self._decimals}f}".replace(".", ",")
        self._label.setText(f"{text}{self._param.suffix}")
        self.changed.emit()


class EffectsDialog(QDialog):
    """Choose an effect and its settings; the render area shows the result while choosing.

    Parameters
    ----------
    parent : QWidget
        Parent window.
    player : Player
        Player showing the preview.
    project : Project
        Current project (never modified by the dialog).
    kind : str
        ``VIDEO`` or ``AUDIO``: effects offered.
    subject : str
        What the effect will apply to (shown under the title).
    preview : callable
        ``preview(project_copy, effect_type, values)`` applies the effect to a copy of the project.
    commit : callable
        ``commit(effect_type, values)`` applies the effect for real (undoable).
    effect_type : str, optional
        Effect selected when the dialog opens.
    values : dict, optional
        Initial settings of ``effect_type``.
    edit_mode : bool
        Change the settings of an applied effect: the list of effects is hidden.
    """

    def __init__(self, parent, player, project, kind, subject, preview, commit,
                 effect_type=None, values=None, edit_mode=False):
        super().__init__(parent)
        self._player = player
        self._project = project
        self._preview_function = preview
        self._commit = commit
        self._initial_values = dict(values or {})
        self._initial_type = effect_type
        self._editors: dict[str, _ParamEditor] = {}
        self._was_playing = player.playing
        self._preview_timer = QTimer(self, singleShot=True, interval=PREVIEW_DELAY_MS)
        self._preview_timer.timeout.connect(self._update_preview)
        self.setWindowTitle("Effets")
        self.setMinimumSize(580, 470)

        title = QLabel(("Effets vidéo" if kind == VIDEO else "Effets audio") if not edit_mode else "Modifier l'effet")
        title.setObjectName("DialogTitle")
        subtitle = QLabel(subject)
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)

        self._list = QListWidget()
        self._list.setObjectName("EffectList")
        self._list.setFixedWidth(200)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setIconSize(QSize(16, 16))
        for effect in effects_of(kind):
            item = QListWidgetItem(icons.icon("sparkles", size=16), effect.label)
            item.setData(Qt.ItemDataRole.UserRole, effect.type_id)
            self._list.addItem(item)
        self._list.currentItemChanged.connect(self._on_effect_selected)
        self._list.setVisible(not edit_mode)

        placeholder = QWidget()
        placeholder_layout = QVBoxLayout(placeholder)
        mascot = QLabel()
        mascot.setPixmap(QPixmap(str(ASSETS_DIR / "mascot_laptop.png")).scaledToHeight(
            90, Qt.TransformationMode.SmoothTransformation))
        mascot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = QLabel("Choisissez un effet dans la liste :\nl'aperçu s'affiche dans la zone de rendu.")
        hint.setObjectName("Muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder_layout.addStretch()
        placeholder_layout.addWidget(mascot)
        placeholder_layout.addWidget(hint)
        placeholder_layout.addStretch()

        self._settings = QWidget()
        self._settings_layout = QVBoxLayout(self._settings)
        self._settings_layout.setContentsMargins(8, 0, 0, 0)
        self._effect_name = QLabel()
        self._effect_name.setObjectName("SectionTitle")
        self._description = QLabel()
        self._description.setObjectName("Muted")
        self._description.setWordWrap(True)
        self._form = QFormLayout()
        self._form.setSpacing(12)
        self._settings_layout.addWidget(self._effect_name)
        self._settings_layout.addWidget(self._description)
        self._settings_layout.addSpacing(8)
        self._settings_layout.addLayout(self._form)
        self._settings_layout.addStretch()

        self._pages = QStackedWidget()
        self._pages.addWidget(placeholder)
        self._pages.addWidget(self._settings)
        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(self._list)
        body.addWidget(self._pages, 1)

        self._play_button = QPushButton()
        self._play_button.clicked.connect(player.toggle)
        player.playing_changed.connect(self._update_play_button)
        self._update_play_button(player.playing)
        self._close_button = QPushButton("Fermer")
        self._close_button.clicked.connect(self.reject)
        self._cancel_button = QPushButton("Annuler")
        self._cancel_button.clicked.connect(self.reject)
        self._apply_button = QPushButton("Appliquer")
        self._apply_button.setObjectName("Primary")
        self._apply_button.clicked.connect(self._apply)
        footer = QHBoxLayout()
        footer.addWidget(self._play_button)
        footer.addStretch()
        for button in (self._close_button, self._cancel_button, self._apply_button):
            footer.addWidget(button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(body, 1)
        layout.addLayout(footer)
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, player.toggle)

        self._show_buttons(selected=False)
        if effect_type is not None:
            match = [self._list.item(i) for i in range(self._list.count())
                     if self._list.item(i).data(Qt.ItemDataRole.UserRole) == effect_type]
            if match:
                self._list.setCurrentItem(match[0])
            else:  # edit mode: the effect is not in the list
                self._show_effect(effect_type)

    # ---------------------------------------------------------------- effect
    def _on_effect_selected(self, item, _previous=None) -> None:
        if item is not None:
            self._show_effect(item.data(Qt.ItemDataRole.UserRole))

    def _show_effect(self, effect_type: str) -> None:
        effect = get_effect(effect_type)
        self._effect_type = effect_type
        self._effect_name.setText(effect.label)
        self._description.setText(effect.description)
        while self._form.rowCount():
            self._form.removeRow(0)
        self._editors = {}
        values = effect.values(self._initial_values if effect_type == self._initial_type else {})
        for param in effect.params:
            editor = _ParamEditor(param, values[param.name])
            editor.changed.connect(self._preview_timer.start)
            self._form.addRow(param.label, editor)
            self._editors[param.name] = editor
        if not effect.params:
            note = QLabel("Cet effet n'a pas de réglage.")
            note.setObjectName("Muted")
            self._form.addRow(note)
        self._pages.setCurrentIndex(1)
        self._show_buttons(selected=True)
        self._update_preview()

    def _values(self) -> dict:
        return {name: editor.value() for name, editor in self._editors.items()}

    def _show_buttons(self, selected: bool) -> None:
        self._close_button.setVisible(not selected)
        self._cancel_button.setVisible(selected)
        self._apply_button.setVisible(selected)

    def _update_preview(self) -> None:
        preview = copy.deepcopy(self._project)
        self._preview_function(preview, self._effect_type, self._values())
        self._player.set_preview(preview)

    def _update_play_button(self, playing: bool) -> None:
        self._play_button.setIcon(icons.icon("pause" if playing else "play", size=16))
        self._play_button.setText("Pause" if playing else "Lire l'aperçu")

    # --------------------------------------------------------------- closing
    def _apply(self) -> None:
        self._close_preview()
        self._commit(self._effect_type, self._values())
        self.accept()

    def reject(self) -> None:
        self._close_preview()
        super().reject()

    def _close_preview(self) -> None:
        self._preview_timer.stop()
        if self._player.playing and not self._was_playing:
            self._player.pause()
        self._player.set_preview(None)
        self._player.playing_changed.disconnect(self._update_play_button)

    @classmethod
    def run(cls, parent, *args, **kwargs) -> None:
        """Open the dialog over the Import/Export area, so that the render area stays visible."""
        dialog = cls(parent, *args, **kwargs)
        dialog.adjustSize()
        dialog.move(parent.window().mapToGlobal(QPoint(24, 90)))
        dialog.exec()
