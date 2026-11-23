"""Home page: carousel of projects, the first card creates a new project."""

import base64
from datetime import datetime

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractButton, QHBoxLayout, QLabel, QMenu, QPushButton, QScrollArea, QToolButton,
                               QVBoxLayout, QWidget)

from edison.config import ASSETS_DIR
from edison.controller.recent import ProjectSummary, list_projects
from edison.ui import icons, theme
from edison.ui.painting import draw_cover, draw_pixmap, rounded

CARD_SIZE = QSize(230, 196)
THUMB_HEIGHT = 130


class _Card(QAbstractButton):
    """Clickable card with a hover effect."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(CARD_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hovered = False

    def enterEvent(self, _event):
        self._hovered = True
        self.update()

    def leaveEvent(self, _event):
        self._hovered = False
        self.update()


class _NewProjectCard(_Card):
    """Card with a "+" to create a project."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setToolTip("Créer un nouveau projet")

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        painter.fillPath(rounded(rect, 14), QColor("#ecff5c" if self._hovered else theme.ACCENT))
        size = 44
        draw_pixmap(painter, QRectF(rect.center().x() - size / 2, rect.center().y() - size / 2 - 14, size, size),
                    icons.pixmap("plus", theme.INK, size))
        font = QFont(painter.font())
        font.setPointSizeF(11)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(theme.INK))
        painter.drawText(rect.adjusted(0, 0, 0, -30), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                         "Nouveau projet")


class _ProjectCard(_Card):
    """Card showing a saved project: thumbnail, name and date.

    A trash button appears on hover; the right click also offers to delete the project.
    """

    delete_requested = Signal()

    def __init__(self, summary: ProjectSummary, mascot: QPixmap, parent=None):
        super().__init__(parent)
        self.summary = summary
        self.setToolTip(summary.path)
        self._mascot = mascot
        self._thumbnail = QPixmap()
        if summary.thumbnail:
            self._thumbnail.loadFromData(base64.b64decode(summary.thumbnail))
        self._delete = QToolButton(self)
        self._delete.setObjectName("CardDelete")
        self._delete.setIcon(icons.icon("trash", size=16))
        self._delete.setToolTip("Supprimer le projet")
        self._delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self._delete.setGeometry(CARD_SIZE.width() - 42, 10, 30, 30)
        self._delete.clicked.connect(self.delete_requested)
        self._delete.hide()

    def enterEvent(self, event):
        super().enterEvent(event)
        self._delete.show()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._delete.hide()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.addAction(icons.icon("folder", size=16), "Ouvrir", self.click)
        menu.addSeparator()
        menu.addAction(icons.icon("trash", size=16), "Supprimer le projet…", self.delete_requested.emit)
        menu.exec(event.globalPos())

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        card = rounded(rect, 14)
        painter.fillPath(card, QColor(theme.SURFACE_ALT if self._hovered else theme.SURFACE))
        thumb = QRectF(rect.x(), rect.y(), rect.width(), THUMB_HEIGHT)
        painter.save()
        painter.setClipPath(card)
        if self._thumbnail.isNull():
            gradient = QLinearGradient(thumb.topLeft(), thumb.bottomRight())
            gradient.setColorAt(0, QColor(theme.PRIMARY))
            gradient.setColorAt(1, QColor("#241a45"))
            painter.fillRect(thumb, gradient)
            height = thumb.height() * 0.7
            width = height * self._mascot.width() / max(1, self._mascot.height())
            draw_pixmap(painter, QRectF(thumb.center().x() - width / 2, thumb.center().y() - height / 2, width, height),
                        self._mascot)
        else:
            draw_cover(painter, thumb, self._thumbnail)
        painter.restore()
        font = QFont(painter.font())
        font.setPointSizeF(10.5)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(theme.TEXT))
        text = rect.adjusted(12, THUMB_HEIGHT + 10, -12, 0)
        name = painter.fontMetrics().elidedText(self.summary.name, Qt.TextElideMode.ElideRight, int(text.width()))
        painter.drawText(text, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, name)
        font.setBold(False)
        font.setPointSizeF(9)
        painter.setFont(font)
        painter.setPen(QColor(theme.TEXT_MUTED))
        date = datetime.fromtimestamp(self.summary.saved_at).strftime("Modifié le %d/%m/%Y à %H:%M")
        painter.drawText(text.adjusted(0, 22, 0, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, date)
        if self._hovered:
            painter.setPen(QPen(QColor(theme.PRIMARY_LIGHT), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(card)


class _Carousel(QScrollArea):
    """Horizontal scroll area; the mouse wheel scrolls horizontally."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFixedHeight(CARD_SIZE.height() + 18)
        self.viewport().setAutoFillBackground(False)
        self.content = QWidget()
        self.content.setObjectName("Transparent")
        self.row = QHBoxLayout(self.content)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(16)
        self.setWidget(self.content)

    def wheelEvent(self, event):
        bar = self.horizontalScrollBar()
        bar.setValue(bar.value() - (event.angleDelta().y() or event.angleDelta().x()))
        event.accept()


class HomePage(QWidget):
    """Home page of the application."""

    new_project_requested = Signal()
    open_project_requested = Signal(str)
    delete_project_requested = Signal(str, str)  # path, name
    browse_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self._mascot = QPixmap(str(ASSETS_DIR / "mascot_headphones.png"))

        waving = QLabel()
        waving.setPixmap(QPixmap(str(ASSETS_DIR / "mascot_waving.png")).scaledToHeight(
            150, Qt.TransformationMode.SmoothTransformation))
        title = QLabel("Bienvenue dans Edison")
        title.setObjectName("HeroTitle")
        subtitle = QLabel("Créez un nouveau projet ou reprenez un montage en cours.")
        subtitle.setObjectName("Muted")
        texts = QVBoxLayout()
        texts.addStretch()
        texts.addWidget(title)
        texts.addWidget(subtitle)
        texts.addStretch()
        hero = QHBoxLayout()
        hero.setSpacing(24)
        hero.addWidget(waving)
        hero.addLayout(texts)
        hero.addStretch()

        section = QLabel("Mes projets")
        section.setObjectName("SectionTitle")
        browse = QPushButton("Ouvrir un fichier…")
        browse.setIcon(icons.icon("folder", size=16))
        browse.clicked.connect(self.browse_requested)
        section_row = QHBoxLayout()
        section_row.addWidget(section)
        section_row.addStretch()
        section_row.addWidget(browse)

        self._carousel = _Carousel()
        self._empty = QLabel("Aucun projet pour l'instant : cliquez sur « Nouveau projet » pour commencer.")
        self._empty.setObjectName("Muted")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(56, 40, 56, 40)
        layout.setSpacing(20)
        layout.addLayout(hero)
        layout.addSpacing(10)
        layout.addLayout(section_row)
        layout.addWidget(self._carousel)
        layout.addWidget(self._empty)
        layout.addStretch()

    def refresh(self) -> None:
        """Reload the list of projects."""
        row = self._carousel.row
        while row.count():
            widget = row.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        new_card = _NewProjectCard()
        new_card.clicked.connect(self.new_project_requested)
        row.addWidget(new_card)
        summaries = list_projects()
        for summary in summaries:
            card = _ProjectCard(summary, self._mascot)
            card.clicked.connect(lambda _checked=False, path=summary.path: self.open_project_requested.emit(path))
            card.delete_requested.connect(
                lambda path=summary.path, name=summary.name: self.delete_project_requested.emit(path, name))
            row.addWidget(card)
        row.addStretch()
        self._empty.setVisible(not summaries)
