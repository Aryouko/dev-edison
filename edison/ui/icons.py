"""Line icons drawn from small SVG paths (24 x 24 grid), coloured on demand."""

import tempfile
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from edison.ui.theme import TEXT, TEXT_DISABLED

_PATHS = {
    "undo": '<path d="M9 14L4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>',
    "redo": '<path d="M15 14l5-5-5-5"/><path d="M20 9H10a6 6 0 0 0 0 12h3"/>',
    "trash": '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
    "cut": '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/>'
           '<path d="M20 4L8.1 15.9M14.5 14.5L20 20M8.1 8.1L12 12"/>',
    "merge": '<path d="M12 4v16"/><path d="M3 12h6M6 9l3 3-3 3M21 12h-6M18 9l-3 3 3 3"/>',
    "play": '<path d="M8 5v14l11-7z" fill="currentColor"/>',
    "pause": '<rect x="6" y="5" width="4" height="14" rx="1" fill="currentColor"/>'
             '<rect x="14" y="5" width="4" height="14" rx="1" fill="currentColor"/>',
    "back": '<path d="M11 7l-6 5 6 5zM19 7l-6 5 6 5z" fill="currentColor"/>',
    "forward": '<path d="M5 7l6 5-6 5zM13 7l6 5-6 5z" fill="currentColor"/>',
    "volume": '<path d="M4 9h4l5-4v14l-5-4H4z" fill="currentColor"/><path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12"/>',
    "mute": '<path d="M4 9h4l5-4v14l-5-4H4z" fill="currentColor"/><path d="M17 9l5 6M22 9l-5 6"/>',
    "fullscreen": '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "video": '<rect x="3" y="5" width="18" height="14" rx="2"/>'
             '<path d="M7 5v14M17 5v14M3 9.5h4M3 14.5h4M17 9.5h4M17 14.5h4"/>',
    "audio": '<path d="M9 18V6l11-2v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="17.5" cy="16" r="2.5"/>',
    "unlink": '<path d="M9 7H7a5 5 0 0 0 0 10h2M15 7h2a5 5 0 0 1 0 10h-2M12 3v3M12 18v3"/>',
    "copy": '<rect x="8" y="8" width="12" height="12" rx="2"/>'
            '<path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    "fade": '<path d="M3 19L9 6h6l6 13"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "chevron-down": '<path d="M6 9l6 6 6-6"/>',
    "export": '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
    "sort": '<path d="M7 4v16M3 16l4 4 4-4M17 20V4M13 8l4-4 4 4"/>',
    "import": '<path d="M12 15V4M7 9l5-5 5 5M5 20h14"/>',
    "sparkles": '<path d="M11 3l1.9 5.1L18 10l-5.1 1.9L11 17l-1.9-5.1L4 10l5.1-1.9z"/>'
                '<path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
}


def _svg(name: str, color: str) -> bytes:
    body = _PATHS[name].replace("currentColor", color)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{body}</svg>').encode()


def pixmap(name: str, color: str = TEXT, size: int = 20, ratio: float = 2.0) -> QPixmap:
    """Render an icon to a pixmap (drawn at ``ratio`` for high DPI screens)."""
    renderer = QSvgRenderer(QByteArray(_svg(name, color)))
    result = QPixmap(int(size * ratio), int(size * ratio))
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    renderer.render(painter)
    painter.end()
    result.setDevicePixelRatio(ratio)
    return result


def icon(name: str, color: str = TEXT, size: int = 20) -> QIcon:
    """Return an icon with a greyed version for disabled buttons."""
    result = QIcon()
    result.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal)
    result.addPixmap(pixmap(name, TEXT_DISABLED, size), QIcon.Mode.Disabled)
    return result


def icon_file(name: str, color: str, size: int = 16) -> str:
    """Save an icon as PNG (style sheets need a file) and return its path."""
    folder = Path(tempfile.gettempdir()) / "edison-icons"
    folder.mkdir(exist_ok=True)
    path = folder / f"{name}-{color.lstrip('#')}-{size}.png"
    if not path.exists():
        pixmap(name, color, size).save(str(path))
    return path.as_posix()
