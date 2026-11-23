"""Timeline ("trame"): toolbar, time ruler, tracks, clips and playhead.

The timeline is painted by hand with QPainter. Mouse interactions only
compute a preview while dragging; the change is sent to the controller when
the mouse button is released (one undoable action per drag).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QScrollBar, QToolButton, QVBoxLayout, QWidget

from edison.config import ASSETS_DIR, WAVEFORM_RATE
from edison.effects import get_effect
from edison.effects.audio import FADE
from edison.model import editing
from edison.model.project import AUDIO, EFFECT, VIDEO, Clip, EffectInstance, Media, Track
from edison.render.renderer import gain_envelope
from edison.ui import icons, theme
from edison.ui.dialogs import VolumeDialog
from edison.ui.effects_dialog import EffectsDialog
from edison.ui.import_panel import MEDIA_MIME
from edison.ui.painting import draw_pixmap, rounded
from edison.utils import format_time

HEADER_WIDTH = 132
RULER_HEIGHT = 30
TRACK_HEIGHT = 48
TRACK_SPACING = 6
EDGE_GRAB = 9  # pixels, trim handles inside the clip edges
JUNCTION_GRAB = 4  # pixels around the junction of two touching clips
SNAP_DISTANCE = 10  # pixels
DRAG_THRESHOLD = 4  # pixels before a click becomes a drag
MIN_ZOOM, MAX_ZOOM = 4.0, 800.0  # pixels per second
TAIL_SECONDS = 30.0  # scrollable space after the last clip
RULER_STEPS = (0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600)
TRACK_ICONS = {VIDEO: "video", AUDIO: "audio", EFFECT: "sparkles"}


@dataclass
class _Hit:
    """What is under the mouse."""

    area: str  # "ruler", "header", "clip", "edge", "junction", "lane" or "none"
    track: Track | None = None
    clip: Clip | None = None
    edge: str = ""
    right: Clip | None = None  # right clip of a junction


@dataclass
class _Drag:
    """State of a mouse drag."""

    mode: str  # "seek", "move" or "trim"
    clip_id: str = ""
    press: QPointF = field(default_factory=QPointF)
    started: bool = False
    clip_ids: set = field(default_factory=set)
    delta: float = 0.0
    target_track_id: str | None = None
    valid: bool = True
    edge: str = ""
    bounds: tuple = (0.0, 0.0)


@dataclass
class _Drop:
    """Preview of a media dragged from the library."""

    media: Media
    start: float
    plan: editing.AddPlan


class TimelineWidget(QWidget):
    """Painted multitrack timeline."""

    seek_requested = Signal(float)
    clip_menu_requested = Signal(str, QPoint)
    track_menu_requested = Signal(str, QPoint)
    lane_menu_requested = Signal(str, float, QPoint)  # track, time, position
    clip_double_clicked = Signal(str)

    def __init__(self, controller, hbar: QScrollBar, vbar: QScrollBar, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._hbar, self._vbar = hbar, vbar
        self._zoom = 40.0
        self._scroll_x = 0
        self._scroll_y = 0
        self._playhead = 0.0
        self._drag: _Drag | None = None
        self._drop: _Drop | None = None
        self._empty_mascot = QPixmap(str(ASSETS_DIR / "mascot_sleeping.png"))
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setMinimumHeight(RULER_HEIGHT + 2 * (TRACK_HEIGHT + TRACK_SPACING) + TRACK_SPACING)
        hbar.valueChanged.connect(self._on_hbar)
        vbar.valueChanged.connect(self._on_vbar)

        self._add_track = QToolButton(self)
        self._add_track.setObjectName("ToolbarButton")
        self._add_track.setText("Piste")
        self._add_track.setIcon(icons.icon("plus", size=14))
        self._add_track.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._add_track.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._add_track.setToolTip("Ajouter une piste")
        menu = QMenu(self._add_track)
        menu.addAction(icons.icon("video", size=16), "Piste vidéo", lambda: controller.add_track(VIDEO))
        menu.addAction(icons.icon("audio", size=16), "Piste audio", lambda: controller.add_track(AUDIO))
        menu.addAction(icons.icon("sparkles", size=16), "Piste d'effets", lambda: controller.add_track(EFFECT))
        self._add_track.setMenu(menu)
        self._add_track.setGeometry(10, 3, HEADER_WIDTH - 20, RULER_HEIGHT - 6)

        controller.project_changed.connect(self._on_project_changed)
        controller.selection_changed.connect(self.update)
        controller.media_changed.connect(self.update)

    # ================================================================ public
    @property
    def project(self):
        return self._controller.project

    def set_playhead(self, time: float, follow: bool = False) -> None:
        """Move the playhead; with ``follow``, scroll to keep it visible (playback)."""
        self._playhead = time
        if follow:
            x = self._x_for(time)
            if x > self.width() - 40 or x < HEADER_WIDTH:
                self._hbar.setValue(int(time * self._zoom - (self.width() - HEADER_WIDTH) * 0.1))
        self.update()

    # ============================================================== geometry
    def _x_for(self, time: float) -> float:
        return HEADER_WIDTH + time * self._zoom - self._scroll_x

    def _time_at(self, x: float) -> float:
        return max(0.0, (x - HEADER_WIDTH + self._scroll_x) / self._zoom)

    def _track_top(self, index: int) -> float:
        return RULER_HEIGHT + TRACK_SPACING + index * (TRACK_HEIGHT + TRACK_SPACING) - self._scroll_y

    def _track_index_at(self, y: float) -> int | None:
        if self.project is None or y < RULER_HEIGHT:
            return None
        index = int((y - RULER_HEIGHT - TRACK_SPACING / 2 + self._scroll_y) // (TRACK_HEIGHT + TRACK_SPACING))
        return index if 0 <= index < len(self.project.tracks) else None

    def _track_index(self, track_id: str | None) -> int | None:
        return next((i for i, t in enumerate(self.project.tracks) if t.id == track_id), None)

    def _clip_rect(self, index: int, start: float, duration: float) -> QRectF:
        return QRectF(self._x_for(start), self._track_top(index), max(duration * self._zoom, 3.0), TRACK_HEIGHT)

    def _content_height(self) -> int:
        count = len(self.project.tracks) if self.project else 0
        return RULER_HEIGHT + TRACK_SPACING + count * (TRACK_HEIGHT + TRACK_SPACING)

    def _hit_test(self, position: QPointF) -> _Hit:
        x, y = position.x(), position.y()
        if self.project is None:
            return _Hit("none")
        if y < RULER_HEIGHT:
            return _Hit("ruler" if x >= HEADER_WIDTH else "none")
        index = self._track_index_at(y)
        if index is None:
            return _Hit("none")
        track = self.project.tracks[index]
        top = self._track_top(index)
        if not top <= y <= top + TRACK_HEIGHT:
            return _Hit("none")
        if x < HEADER_WIDTH:
            return _Hit("header", track)
        for left, right in zip(track.clips, track.clips[1:]):
            if abs(left.end - right.start) < editing.JOIN_TOLERANCE and abs(x - self._x_for(right.start)) <= JUNCTION_GRAB:
                return _Hit("junction", track, left, right=right)
        for clip in track.clips:
            left_x, right_x = self._x_for(clip.start), self._x_for(clip.end)
            if left_x <= x <= right_x:
                grab = min(EDGE_GRAB, (right_x - left_x) / 4)
                if x - left_x <= grab:
                    return _Hit("edge", track, clip, "start")
                if right_x - x <= grab:
                    return _Hit("edge", track, clip, "end")
                return _Hit("clip", track, clip)
        return _Hit("lane", track)

    # ============================================================= scrolling
    def _update_scrollbars(self) -> None:
        visible_width = max(1, self.width() - HEADER_WIDTH)
        duration = self.project.duration if self.project else 0.0
        content_width = (duration + TAIL_SECONDS) * self._zoom
        self._hbar.setRange(0, max(0, int(content_width - visible_width)))
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
        self._drop = None
        self._update_scrollbars()
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_scrollbars()

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:  # zoom around the mouse
            steps = delta.y() / 120
            anchor_x = max(event.position().x(), HEADER_WIDTH)
            anchor_time = self._time_at(anchor_x)
            self._zoom = min(max(self._zoom * 1.2 ** steps, MIN_ZOOM), MAX_ZOOM)
            self._update_scrollbars()
            self._hbar.setValue(int(anchor_time * self._zoom - (anchor_x - HEADER_WIDTH)))
            self.update()
        elif event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._vbar.setValue(self._vbar.value() - (delta.y() or delta.x()))
        else:  # the wheel alone scrolls horizontally
            self._hbar.setValue(self._hbar.value() - (delta.x() or delta.y()))
        event.accept()

    # ================================================================= mouse
    def mousePressEvent(self, event) -> None:
        if self.project is None:
            return
        position = event.position()
        hit = self._hit_test(position)
        if event.button() == Qt.MouseButton.RightButton:
            if hit.clip is not None and hit.area != "junction":
                if hit.clip.id not in self._controller.selected_clips:
                    self._controller.select_clips([hit.clip.id])
                self.clip_menu_requested.emit(hit.clip.id, event.globalPosition().toPoint())
            elif hit.area == "header":
                self.track_menu_requested.emit(hit.track.id, event.globalPosition().toPoint())
            elif hit.area == "lane":
                self.lane_menu_requested.emit(hit.track.id, self._time_at(position.x()),
                                              event.globalPosition().toPoint())
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if hit.area == "ruler":
            self._drag = _Drag("seek")
            self.seek_requested.emit(self._time_at(position.x()))
        elif hit.area == "junction":
            self._controller.select_junction(hit.track.id, hit.clip.id, hit.right.id)
        elif hit.area == "edge":
            self._controller.select_clips([hit.clip.id])
            self._drag = _Drag("trim", clip_id=hit.clip.id, press=position, edge=hit.edge,
                               bounds=editing.trim_bounds(self.project, hit.clip.id, hit.edge))
        elif hit.area == "clip":
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._controller.select_clips([hit.clip.id], toggle=True)
                return
            if hit.clip.id not in self._controller.selected_clips:
                self._controller.select_clips([hit.clip.id])
            self._drag = _Drag("move", clip_id=hit.clip.id, press=position,
                               clip_ids=set(self._controller.selected_clips))
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        else:
            self._controller.clear_selection()

    def mouseMoveEvent(self, event) -> None:
        position = event.position()
        if self._drag is None:
            self._update_cursor(self._hit_test(position))
        elif self._drag.mode == "seek":
            self.seek_requested.emit(self._time_at(position.x()))
        elif self._drag.mode == "move":
            self._update_move(position)
        elif self._drag.mode == "trim":
            self._update_trim(position)

    def mouseReleaseEvent(self, event) -> None:
        drag, self._drag = self._drag, None
        if drag is None or event.button() != Qt.MouseButton.LeftButton:
            return
        if drag.mode == "move":
            origin = self.project.find_clip(drag.clip_id)
            changed_track = origin is not None and drag.target_track_id not in (None, origin[0].id)
            if drag.started and (abs(drag.delta) > 1e-9 or changed_track):
                if drag.valid:
                    self._controller.move_clips(drag.clip_ids, drag.delta, drag.clip_id, drag.target_track_id)
                else:
                    self._controller.message.emit("Impossible de déplacer ici : l'emplacement est déjà occupé.")
            elif not drag.started:
                self._controller.select_clips([drag.clip_id])  # a simple click keeps only this clip
        elif drag.mode == "trim" and abs(drag.delta) > 1e-9:
            self._controller.trim_clip(drag.clip_id, drag.edge, drag.delta)
        self._update_cursor(self._hit_test(event.position()))
        self.update()

    def mouseDoubleClickEvent(self, event) -> None:
        hit = self._hit_test(event.position())
        if event.button() == Qt.MouseButton.LeftButton and hit.clip is not None and hit.area in ("clip", "edge"):
            self.clip_double_clicked.emit(hit.clip.id)

    def leaveEvent(self, _event) -> None:
        if self._drag is None:
            self.unsetCursor()

    def _update_cursor(self, hit: _Hit) -> None:
        cursors = {
            "edge": Qt.CursorShape.SizeHorCursor,
            "junction": Qt.CursorShape.SplitHCursor,
            "clip": Qt.CursorShape.OpenHandCursor,
            "ruler": Qt.CursorShape.PointingHandCursor,
        }
        self.setCursor(cursors.get(hit.area, Qt.CursorShape.ArrowCursor))
        tooltips = {
            "junction": "Jonction : cliquez pour la sélectionner, puis « Fusionner »",
            "edge": "Tirez pour rogner le clip",
        }
        self.setToolTip(tooltips.get(hit.area, ""))

    def _snap(self, times: list[float], exclude_ids) -> float:
        """Return the offset aligning one of ``times`` on a clip edge or the playhead."""
        points = editing.snap_points(self.project, exclude_ids) + [self._playhead]
        best = None
        for time in times:
            for point in points:
                offset = point - time
                if abs(offset) * self._zoom <= SNAP_DISTANCE and (best is None or abs(offset) < abs(best)):
                    best = offset
        return best or 0.0

    def _update_move(self, position: QPointF) -> None:
        drag = self._drag
        if not drag.started:
            moved = abs(position.x() - drag.press.x()) + abs(position.y() - drag.press.y())
            if moved < DRAG_THRESHOLD:
                return
            drag.started = True
        found = self.project.find_clip(drag.clip_id)
        if found is None:
            return
        origin_track = found[0]
        clips = [clip for _, clip in self.project.iter_clips() if clip.id in drag.clip_ids]
        earliest = min(clip.start for clip in clips)
        delta = max((position.x() - drag.press.x()) / self._zoom, -earliest)
        delta += self._snap([t + delta for c in clips for t in (c.start, c.end)], drag.clip_ids)
        delta = max(delta, -earliest)
        index = self._track_index_at(position.y())
        target = self.project.tracks[index] if index is not None else origin_track
        if target.kind != origin_track.kind:
            target = origin_track
        drag.delta = delta
        drag.target_track_id = target.id
        drag.valid = editing.can_move(self.project, drag.clip_ids, delta, drag.clip_id, target.id)
        self.update()

    def _update_trim(self, position: QPointF) -> None:
        drag = self._drag
        found = self.project.find_clip(drag.clip_id)
        if found is None:
            return
        clip = found[1]
        delta = (position.x() - drag.press.x()) / self._zoom
        edge_time = (clip.start if drag.edge == "start" else clip.end) + delta
        linked = {clip.id} | {c.id for c in self.project.linked_clips(clip)}
        delta += self._snap([edge_time], linked)
        low, high = drag.bounds
        drag.delta = min(max(delta, low), high)
        self.update()

    # ========================================================= drag and drop
    def _media_from(self, event) -> Media | None:
        if self.project is None or not event.mimeData().hasFormat(MEDIA_MIME):
            return None
        media_id = bytes(event.mimeData().data(MEDIA_MIME)).decode()
        return self.project.get_media(media_id)

    def dragEnterEvent(self, event) -> None:
        if self._media_from(event) is not None:
            event.acceptProposedAction()
            self._update_drop(event)
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if self._media_from(event) is not None:
            event.acceptProposedAction()
            self._update_drop(event)

    def dragLeaveEvent(self, _event) -> None:
        self._drop = None
        self.update()

    def dropEvent(self, event) -> None:
        drop, self._drop = self._drop, None
        if drop is not None:
            event.acceptProposedAction()
            if drop.plan.valid:
                self._controller.add_media_clip(drop.media.id, drop.start, drop.plan.main_track_id)
            else:
                self._controller.message.emit("Cet emplacement est déjà occupé par un autre clip.")
        self.update()

    def _update_drop(self, event) -> None:
        media = self._media_from(event)
        position = event.position()
        start = self._time_at(position.x())
        start = max(0.0, start + self._snap([start, start + media.duration], ()))
        index = self._track_index_at(position.y())
        hovered = self.project.tracks[index].id if index is not None else None
        self._drop = _Drop(media, start, editing.plan_add_media(self.project, media, start, hovered))
        self.update()

    # ============================================================== painting
    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor(theme.SURFACE))
        if self.project is None:
            return
        lanes = QRectF(HEADER_WIDTH, RULER_HEIGHT, self.width() - HEADER_WIDTH, self.height() - RULER_HEIGHT)
        painter.save()
        painter.setClipRect(lanes)
        self._paint_lanes(painter)
        self._paint_clips(painter)
        self._paint_junction(painter)
        self._paint_drop(painter)
        if self.project.duration <= 0 and self._drop is None:
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
        drag = self._drag
        moving = drag is not None and drag.mode == "move" and drag.started
        trimming = drag is not None and drag.mode == "trim"
        trimmed_ids = set()
        if trimming:
            found = self.project.find_clip(drag.clip_id)
            if found:
                trimmed_ids = {found[1].id} | {c.id for c in self.project.linked_clips(found[1])}
        selected = self._controller.selected_clips
        for index, track in enumerate(self.project.tracks):
            for clip in track.clips:
                start, duration, in_point = clip.start, clip.duration, clip.in_point
                if clip.id in trimmed_ids:
                    if drag.edge == "start":
                        start, duration, in_point = start + drag.delta, duration - drag.delta, in_point + drag.delta
                    else:
                        duration += drag.delta
                is_moving = moving and clip.id in drag.clip_ids
                rect = self._clip_rect(index, start, duration)
                self._paint_clip(painter, rect, clip, track.kind, clip.id in selected, 0.35 if is_moving else 1.0,
                                 in_point=in_point)
        if moving:  # ghosts at the new position
            for index, track in enumerate(self.project.tracks):
                for clip in track.clips:
                    if clip.id not in drag.clip_ids:
                        continue
                    target = index
                    if clip.id == drag.clip_id:
                        target = self._track_index(drag.target_track_id)
                        target = index if target is None else target
                    rect = self._clip_rect(target, clip.start + drag.delta, clip.duration)
                    self._paint_clip(painter, rect, clip, track.kind, True, 0.9, invalid=not drag.valid)

    def _paint_clip(self, painter: QPainter, rect: QRectF, clip: Clip, kind: str, selected: bool,
                    opacity: float = 1.0, invalid: bool = False, in_point: float | None = None) -> None:
        media = self.project.get_media(clip.media_id)
        missing = not clip.is_effect_block and (media is None or clip.media_id in self._controller.missing)
        if missing:
            color = theme.MISSING_CLIP
        elif kind == EFFECT:
            color = theme.EFFECT_CLIP_SELECTED if selected else theme.EFFECT_CLIP
        elif kind == VIDEO:
            color = theme.VIDEO_CLIP_SELECTED if selected else theme.VIDEO_CLIP
        else:
            color = theme.AUDIO_CLIP_SELECTED if selected else theme.AUDIO_CLIP
        body = rect.adjusted(0.5, 1, -0.5, -1)
        path = rounded(body, 6)
        painter.save()
        painter.setOpacity(opacity)
        painter.fillPath(path, QColor(color))
        painter.setClipPath(path, Qt.ClipOperation.IntersectClip)
        if kind == AUDIO:
            self._paint_waveform(painter, body, clip, clip.in_point if in_point is None else in_point)
        self._paint_fades(painter, body, clip)
        # Texts
        font = QFont(painter.font())
        font.setPointSizeF(8.5)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(theme.TEXT))
        # Keep the texts readable when the beginning of the clip is scrolled out of view
        visible_left = max(body.left(), HEADER_WIDTH)
        text_rect = QRectF(visible_left + 9, body.top() + 6, body.right() - visible_left - 17, body.height() - 12)
        effects = self._effect_labels(clip)
        if clip.is_effect_block:
            name = " + ".join(effects) or "Effet"
        else:
            name = media.name if media else "Média supprimé"
        if effects and not clip.is_effect_block:  # small icon showing the applied effects
            badge = f"{len(effects)}"
            badge_width = painter.fontMetrics().horizontalAdvance(badge) + 24
            badge_rect = QRectF(text_rect.right() - badge_width, text_rect.top() - 2, badge_width, 18)
            if badge_rect.left() > text_rect.left() + 30:
                painter.fillPath(rounded(badge_rect, 9), QColor(0, 0, 0, 90))
                draw_pixmap(painter, QRectF(badge_rect.left() + 5, badge_rect.top() + 3, 12, 12),
                            icons.pixmap("sparkles", theme.ACCENT, 12))
                painter.drawText(badge_rect.adjusted(19, 0, -5, 0), Qt.AlignmentFlag.AlignVCenter, badge)
                text_rect.setRight(badge_rect.left() - 6)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                         painter.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, int(text_rect.width())))
        details = []
        if missing:
            details.append("Fichier introuvable")
        if kind == AUDIO and abs(clip.volume - 1.0) > 1e-3:
            details.append(f"Volume {clip.volume * 100:.0f} %")
        if clip.link_id and self.project.linked_clips(clip):
            details.append("lié")
        if details:
            font.setBold(False)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255, 170))
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                             " • ".join(details))
        painter.restore()
        if selected or invalid:
            painter.save()
            painter.setOpacity(opacity)
            painter.setPen(QPen(QColor(theme.DANGER if invalid else theme.ACCENT), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
            painter.restore()

    @staticmethod
    def _effect_labels(clip: Clip) -> list[str]:
        plugins = [get_effect(effect.type) for effect in clip.effects]
        return [plugin.label for plugin in plugins if plugin is not None]

    def _paint_waveform(self, painter: QPainter, body: QRectF, clip: Clip, in_point: float) -> None:
        """Draw the loudness of the sound along the clip (with its volume and fades)."""
        peaks = self._controller.waveforms.get(clip.media_id)
        left, right = max(body.left(), HEADER_WIDTH), min(body.right(), self.width())
        columns = int(right - left)
        if peaks is None or len(peaks) == 0 or columns < 2:
            return
        # Time (from the clip start) of the edges of each visible pixel column
        offsets = (np.arange(columns + 1) + left - body.left()) / self._zoom
        positions = (in_point + offsets) * WAVEFORM_RATE
        if WAVEFORM_RATE >= self._zoom:  # several values per pixel: keep the loudest one
            edges = np.clip(positions.astype(int), 0, len(peaks) - 1)
            values = np.maximum.reduceat(peaks, edges[:-1])
        else:
            values = np.interp(positions[:-1], np.arange(len(peaks)), peaks)
        values = np.clip(values * gain_envelope(clip, offsets[:-1]), 0.0, 1.3) / 1.3
        center, half = body.center().y() + 4, body.height() / 2 - 6
        xs = left + np.arange(columns) + 0.5
        top = [QPointF(x, center - v * half) for x, v in zip(xs, values)]
        bottom = [QPointF(x, center + v * half) for x, v in zip(xs[::-1], values[::-1])]
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 70))
        painter.drawPolygon(QPolygonF(top + bottom))

    def _paint_fades(self, painter: QPainter, body: QRectF, clip: Clip) -> None:
        shade = QColor(0, 0, 0, 90)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(shade)
        if clip.fade_in > 0:
            width = clip.fade_in * self._zoom
            painter.drawPolygon(QPolygonF([body.bottomLeft(), body.topLeft(),
                                           QPointF(body.left() + width, body.top())]))
        if clip.fade_out > 0:
            width = clip.fade_out * self._zoom
            painter.drawPolygon(QPolygonF([body.bottomRight(), body.topRight(),
                                           QPointF(body.right() - width, body.top())]))

    def _paint_junction(self, painter: QPainter) -> None:
        junction = self._controller.selected_junction
        index = self._track_index(junction[0]) if junction else None
        found = self.project.find_clip(junction[2]) if junction else None
        if index is None or found is None:
            return
        x = self._x_for(found[1].start)
        top = self._track_top(index)
        color = QColor(theme.ACCENT)
        painter.fillRect(QRectF(x - 1.5, top - 3, 3, TRACK_HEIGHT + 6), color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        for y in (top - 3, top + TRACK_HEIGHT + 3):
            painter.drawPolygon(QPolygonF([QPointF(x, y - 5), QPointF(x + 5, y), QPointF(x, y + 5), QPointF(x - 5, y)]))

    def _paint_drop(self, painter: QPainter) -> None:
        drop = self._drop
        if drop is None:
            return
        ghost = Clip("", drop.media.id, drop.start, 0.0, drop.media.duration)
        for track_id, kind in ((drop.plan.main_track_id, drop.media.kind),
                               (drop.plan.audio_track_id if drop.plan.needs_audio else None, AUDIO)):
            index = self._track_index(track_id)
            if index is not None:
                rect = self._clip_rect(index, drop.start, drop.media.duration)
                self._paint_clip(painter, rect, ghost, kind, True, 0.75, invalid=not drop.plan.valid)

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
    """Toolbar and timeline, with the clip context menus."""

    def __init__(self, controller, player, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._player = player

        self.undo_action = QAction(icons.icon("undo", size=16), "Annuler", self)
        self.undo_action.setShortcuts([QKeySequence.StandardKey.Undo])
        self.undo_action.triggered.connect(controller.undo_stack.undo)
        self.redo_action = QAction(icons.icon("redo", size=16), "Rétablir", self)
        self.redo_action.setShortcuts([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])
        self.redo_action.triggered.connect(controller.undo_stack.redo)
        self.delete_action = QAction(icons.icon("trash", size=16), "Supprimer", self)
        self.delete_action.setShortcuts([QKeySequence.StandardKey.Delete, QKeySequence(Qt.Key.Key_Backspace)])
        self.delete_action.triggered.connect(controller.delete_selection)
        self.cut_action = QAction(icons.icon("cut", size=16), "Couper", self)
        self.cut_action.setShortcut(QKeySequence("Ctrl+K"))
        self.cut_action.triggered.connect(lambda: controller.cut(player.position))
        self.merge_action = QAction(icons.icon("merge", size=16), "Fusionner", self)
        self.merge_action.setShortcut(QKeySequence("Ctrl+M"))
        self.merge_action.triggered.connect(controller.merge_selected_junction)
        self.effect_action = QAction(icons.icon("sparkles", size=16), "Effet", self)
        self.effect_action.setShortcut(QKeySequence("Ctrl+E"))
        self.effect_action.triggered.connect(self.open_effects)
        tooltips = {
            self.undo_action: "Annule la dernière action (Ctrl+Z)",
            self.redo_action: "Rétablit l'action annulée (Ctrl+Y)",
            self.delete_action: "Supprime les éléments sélectionnés (Suppr)",
            self.cut_action: "Coupe le clip sélectionné à la position du curseur (Ctrl+K)",
            self.merge_action: "Fusionne deux clips collés quand la jonction est sélectionnée (Ctrl+M)",
            self.effect_action: "Ouvre la pop-up des effets pour l'élément sélectionné ; sans sélection, "
                                "ajoute un effet sur la piste d'effets (Ctrl+E)",
        }
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(12, 8, 12, 4)
        toolbar.setSpacing(6)
        for action, tooltip in tooltips.items():
            action.setToolTip(tooltip)
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
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
        self.timeline.clip_menu_requested.connect(self._show_clip_menu)
        self.timeline.track_menu_requested.connect(self._show_track_menu)
        self.timeline.lane_menu_requested.connect(self._show_lane_menu)
        self.timeline.clip_double_clicked.connect(self._on_clip_double_clicked)
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

        controller.undo_stack.canUndoChanged.connect(self._update_actions)
        controller.undo_stack.canRedoChanged.connect(self._update_actions)
        controller.undo_stack.indexChanged.connect(self._update_actions)
        controller.selection_changed.connect(self._update_actions)
        controller.project_changed.connect(self._update_actions)
        player.position_changed.connect(self._on_position_changed)
        self._update_actions()

    def _on_position_changed(self, position: float) -> None:
        self.timeline.set_playhead(position, follow=self._player.playing)
        self.cut_action.setEnabled(self._controller.can_cut(position))

    def _update_actions(self) -> None:
        stack = self._controller.undo_stack
        self.undo_action.setEnabled(stack.canUndo())
        self.redo_action.setEnabled(stack.canRedo())
        self.undo_action.setToolTip(f"Annuler : {stack.undoText()} (Ctrl+Z)" if stack.canUndo() else "Rien à annuler")
        self.redo_action.setToolTip(f"Rétablir : {stack.redoText()} (Ctrl+Y)" if stack.canRedo() else "Rien à rétablir")
        self.delete_action.setEnabled(bool(self._controller.selected_clips))
        self.cut_action.setEnabled(self._controller.can_cut(self._player.position))
        self.merge_action.setEnabled(self._controller.can_merge())
        self.effect_action.setEnabled(self._controller.project is not None)

    # ---------------------------------------------------------------- effects
    def _clips_of(self, kind: str, clip_ids) -> list[Clip]:
        return [clip for track, clip in self._controller.project.iter_clips()
                if clip.id in clip_ids and track.kind == kind]

    def open_effects(self) -> None:
        """"Effet" tool: effects of the selected clips, or a new effect block without selection."""
        selection = self._controller.selected_clips
        video = self._clips_of(VIDEO, selection)
        audio = self._clips_of(AUDIO, selection)
        blocks = self._clips_of(EFFECT, selection)
        if video:
            self._add_effect_to_clips(video, VIDEO)
        elif audio:
            self._add_effect_to_clips(audio, AUDIO)
        elif len(blocks) == 1:
            self._edit_effect(blocks[0], blocks[0].effects[0])
        else:
            self._add_effect_block(self._player.position)

    def _show_playhead_in(self, clips: list[Clip]) -> None:
        """Move the playhead inside the clips, so that the preview shows the effect."""
        if not any(clip.contains(self._player.position) for clip in clips):
            first = min(clips, key=lambda clip: clip.start)
            self._player.seek(first.start + min(0.5, first.duration / 3))

    def _subject(self, clips: list[Clip]) -> str:
        project = self._controller.project
        names = sorted({project.get_media(clip.media_id).name for clip in clips if project.get_media(clip.media_id)})
        return "Appliqué à : " + ", ".join(names)

    def _add_effect_to_clips(self, clips: list[Clip], kind: str, effect_type: str | None = None) -> None:
        clip_ids = {clip.id for clip in clips}
        values = None
        if effect_type == FADE:
            values = {"fade_in": clips[0].fade_in, "fade_out": clips[0].fade_out}
        self._show_playhead_in(clips)
        EffectsDialog.run(
            self, self._player, self._controller.project, kind, self._subject(clips),
            preview=lambda project, effect, params: editing.add_effect(project, clip_ids, effect, params),
            commit=lambda effect, params: self._controller.add_effect(clip_ids, effect, params),
            effect_type=effect_type, values=values)

    def _add_effect_block(self, start: float) -> None:
        subject = (f"Ajouté sur la piste d'effets à {format_time(start)}, pour "
                   f"{editing.DEFAULT_EFFECT_BLOCK_DURATION:.0f} s (tirez ses bords pour changer sa durée). "
                   "Il s'applique à toute l'image.")
        self._player.seek(start)
        EffectsDialog.run(
            self, self._player, self._controller.project, VIDEO, subject,
            preview=lambda project, effect, params: editing.add_effect_block(project, start, effect, params),
            commit=lambda effect, params: self._controller.add_effect_block(start, effect, params))

    def _edit_effect(self, clip: Clip, effect: EffectInstance) -> None:
        plugin = get_effect(effect.type)
        if plugin is None:
            self._controller.message.emit("Cet effet n'est pas disponible dans cette version d'Edison.")
            return
        self._show_playhead_in([clip])
        subject = "Bloc de la piste d'effets" if clip.is_effect_block else self._subject([clip])
        clip_id, effect_id = clip.id, effect.id
        EffectsDialog.run(
            self, self._player, self._controller.project, plugin.kind, subject,
            preview=lambda project, _effect, params: editing.update_effect(project, clip_id, effect_id, params),
            commit=lambda _effect, params: self._controller.update_effect(clip_id, effect_id, params),
            effect_type=effect.type, values=effect.params, edit_mode=True)

    def _on_clip_double_clicked(self, clip_id: str) -> None:
        found = self._controller.project.find_clip(clip_id)
        if found and found[1].is_effect_block and found[1].effects:
            self._edit_effect(found[1], found[1].effects[0])

    # ---------------------------------------------------------- context menus
    def _show_clip_menu(self, clip_id: str, position: QPoint) -> None:
        project = self._controller.project
        found = project.find_clip(clip_id)
        if found is None:
            return
        track, clip = found
        selection = set(self._controller.selected_clips)
        menu = QMenu(self)
        if track.kind == EFFECT:
            menu.addAction(icons.icon("sparkles", size=16), "Modifier l'effet…",
                           lambda: self._edit_effect(clip, clip.effects[0]))
            menu.addAction(icons.icon("copy", size=16), "Dupliquer", lambda: self._controller.duplicate_clips(selection))
        elif track.kind == VIDEO:
            split = menu.addAction(icons.icon("unlink", size=16), "Séparer l'audio et la vidéo",
                                   lambda: self._controller.unlink_clip(clip_id))
            split.setEnabled(bool(project.linked_clips(clip)))
            clips = self._clips_of(VIDEO, selection) or [clip]
            menu.addAction(icons.icon("sparkles", size=16), "Effet…", lambda: self._add_effect_to_clips(clips, VIDEO))
            self._add_applied_effects_menu(menu, clip)
            menu.addAction(icons.icon("copy", size=16), "Dupliquer", lambda: self._controller.duplicate_clips(selection))
        else:
            clips = self._clips_of(AUDIO, selection) or [clip]
            menu.addAction(icons.icon("volume", size=16), "Volume…", lambda: self._edit_volume(clip, selection))
            menu.addAction(icons.icon("sparkles", size=16), "Effet…", lambda: self._add_effect_to_clips(clips, AUDIO))
            self._add_applied_effects_menu(menu, clip)
            menu.addAction(icons.icon("fade", size=16), "Fondu entrant / sortant…",
                           lambda: self._add_effect_to_clips([clip], AUDIO, FADE))
        menu.addSeparator()
        menu.addAction(icons.icon("trash", size=16), "Supprimer", self._controller.delete_selection)
        menu.exec(position)

    def _add_applied_effects_menu(self, menu: QMenu, clip: Clip) -> None:
        """"Effets appliqués" sub-menu: modify or remove each effect of the clip."""
        submenu = menu.addMenu(icons.icon("sparkles", size=16), "Effets appliqués")
        effects = [(effect, get_effect(effect.type)) for effect in clip.effects]
        for effect, plugin in effects:
            label = plugin.label if plugin else f"Effet inconnu ({effect.type})"
            entry = submenu.addMenu(label)
            modify = entry.addAction("Modifier…", lambda e=effect: self._edit_effect(clip, e))
            modify.setEnabled(plugin is not None)
            entry.addAction(icons.icon("trash", size=16), "Retirer",
                            lambda e=effect: self._controller.remove_effect(clip.id, e.id))
        if not effects:
            submenu.addAction("Aucun effet appliqué").setEnabled(False)

    def _edit_volume(self, clip: Clip, selection: set) -> None:
        volume = VolumeDialog.ask(self, clip.volume)
        if volume is not None:
            audio_ids = {c.id for c in self._clips_of(AUDIO, selection)}
            self._controller.set_volume(audio_ids or {clip.id}, volume)

    def _show_lane_menu(self, track_id: str, time: float, position: QPoint) -> None:
        track = self._controller.project.get_track(track_id)
        if track is None or track.kind != EFFECT:
            return
        menu = QMenu(self)
        menu.addAction(icons.icon("sparkles", size=16), "Ajouter un effet ici…", lambda: self._add_effect_block(time))
        menu.exec(position)

    def _show_track_menu(self, track_id: str, position: QPoint) -> None:
        track = self._controller.project.get_track(track_id)
        menu = QMenu(self)
        remove = menu.addAction(icons.icon("trash", size=16), f"Supprimer la piste « {track.name} »",
                                lambda: self._controller.remove_track(track_id))
        can_remove = not track.clips and len(self._controller.project.tracks_of(track.kind)) > 1
        remove.setEnabled(can_remove)
        if not can_remove:
            menu.addAction("Seule une piste vide peut être supprimée").setEnabled(False)
        menu.exec(position)
