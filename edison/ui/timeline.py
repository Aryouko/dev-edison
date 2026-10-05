"""Timeline (CDC "Trame"): toolbar, time ruler, tracks, clips and cursor.

The timeline is a single widget painted by hand with QPainter (``paintEvent``).

Ready:
    * geometry helpers: time <-> x position, track index <-> y position;
    * painting of the ruler (mm:ss graduations), of the track headers, of the
      lanes and of the cursor (playhead) extended over every track;
    * scroll bars, "+ Piste" button, toolbar connected to the controller.

To do (sprint S3 "Timeline navigable", then S5):
    * ``_paint_clips``: draw the clips of each track;
    * mouse: click on the ruler -> move the cursor; select, move, trim the clips;
      select the junction between two touching clips; right click menus;
    * wheel: alone = horizontal scroll, Ctrl + wheel = zoom (CDC);
    * drop of a tile of the "Import" tab (``MEDIA_MIME``).

Rule: during a drag, only draw a preview; send ONE change to the controller when
the mouse button is released (one undoable action per drag).
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QScrollBar, QToolButton, QVBoxLayout, QWidget

from edison.config import ASSETS_DIR
from edison.model.project import AUDIO, EFFECT, VIDEO
from edison.ui import icons, theme
from edison.ui.painting import draw_pixmap, rounded
from edison.utils import format_time

HEADER_WIDTH = 132  # width of the column with the track names
RULER_HEIGHT = 30
TRACK_HEIGHT = 48
TRACK_SPACING = 6
MIN_ZOOM, MAX_ZOOM = 4.0, 800.0  # pixels per second (Ctrl + wheel)
TAIL_SECONDS = 30.0  # scrollable empty space after the last clip
RULER_STEPS = (0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600)  # possible gaps between graduations
TRACK_ICONS = {VIDEO: "video", AUDIO: "audio", EFFECT: "sparkles"}


class TimelineWidget(QWidget):
    """Painted multitrack timeline.

    Parameters
    ----------
    controller : ProjectController
        Gives the project (read only here) and receives the edits.
    hbar, vbar : QScrollBar
        Scroll bars placed around the widget by :class:`TimelinePanel`.
    """

    seek_requested = Signal(float)  # the user moved the cursor (connected to Player.seek)

    def __init__(self, controller, hbar: QScrollBar, vbar: QScrollBar, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._hbar, self._vbar = hbar, vbar
        self._zoom = 40.0  # pixels per second
        self._scroll_x = 0  # pixels
        self._scroll_y = 0
        self._playhead = 0.0  # seconds
        self._empty_mascot = QPixmap(str(ASSETS_DIR / "mascot_sleeping.png"))
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setMinimumHeight(RULER_HEIGHT + 2 * (TRACK_HEIGHT + TRACK_SPACING) + TRACK_SPACING)
        hbar.valueChanged.connect(self._on_hbar)
        vbar.valueChanged.connect(self._on_vbar)

        # "+ Piste" button in the top left corner
        self._add_track = QToolButton(self)
        self._add_track.setObjectName("ToolbarButton")
        self._add_track.setText("Piste")
        self._add_track.setIcon(icons.icon("plus", size=14))
        self._add_track.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._add_track.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._add_track.setToolTip("Ajouter une piste")
        menu = QMenu(self._add_track)
        for kind, label in ((VIDEO, "Piste vidéo"), (AUDIO, "Piste audio"), (EFFECT, "Piste d'effets")):
            # TODO(S3): editing.add_track(project, kind) + controller.add_track(kind)
            menu.addAction(icons.icon(TRACK_ICONS[kind], size=16), label,
                           lambda: controller.todo("Ajouter une piste", "S3"))
        self._add_track.setMenu(menu)
        self._add_track.setGeometry(10, 3, HEADER_WIDTH - 20, RULER_HEIGHT - 6)

        controller.project_changed.connect(self._on_project_changed)
        controller.selection_changed.connect(self.update)

    @property
    def project(self):
        return self._controller.project

    def set_playhead(self, time: float, follow: bool = False) -> None:
        """Move the cursor (``Player.position_changed``).

        TODO(S4): with ``follow`` (during playback), scroll when the cursor leaves the view.
        """
        self._playhead = time
        self.update()

    # ============================================================== geometry
    def _x_for(self, time: float) -> float:
        """x position of a time, in pixels."""
        return HEADER_WIDTH + time * self._zoom - self._scroll_x

    def _time_at(self, x: float) -> float:
        """Time at an x position, in seconds."""
        return max(0.0, (x - HEADER_WIDTH + self._scroll_x) / self._zoom)

    def _track_top(self, index: int) -> float:
        """y position of the top of a track (index in ``project.tracks``)."""
        return RULER_HEIGHT + TRACK_SPACING + index * (TRACK_HEIGHT + TRACK_SPACING) - self._scroll_y

    def _track_index_at(self, y: float) -> int | None:
        """Index of the track at a y position, or None."""
        if self.project is None or y < RULER_HEIGHT:
            return None
        index = int((y - RULER_HEIGHT - TRACK_SPACING / 2 + self._scroll_y) // (TRACK_HEIGHT + TRACK_SPACING))
        return index if 0 <= index < len(self.project.tracks) else None

    def _clip_rect(self, index: int, start: float, duration: float) -> QRectF:
        """Rectangle of a clip (track index, start and duration in seconds)."""
        return QRectF(self._x_for(start), self._track_top(index), max(duration * self._zoom, 3.0), TRACK_HEIGHT)

    def _content_height(self) -> int:
        count = len(self.project.tracks) if self.project else 0
        return RULER_HEIGHT + TRACK_SPACING + count * (TRACK_HEIGHT + TRACK_SPACING)

    # ============================================================= scrolling
    def _update_scrollbars(self) -> None:
        """Adapt the scroll bars to the length of the montage, the zoom and the number of tracks."""
        visible_width = max(1, self.width() - HEADER_WIDTH)
        duration = self.project.duration if self.project else 0.0
        self._hbar.setRange(0, max(0, int((duration + TAIL_SECONDS) * self._zoom - visible_width)))
        self._hbar.setPageStep(visible_width)
        self._hbar.setSingleStep(40)
        visible_height = max(1, self.height() - RULER_HEIGHT)
        vertical = max(0, self._content_height() - RULER_HEIGHT - visible_height)
        self._vbar.setRange(0, vertical)
        self._vbar.setPageStep(visible_height)
        self._vbar.setVisible(vertical > 0)

    def _on_hbar(self, value: int) -> None:
        self._scroll_x = value
        self.update()

    def _on_vbar(self, value: int) -> None:
        self._scroll_y = value
        self.update()

    def _on_project_changed(self) -> None:
        self._update_scrollbars()
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_scrollbars()

    def wheelEvent(self, event) -> None:
        """TODO(S3) CDC "Ctrl + molette zoome et dézoome, la molette seule fait défiler horizontalement".

        * Ctrl: ``self._zoom *= 1.2 ** (event.angleDelta().y() / 120)`` (between MIN_ZOOM and
          MAX_ZOOM), keeping the time under the mouse at the same place (adjust ``self._hbar``);
        * otherwise: ``self._hbar.setValue(self._hbar.value() - event.angleDelta().y())``;
        * then ``self._update_scrollbars()`` and ``self.update()``.
        """
        event.accept()

    # ================================================================= mouse
    def mousePressEvent(self, event) -> None:
        """TODO(S3) — what the left click does depends on what is under the mouse:

        * ruler (``y < RULER_HEIGHT``): ``self.seek_requested.emit(self._time_at(x))``, and keep
          following the mouse while the button is held (in ``mouseMoveEvent``);
        * junction between two touching clips (a few pixels around it): ``controller.select_junction``;
        * edge of a clip (a few pixels inside it): start a trim;
        * clip: ``controller.select_clips([clip.id], toggle=Ctrl)``, then start a move;
        * empty place: ``controller.clear_selection()``.

        Right click on a clip: context menu of the CDC ("Piste vidéo" / "Piste audio" menus).
        Tip: write a ``_hit_test(position)`` method returning what is under the mouse.
        """

    def mouseMoveEvent(self, event) -> None:
        """TODO(S3): update the preview of the current drag (seek, move or trim) and the cursor shape.

        CDC "Magnétisme": when an edge comes close to another clip edge or to the cursor
        (e.g. 10 pixels), align it exactly.
        """

    def mouseReleaseEvent(self, event) -> None:
        """TODO(S3): end of the drag -> ONE call: ``controller.move_clips(...)`` or ``controller.trim_clip(...)``."""

    # ========================================================= drag and drop
    def dragEnterEvent(self, event) -> None:
        """TODO(S3): accept the tiles of the "Import" tab (``event.mimeData().hasFormat(MEDIA_MIME)``)."""
        event.ignore()

    def dropEvent(self, event) -> None:
        """TODO(S3): ``controller.add_media_clip(media_id, self._time_at(x), hovered_track_id)``."""

    # ============================================================== painting
    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor(theme.SURFACE))
        if self.project is None:
            return
        lanes = QRectF(HEADER_WIDTH, RULER_HEIGHT, self.width() - HEADER_WIDTH, self.height() - RULER_HEIGHT)
        painter.save()
        painter.setClipRect(lanes)  # clips never overlap the headers or the ruler
        self._paint_lanes(painter)
        self._paint_clips(painter)
        if self.project.duration <= 0:
            self._paint_empty_state(painter, lanes)
        painter.restore()
        self._paint_headers(painter)
        self._paint_ruler(painter)
        self._paint_playhead(painter)

    def _paint_lanes(self, painter: QPainter) -> None:
        for index, _track in enumerate(self.project.tracks):
            lane = QRectF(HEADER_WIDTH, self._track_top(index), self.width() - HEADER_WIDTH, TRACK_HEIGHT)
            painter.fillPath(rounded(lane, 6), QColor(theme.BACKGROUND))

    def _paint_clips(self, painter: QPainter) -> None:
        """TODO(S3): draw every clip.

        For each ``index, track`` of ``self.project.tracks`` and each clip of the track:
            * ``rect = self._clip_rect(index, clip.start, clip.duration)``;
            * fill ``rounded(rect, 6)`` with ``theme.VIDEO_CLIP`` / ``theme.AUDIO_CLIP`` /
              ``theme.EFFECT_CLIP`` (``..._SELECTED`` if ``clip.id in controller.selected_clips``);
            * write the media name (``project.get_media(clip.media_id).name``) in the top left corner;
            * selected clip: ``theme.ACCENT`` border of 2 pixels (as on the mock-up).
        Later: the waveform of the audio clips (S4), an icon on clips with effects (S5).
        """

    def _paint_empty_state(self, painter: QPainter, lanes: QRectF) -> None:
        height = min(70.0, lanes.height() * 0.5)
        width = height * self._empty_mascot.width() / max(1, self._empty_mascot.height())
        center = lanes.center()
        text = "La trame est vide : glissez ici un média depuis l'onglet Import"
        text_width = painter.fontMetrics().horizontalAdvance(text)
        left = center.x() - (width + 16 + text_width) / 2
        painter.setOpacity(0.8)
        draw_pixmap(painter, QRectF(left, center.y() - height / 2, width, height), self._empty_mascot)
        painter.setOpacity(1.0)
        painter.setPen(QColor(theme.TEXT_MUTED))
        painter.drawText(QRectF(left + width + 16, center.y() - 12, text_width + 4, 24),
                         Qt.AlignmentFlag.AlignVCenter, text)

    def _paint_headers(self, painter: QPainter) -> None:
        painter.fillRect(QRectF(0, RULER_HEIGHT, HEADER_WIDTH, self.height()), QColor(theme.SURFACE))
        painter.save()
        painter.setClipRect(QRectF(0, RULER_HEIGHT, HEADER_WIDTH, self.height() - RULER_HEIGHT))
        font = QFont(painter.font())
        font.setPointSizeF(9)
        font.setBold(True)
        painter.setFont(font)
        for index, track in enumerate(self.project.tracks):
            rect = QRectF(10, self._track_top(index), HEADER_WIDTH - 20, TRACK_HEIGHT)
            painter.fillPath(rounded(rect, 8), QColor(theme.SURFACE_ALT))
            draw_pixmap(painter, QRectF(rect.left() + 10, rect.center().y() - 8, 16, 16),
                        icons.pixmap(TRACK_ICONS[track.kind], theme.TEXT_MUTED, 16))
            painter.setPen(QColor(theme.TEXT))
            painter.drawText(rect.adjusted(34, 0, -6, 0), Qt.AlignmentFlag.AlignVCenter, track.name)
        painter.restore()

    def _paint_ruler(self, painter: QPainter) -> None:
        """Graduations in mm:ss; their gap depends on the zoom (one label every 80 pixels at least)."""
        painter.fillRect(QRectF(0, 0, self.width(), RULER_HEIGHT), QColor(theme.SURFACE))
        painter.setPen(QColor(theme.BORDER))
        painter.drawLine(QPointF(HEADER_WIDTH, RULER_HEIGHT - 0.5), QPointF(self.width(), RULER_HEIGHT - 0.5))
        major = next((step for step in RULER_STEPS if step * self._zoom >= 80), RULER_STEPS[-1])
        minor = major / 5 if major * self._zoom / 5 >= 10 else major / 2
        ticks_per_major = round(major / minor)
        font = QFont(painter.font())
        font.setPointSizeF(8)
        painter.setFont(font)
        painter.save()
        painter.setClipRect(QRectF(HEADER_WIDTH, 0, self.width() - HEADER_WIDTH, RULER_HEIGHT))
        tick = math.floor(self._time_at(HEADER_WIDTH) / minor)
        while True:
            time = tick * minor
            x = self._x_for(time)
            if x > self.width():
                break
            is_major = tick % ticks_per_major == 0
            painter.setPen(QColor(theme.TEXT_MUTED if is_major else theme.BORDER))
            painter.drawLine(QPointF(x, RULER_HEIGHT - (10 if is_major else 5)), QPointF(x, RULER_HEIGHT - 1))
            if is_major:
                painter.drawText(QPointF(x + 4, RULER_HEIGHT - 12), format_time(time, precise=major < 1))
            tick += 1
        painter.restore()

    def _paint_playhead(self, painter: QPainter) -> None:
        """Cursor: a vertical line over every track, with a handle in the ruler (lime, as on the mock-up)."""
        x = self._x_for(self._playhead)
        if x < HEADER_WIDTH - 1 or x > self.width() + 1:
            return
        color = QColor(theme.ACCENT)
        painter.setPen(QPen(color, 2))
        painter.drawLine(QPointF(x, RULER_HEIGHT - 8), QPointF(x, self.height()))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPolygon(QPolygonF([QPointF(x - 7, 3), QPointF(x + 7, 3), QPointF(x + 7, 13),
                                       QPointF(x, 20), QPointF(x - 7, 13)]))


class TimelinePanel(QWidget):
    """Toolbar (CDC "Liste des outils") above the timeline."""

    def __init__(self, controller, player, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._player = player

        stack = controller.undo_stack
        self.undo_action = self._action("undo", "Annuler", "Annule la dernière action (Ctrl+Z)", stack.undo,
                                        QKeySequence.StandardKey.Undo)
        self.redo_action = self._action("redo", "Rétablir", "Rétablit l'action annulée (Ctrl+Y)", stack.redo,
                                        QKeySequence("Ctrl+Y"))
        self.delete_action = self._action("trash", "Supprimer", "Supprime les éléments sélectionnés (Suppr)",
                                          controller.delete_selection, QKeySequence.StandardKey.Delete)
        self.cut_action = self._action("cut", "Couper", "Coupe le clip sélectionné à la position du curseur",
                                       lambda: controller.cut(player.position))
        self.merge_action = self._action("merge", "Fusionner",
                                         "Fusionne deux clips collés quand la jonction est sélectionnée",
                                         controller.merge_selected_junction)
        # TODO(S5): open the effects pop-up (edison/ui/effects_dialog.py) for the selected clips.
        self.effect_action = self._action("sparkles", "Effet", "Ouvre la pop-up des effets pour l'élément sélectionné",
                                          lambda: controller.todo("Pop-up des effets", "S5"))

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(12, 8, 12, 4)
        toolbar.setSpacing(6)
        for action in (self.undo_action, self.redo_action, self.delete_action, self.cut_action,
                       self.merge_action, self.effect_action):
            button = QToolButton()
            button.setObjectName("ToolbarButton")
            button.setDefaultAction(action)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setIconSize(QSize(16, 16))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            toolbar.addWidget(button)
        toolbar.addStretch()
        hint = QLabel("Molette : défiler   •   Ctrl + molette : zoomer")
        hint.setObjectName("Muted")
        toolbar.addWidget(hint)

        hbar = QScrollBar(Qt.Orientation.Horizontal)
        vbar = QScrollBar(Qt.Orientation.Vertical)
        self.timeline = TimelineWidget(controller, hbar, vbar)
        self.timeline.seek_requested.connect(player.seek)
        area = QHBoxLayout()
        area.setContentsMargins(0, 0, 0, 0)
        area.setSpacing(0)
        area.addWidget(self.timeline, 1)
        area.addWidget(vbar)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 6)
        layout.setSpacing(4)
        layout.addLayout(toolbar)
        layout.addLayout(area, 1)
        layout.addWidget(hbar)

        stack.canUndoChanged.connect(self._update_actions)
        stack.canRedoChanged.connect(self._update_actions)
        controller.selection_changed.connect(self._update_actions)
        player.position_changed.connect(self.timeline.set_playhead)
        self._update_actions()

    def _action(self, icon: str, text: str, tooltip: str, slot, shortcut=None) -> QAction:
        """Create a toolbar action (its shortcut works in the whole window)."""
        action = QAction(icons.icon(icon, size=16), text, self)
        action.setToolTip(tooltip)
        action.triggered.connect(slot)
        if shortcut is not None:
            action.setShortcut(shortcut)
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        return action

    def _update_actions(self) -> None:
        """Enable the tools that can be used now (greyed out otherwise)."""
        stack = self._controller.undo_stack
        self.undo_action.setEnabled(stack.canUndo())
        self.redo_action.setEnabled(stack.canRedo())
        self.delete_action.setEnabled(bool(self._controller.selected_clips))
        # TODO(S3): enable "Couper" only if a selected clip is under the cursor,
        # and "Fusionner" only if a junction is selected.
