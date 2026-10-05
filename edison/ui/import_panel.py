"""Import tab (CDC "Onglet Import"): library of the imported media.

Ready: sort text (top left), type filter (top right), grid of tiles with the "+"
tile at the beginning or at the end, file dialog, files dropped from the explorer,
error message listing the accepted formats.

To do: the import itself (``ProjectController.import_files``, S2), the thumbnails
(S2), the waveform of the audio tiles (S4), the drag to the timeline (S3).
"""

import os

from PySide6.QtCore import QMimeData, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu, QMessageBox,
                               QPushButton, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget)

from edison.config import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS
from edison.media.probe import accepted_formats_text
from edison.model.project import AUDIO, VIDEO
from edison.ui import icons, theme
from edison.ui.painting import draw_cover, draw_pixmap, rounded, to_qimage
from edison.ui.widgets import ComboBox
from edison.utils import format_time

MEDIA_MIME = "application/x-edison-media"  # drag and drop of a tile: the data is the media id
ADD_ITEM = "__add__"  # identifier of the "+" tile

SORT_OPTIONS = {  # key: (short text of the button, text of the menu)
    "recent": ("Plus récents", "Imports les plus récents en premier"),
    "oldest": ("Plus anciens", "Imports les plus anciens en premier"),
    "az": ("A-Z", "A-Z"),
    "za": ("Z-A", "Z-A"),
}
FILTER_OPTIONS = {"all": "Tout", VIDEO: "Vidéo", AUDIO: "Audio"}

TILE_SIZE = QSize(150, 132)
THUMB_HEIGHT = 84


class _MediaDelegate(QStyledItemDelegate):
    """Draws a tile: thumbnail, name and duration of a media, or the "+" tile."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._pixmaps: dict[str, QPixmap] = {}  # thumbnails converted once, not at each paint

    def clear_cache(self) -> None:
        self._pixmaps.clear()

    def sizeHint(self, _option, _index) -> QSize:
        return TILE_SIZE

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(option.rect).adjusted(5, 5, -5, -5)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        media_id = index.data(Qt.ItemDataRole.UserRole)
        if media_id == ADD_ITEM:
            self._paint_add_tile(painter, rect, hovered)
        elif self._controller.project is not None:
            media = self._controller.project.get_media(media_id)
            if media is not None:
                self._paint_media_tile(painter, rect, media, hovered, selected)
        painter.restore()

    def _paint_add_tile(self, painter, rect, hovered) -> None:
        tile = QRectF(rect.x(), rect.y(), rect.width(), THUMB_HEIGHT + 30)
        painter.fillPath(rounded(tile, 10), QColor("#ecff5c" if hovered else theme.ACCENT))
        size = 30
        draw_pixmap(painter, QRectF(tile.center().x() - size / 2, tile.center().y() - size / 2 - 8, size, size),
                    icons.pixmap("plus", theme.INK, size))
        painter.setPen(QColor(theme.INK))
        font = QFont(painter.font())
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(tile.adjusted(0, 0, 0, -12), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                         "Importer")

    def _paint_media_tile(self, painter, rect, media, hovered, selected) -> None:
        thumb = QRectF(rect.x(), rect.y(), rect.width(), THUMB_HEIGHT)
        path = rounded(thumb, 8)
        painter.fillPath(path, QColor(theme.SURFACE_ALT))
        preview = self._controller.previews.get(media.id)
        if media.kind == VIDEO and preview is not None:
            painter.save()
            painter.setClipPath(path)
            draw_cover(painter, thumb, self._video_pixmap(media.id, preview))
            painter.restore()
        # TODO(S4): for an audio media, draw its waveform (``waveform_peaks``) instead of the icon.
        badge = QRectF(thumb.right() - 28, thumb.bottom() - 28, 22, 22)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.PRIMARY))
        painter.drawEllipse(badge)
        draw_pixmap(painter, badge.adjusted(5, 5, -5, -5),
                    icons.pixmap("play" if media.kind == VIDEO else "audio", theme.TEXT, 12))
        if selected or hovered:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(theme.ACCENT if selected else theme.PRIMARY_LIGHT), 2))
            painter.drawPath(path)
        font = QFont(painter.font())
        font.setPointSizeF(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(theme.TEXT))
        name_rect = QRectF(rect.x() + 2, thumb.bottom() + 6, rect.width() - 4, 18)
        name = painter.fontMetrics().elidedText(media.name, Qt.TextElideMode.ElideMiddle, int(name_rect.width()))
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(theme.TEXT_MUTED))
        painter.drawText(name_rect.translated(0, 17), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         format_time(media.duration, precise=False))

    def _video_pixmap(self, media_id, preview) -> QPixmap:
        if media_id not in self._pixmaps:
            self._pixmaps[media_id] = QPixmap.fromImage(to_qimage(preview))
        return self._pixmaps[media_id]


class _MediaList(QListWidget):
    """Grid of tiles. Tiles can be dragged (to the timeline); files can be dropped from the explorer."""

    files_dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setMovement(QListWidget.Movement.Static)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setWrapping(True)
        self.setGridSize(TILE_SIZE)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setMouseTracking(True)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)

    def mimeTypes(self):
        return [MEDIA_MIME]

    def mimeData(self, items):
        """Data of a dragged tile: the media id. The timeline reads it in its ``dropEvent`` (TODO(S3))."""
        data = QMimeData()
        ids = [item.data(Qt.ItemDataRole.UserRole) for item in items]
        ids = [media_id for media_id in ids if media_id != ADD_ITEM]
        if ids:
            data.setData(MEDIA_MIME, ids[0].encode())
        return data

    def startDrag(self, _actions):
        item = self.currentItem()
        if item is not None and item.data(Qt.ItemDataRole.UserRole) != ADD_ITEM:
            super().startDrag(Qt.DropAction.CopyAction)

    # Files dragged from the file explorer
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()


class ImportPanel(QWidget):
    """Import tab."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self._controller = controller
        self._sort = "recent"
        self._last_folder = ""

        title = QLabel("MÉDIAS")
        title.setObjectName("SectionLabel")
        self._count = QLabel()
        self._count.setObjectName("Muted")
        header = QHBoxLayout()
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self._count)

        # Top left: clickable text showing the sort order. Top right: type filter.
        self._sort_button = QPushButton()
        self._sort_button.setObjectName("Link")
        self._sort_button.setIcon(icons.icon("sort", theme.TEXT_MUTED, 16))
        self._sort_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sort_button.setToolTip("Changer l'ordre de tri")
        self._sort_button.setMenu(self._build_sort_menu())
        self._filter = ComboBox()
        for key, label in FILTER_OPTIONS.items():
            self._filter.addItem(label, key)
        self._filter.setToolTip("Type de médias affichés")
        self._filter.currentIndexChanged.connect(self.refresh)
        controls = QHBoxLayout()
        controls.addWidget(self._sort_button)
        controls.addStretch()
        controls.addWidget(self._filter)

        self._delegate = _MediaDelegate(controller, self)
        self._list = _MediaList()
        self._list.setItemDelegate(self._delegate)
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._list.files_dropped.connect(controller.import_files)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_context_menu)

        hint = QLabel("Glissez un média sur la trame ou double-cliquez dessus.")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(header)
        layout.addLayout(controls)
        layout.addWidget(self._list, 1)
        layout.addWidget(hint)

        controller.media_changed.connect(self.refresh)
        controller.import_errors.connect(self._show_import_errors)
        self._update_sort_label()
        self.refresh()

    # ----------------------------------------------------------- sort, filter
    def _build_sort_menu(self) -> QMenu:
        menu = QMenu(self)
        group = QActionGroup(menu)
        for key, (_, label) in SORT_OPTIONS.items():
            action = QAction(label, menu, checkable=True, checked=key == self._sort)
            action.triggered.connect(lambda _checked, k=key: self._set_sort(k))
            group.addAction(action)
            menu.addAction(action)
        return menu

    def _set_sort(self, key: str) -> None:
        self._sort = key
        self._update_sort_label()
        self.refresh()

    def _update_sort_label(self) -> None:
        self._sort_button.setText(f"Tri : {SORT_OPTIONS[self._sort][0]}")

    def _sorted_media(self) -> list:
        project = self._controller.project
        if project is None:
            return []
        kind = self._filter.currentData()
        media = [m for m in project.media if kind == "all" or m.kind == kind]
        if self._sort in ("az", "za"):
            return sorted(media, key=lambda m: m.name.lower(), reverse=self._sort == "za")
        return sorted(media, key=lambda m: m.imported_at, reverse=self._sort == "recent")

    def refresh(self) -> None:
        """Rebuild the grid from the library of the project (``media_changed``)."""
        self._delegate.clear_cache()
        self._list.clear()
        add_item = QListWidgetItem()
        add_item.setData(Qt.ItemDataRole.UserRole, ADD_ITEM)
        add_item.setToolTip("Importer des vidéos ou des audios")
        add_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        # CDC: the "+" tile is first in "Imports les plus récents en premier" mode, last otherwise.
        if self._sort == "recent":
            self._list.addItem(add_item)
        for media in self._sorted_media():
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, media.id)
            item.setToolTip(f"{media.name}\n{format_time(media.duration)}")
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled)
            self._list.addItem(item)
        if self._sort != "recent":
            self._list.addItem(add_item)
        total = len(self._controller.project.media) if self._controller.project else 0
        self._count.setText(f"{total} élément{'s' if total > 1 else ''}")

    # ------------------------------------------------------------ interactions
    def open_file_dialog(self) -> None:
        """Choose files to import ("+" tile)."""
        patterns = " ".join(f"*{ext}" for ext in VIDEO_EXTENSIONS + AUDIO_EXTENSIONS)
        filters = ";;".join([
            f"Médias ({patterns})",
            f"Vidéos ({' '.join('*' + e for e in VIDEO_EXTENSIONS)})",
            f"Audios ({' '.join('*' + e for e in AUDIO_EXTENSIONS)})",
            "Tous les fichiers (*)",  # lets the user pick a refused file: the error message lists the formats
        ])
        paths, _ = QFileDialog.getOpenFileNames(self, "Importer des médias", self._last_folder, filters)
        if paths:
            self._last_folder = os.path.dirname(paths[0])
            self._controller.import_files(paths)

    def _on_item_clicked(self, item) -> None:
        if item.data(Qt.ItemDataRole.UserRole) == ADD_ITEM:
            self.open_file_dialog()

    def _on_item_double_clicked(self, item) -> None:
        media_id = item.data(Qt.ItemDataRole.UserRole)
        if media_id != ADD_ITEM:
            # TODO(S3): add the media at the end of the first track of its kind:
            # self._controller.add_media_clip(media_id, end_of_that_track)
            self._controller.todo("Ajouter un média à la trame", "S3")

    def _show_context_menu(self, position) -> None:
        item = self._list.itemAt(position)
        media_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        if media_id in (None, ADD_ITEM):
            return
        menu = QMenu(self)
        remove = menu.addAction(icons.icon("trash", size=16), "Retirer du projet")
        remove.triggered.connect(lambda: self._controller.remove_media(media_id))
        menu.exec(self._list.viewport().mapToGlobal(position))

    def _show_import_errors(self, errors: list) -> None:
        """CDC: a refused file gives an error message listing the accepted formats."""
        lines = "\n".join(f"• {name} : {reason}" for name, reason in errors)
        QMessageBox.warning(
            self, "Import impossible",
            f"Certains fichiers n'ont pas pu être importés :\n\n{lines}\n\nFormats acceptés :\n{accepted_formats_text()}",
        )
