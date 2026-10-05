"""Creation of the Qt application."""

import logging
import sys

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from edison.config import APP_NAME, ASSETS_DIR
from edison.ui import theme
from edison.ui.main_window import MainWindow


def create_application(argv: list[str]) -> QApplication:
    """Create the QApplication with the Edison look (graphic charter)."""
    if sys.platform == "win32":  # own icon in the Windows task bar
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("iut-vannes.edison")
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)  # used by QSettings (recent projects)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setWindowIcon(QIcon(str(ASSETS_DIR / "logo.png")))
    theme.apply_palette(app)
    app.setStyleSheet(theme.stylesheet())
    return app


def main() -> int:
    """Start Edison."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = create_application(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
