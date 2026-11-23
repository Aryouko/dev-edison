"""Drawing helpers shared by the custom painted widgets."""

import numpy as np
from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter, QPainterPath, QPixmap


def to_qimage(picture: np.ndarray) -> QImage:
    """Convert an RGB array ``(height, width, 3)`` to a QImage (copied)."""
    picture = np.ascontiguousarray(picture)
    height, width = picture.shape[:2]
    return QImage(picture.data, width, height, 3 * width, QImage.Format.Format_RGB888).copy()


def rounded(rect: QRectF, radius: float) -> QPainterPath:
    """Return a rounded rectangle path."""
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def draw_cover(painter: QPainter, rect: QRectF, pixmap: QPixmap) -> None:
    """Draw ``pixmap`` filling ``rect``, cropped to keep its aspect ratio."""
    if pixmap.isNull():
        return
    scale = max(rect.width() / pixmap.width(), rect.height() / pixmap.height())
    source_width, source_height = rect.width() / scale, rect.height() / scale
    source = QRectF((pixmap.width() - source_width) / 2, (pixmap.height() - source_height) / 2,
                    source_width, source_height)
    painter.drawPixmap(rect, pixmap, source)


def fit_rect(bounds: QRectF, width: float, height: float) -> QRectF:
    """Return the largest rectangle of aspect ``width/height`` centred in ``bounds``."""
    if width <= 0 or height <= 0:
        return QRectF(bounds)
    scale = min(bounds.width() / width, bounds.height() / height)
    fitted_width, fitted_height = width * scale, height * scale
    return QRectF(bounds.center().x() - fitted_width / 2, bounds.center().y() - fitted_height / 2,
                  fitted_width, fitted_height)


def draw_pixmap(painter: QPainter, rect: QRectF, pixmap: QPixmap) -> None:
    """Draw the whole ``pixmap`` stretched to ``rect``."""
    painter.drawPixmap(rect, pixmap, QRectF(pixmap.rect()))
