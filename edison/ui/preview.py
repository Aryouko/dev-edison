"""Render area: real-time picture of the montage and playback controls."""

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QToolButton, QVBoxLayout, QWidget, QWidgetAction

from edison.config import ASSETS_DIR
from edison.ui import icons, theme
from edison.ui.painting import fit_rect, rounded
from edison.ui.widgets import Slider
from edison.utils import format_time


class VideoView(QWidget):
    """Displays the last rendered picture, or the mascot when the timeline is empty."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image = QImage()
        self._empty = True
        self._mascot = QPixmap(str(ASSETS_DIR / "mascot_laptop.png"))
        self.setMinimumSize(320, 180)

    def set_image(self, image: QImage) -> None:
        self._image = image
        self.update()

    def set_empty(self, empty: bool) -> None:
        self._empty = empty
        self.update()

    def image_rect(self) -> QRectF:
        """Area where the picture is drawn."""
        if self._image.isNull():
            return QRectF(self.rect())
        return fit_rect(QRectF(self.rect()), self._image.width(), self._image.height())

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        if self._empty:
            painter.fillPath(rounded(QRectF(self.rect()), 12), QColor(theme.SURFACE_ALT))
            height = min(150.0, self.height() * 0.45)
            width = height * self._mascot.width() / max(1, self._mascot.height())
            center = QRectF(self.rect()).center()
            mascot = QRectF(center.x() - width / 2, center.y() - height / 2 - 18, width, height)
            painter.drawPixmap(mascot, self._mascot, QRectF(self._mascot.rect()))
            painter.setPen(QColor(theme.TEXT_MUTED))
            painter.drawText(QRectF(0, mascot.bottom() + 10, self.width(), 24), Qt.AlignmentFlag.AlignHCenter,
                             "Importez un média puis glissez-le sur la trame pour commencer")
            return
        target = self.image_rect()
        painter.setClipPath(rounded(target, 10))
        painter.fillRect(target, Qt.GlobalColor.black)
        if not self._image.isNull():
            painter.drawImage(target, self._image)


class ProgressSlider(QWidget):
    """Video progress bar: shows the position and lets the user drag it."""

    seek_requested = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0.0
        self._maximum = 0.0
        self._hovered = False
        self._dragging = False
        self.setMinimumWidth(80)
        self.setFixedHeight(22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

    def set_range(self, maximum: float) -> None:
        self._maximum = max(0.0, maximum)
        self.update()

    def set_value(self, value: float) -> None:
        self._value = value
        self.update()

    def _track(self) -> QRectF:
        return QRectF(7, self.height() / 2 - 2, self.width() - 14, 4)

    def _value_at(self, x: float) -> float:
        track = self._track()
        ratio = min(max((x - track.left()) / max(track.width(), 1), 0.0), 1.0)
        return ratio * self._maximum

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = self._track()
        painter.fillPath(rounded(track, 2), QColor(theme.SURFACE_HOVER))
        ratio = self._value / self._maximum if self._maximum > 0 else 0.0
        done = QRectF(track.left(), track.top(), track.width() * min(ratio, 1.0), track.height())
        painter.fillPath(rounded(done, 2), QColor(theme.ACCENT))
        if self.isEnabled():
            radius = 7 if (self._hovered or self._dragging) else 5
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(theme.ACCENT))
            painter.drawEllipse(QPointF(done.right(), track.center().y()), radius, radius)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._maximum > 0:
            self._dragging = True
            self.seek_requested.emit(self._value_at(event.position().x()))

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self.seek_requested.emit(self._value_at(event.position().x()))

    def mouseReleaseEvent(self, _event) -> None:
        self._dragging = False
        self.update()

    def enterEvent(self, _event) -> None:
        self._hovered = True
        self.update()

    def leaveEvent(self, _event) -> None:
        self._hovered = False
        self.update()


def _icon_button(name: str, tooltip: str, size: int = 20) -> QToolButton:
    button = QToolButton()
    button.setIcon(icons.icon(name, size=size))
    button.setIconSize(QSize(size, size))
    button.setToolTip(tooltip)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class _VolumeButton(QToolButton):
    """Volume button: a click opens a slider, the icon shows the mute state."""

    def __init__(self, player, parent=None):
        super().__init__(parent)
        self._player = player
        self.setToolTip("Volume de lecture")
        self.setIconSize(QSize(20, 20))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0; }")
        self._slider = Slider(Qt.Orientation.Vertical)
        self._slider.setRange(0, 100)
        self._slider.setValue(100)
        self._slider.setFixedHeight(120)
        self._slider.valueChanged.connect(lambda value: player.set_volume(value / 100))
        mute = QToolButton()
        mute.setText("Muet")
        mute.setCheckable(True)
        mute.toggled.connect(player.set_muted)
        self._mute = mute
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.addWidget(self._slider, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(mute, 0, Qt.AlignmentFlag.AlignHCenter)
        menu = QMenu(self)
        action = QWidgetAction(menu)
        action.setDefaultWidget(container)
        menu.addAction(action)
        self.setMenu(menu)
        player.volume_changed.connect(self._update_icon)
        self._update_icon()

    def _update_icon(self) -> None:
        """Show the player state (also changed by the other volume button, in full screen)."""
        silent = self._player.muted or self._player.volume == 0
        self.setIcon(icons.icon("mute" if silent else "volume", size=20))
        for widget in (self._mute, self._slider):
            widget.blockSignals(True)
        self._mute.setChecked(self._player.muted)
        self._slider.setValue(round(self._player.volume * 100))
        for widget in (self._mute, self._slider):
            widget.blockSignals(False)


class _Controls(QWidget):
    """Playback controls on one line: back, play/pause, forward, progress, time, volume, full screen."""

    fullscreen_requested = Signal()

    def __init__(self, player, with_fullscreen: bool = True, parent=None):
        super().__init__(parent)
        self._player = player
        back = _icon_button("back", "Reculer de 5 s")
        back.clicked.connect(lambda: player.skip(-1))
        self._play = QToolButton()
        self._play.setObjectName("PlayButton")
        self._play.setFixedSize(40, 40)
        self._play.setIconSize(QSize(20, 20))
        self._play.setCursor(Qt.CursorShape.PointingHandCursor)
        self._play.clicked.connect(player.toggle)
        forward = _icon_button("forward", "Avancer de 5 s")
        forward.clicked.connect(lambda: player.skip(1))
        self._slider = ProgressSlider()
        self._slider.seek_requested.connect(player.seek)
        self._time = QLabel()
        self._time.setObjectName("Muted")
        self._time.setMinimumWidth(130)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(back)
        layout.addWidget(self._play)
        layout.addWidget(forward)
        layout.addSpacing(6)
        layout.addWidget(self._slider, 1)
        layout.addSpacing(4)
        layout.addWidget(self._time)
        layout.addWidget(_VolumeButton(player))
        if with_fullscreen:
            fullscreen = _icon_button("fullscreen", "Plein écran")
            fullscreen.clicked.connect(self.fullscreen_requested)
            layout.addWidget(fullscreen)
        player.position_changed.connect(self._update)
        player.playing_changed.connect(self._update_play_icon)
        self._update_play_icon(False)
        self._update()

    def _update_play_icon(self, playing: bool) -> None:
        self._play.setIcon(icons.icon("pause" if playing else "play", theme.INK, 20))
        self._play.setToolTip("Pause (Espace)" if playing else "Lecture (Espace)")

    def _update(self, *_args) -> None:
        duration = self._player.duration
        self._slider.set_range(duration)
        self._slider.set_value(self._player.position)
        self._time.setText(f"{format_time(self._player.position)} / {format_time(duration)}")
        self._play.setEnabled(duration > 0)


class PreviewPanel(QWidget):
    """Render area of the editor."""

    fullscreen_requested = Signal()

    def __init__(self, controller, player, parent=None):
        super().__init__(parent)
        self._controller = controller
        self.view = VideoView()
        controls = _Controls(player)
        controls.fullscreen_requested.connect(self.fullscreen_requested)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)
        layout.addWidget(self.view, 1)
        layout.addWidget(controls)
        player.frame_ready.connect(self.view.set_image)
        controller.project_changed.connect(self._update_empty_state)
        self._update_empty_state()

    def _update_empty_state(self) -> None:
        project = self._controller.project
        self.view.set_empty(project is None or project.duration <= 0)


class FullscreenOverlay(QWidget):
    """Full screen video: the rest of the application is greyed out.

    Closed with the cross (top right), a click around the video or Escape.
    """

    def __init__(self, player, parent: QWidget):
        super().__init__(parent)
        self._player = player
        self.view = VideoView()
        self.view.set_empty(False)
        self._controls = _Controls(player, with_fullscreen=False)
        close = QToolButton(self)
        close.setIcon(icons.icon("close", size=24))
        close.setIconSize(QSize(24, 24))
        close.setToolTip("Quitter le plein écran (Échap)")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.hide)
        self._close = close
        self._content = QWidget(self)
        layout = QVBoxLayout(self._content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self.view, 1)
        layout.addWidget(self._controls)
        player.frame_ready.connect(self.view.set_image)
        parent.installEventFilter(self)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.hide()

    def open(self) -> None:
        """Show the overlay over the whole window."""
        self.setGeometry(self.parentWidget().rect())
        self._layout_children()
        self.show()
        self.raise_()
        self.setFocus()
        self._player.refresh()

    def _layout_children(self) -> None:
        margin_x, margin_y = self.width() * 0.06, self.height() * 0.06
        self._content.setGeometry(int(margin_x), int(margin_y), int(self.width() - 2 * margin_x),
                                  int(self.height() - 2 * margin_y))
        self._close.move(self.width() - 56, 16)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize and self.isVisible():
            self.setGeometry(self.parentWidget().rect())
            self._layout_children()
        return super().eventFilter(watched, event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(8, 7, 12, 215))

    def mousePressEvent(self, event) -> None:
        picture = self.view.image_rect().translated(self.view.mapTo(self, QPoint(0, 0)))
        controls = self._controls.geometry().translated(self._content.pos())
        position = event.position()
        if not picture.contains(position) and not QRectF(controls).contains(position):
            self.hide()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        elif event.key() == Qt.Key.Key_Space:
            self._player.toggle()
        else:
            super().keyPressEvent(event)
