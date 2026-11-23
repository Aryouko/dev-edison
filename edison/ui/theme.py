"""Colours of the graphic charter and style sheet of the application."""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# Graphic charter
PRIMARY = "#5f25f8"
PRIMARY_LIGHT = "#8b3ffa"
ACCENT = "#e1f825"
CREAM = "#fcf7ef"
INK = "#1a1c06"

# Dark interface built on the charter (see maquette_finale.png)
BACKGROUND = "#121117"
SURFACE = "#1a1920"
SURFACE_ALT = "#23212b"
SURFACE_HOVER = "#2d2a37"
BORDER = "#2e2b38"
TEXT = CREAM
TEXT_MUTED = "#9b96a8"
TEXT_DISABLED = "#5b5667"
DANGER = "#ff5a76"

VIDEO_CLIP = "#5a2ee0"
VIDEO_CLIP_SELECTED = PRIMARY_LIGHT
AUDIO_CLIP = "#2c6658"
AUDIO_CLIP_SELECTED = "#3a8a76"
EFFECT_CLIP = "#8f22a8"
EFFECT_CLIP_SELECTED = "#b43bcf"
MISSING_CLIP = "#5c2633"


def apply_palette(app: QApplication) -> None:
    """Dark palette for the parts of Qt not covered by the style sheet (dialogs, menus)."""
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: SURFACE,
        QPalette.ColorRole.WindowText: TEXT,
        QPalette.ColorRole.Base: BACKGROUND,
        QPalette.ColorRole.AlternateBase: SURFACE_ALT,
        QPalette.ColorRole.Text: TEXT,
        QPalette.ColorRole.Button: SURFACE_ALT,
        QPalette.ColorRole.ButtonText: TEXT,
        QPalette.ColorRole.Highlight: PRIMARY,
        QPalette.ColorRole.HighlightedText: TEXT,
        QPalette.ColorRole.ToolTipBase: SURFACE_ALT,
        QPalette.ColorRole.ToolTipText: TEXT,
        QPalette.ColorRole.PlaceholderText: TEXT_MUTED,
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(TEXT_DISABLED))
    app.setPalette(palette)


def stylesheet() -> str:
    """Return the Qt style sheet of the application."""
    from edison.ui.icons import icon_file  # late import: icons depend on this module

    chevron = icon_file("chevron-down", TEXT_MUTED, 14)
    return f"""
    * {{ color: {TEXT}; font-family: "Segoe UI", "Inter", sans-serif; font-size: 10pt; }}
    QMainWindow, QWidget#Page {{ background: {BACKGROUND}; }}
    QWidget#Transparent {{ background: transparent; }}
    QDialog, QMessageBox {{ background: {SURFACE}; }}
    QToolTip {{ background: {SURFACE_ALT}; color: {TEXT}; border: 1px solid {BORDER}; padding: 5px 8px; }}

    QWidget#HeaderBar {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; }}
    QLabel#AppTitle {{ font-size: 13pt; font-weight: 800; letter-spacing: 1px; }}
    QLabel#Muted, QLabel#ProjectLabel {{ color: {TEXT_MUTED}; }}
    QLabel#SectionLabel {{ font-size: 9pt; font-weight: 700; letter-spacing: 1px; color: {TEXT}; }}
    QLabel#SectionTitle {{ font-size: 14pt; font-weight: 700; }}
    QLabel#HeroTitle {{ font-size: 24pt; font-weight: 800; }}
    QLabel#DialogTitle {{ font-size: 13pt; font-weight: 700; }}
    QLabel#Toast {{ background: {SURFACE_ALT}; border: 1px solid {PRIMARY_LIGHT}; border-radius: 10px;
                    padding: 10px 16px; }}
    QFrame#Panel {{ background: {SURFACE}; border-radius: 12px; }}
    QFrame#TabBar {{ background: {BACKGROUND}; border-radius: 10px; }}

    QMenuBar {{ background: transparent; }}
    QMenuBar::item {{ background: transparent; padding: 7px 16px; border-radius: 8px; font-weight: 600; }}
    QMenuBar::item:selected {{ background: {SURFACE_HOVER}; }}
    QMenu {{ background: {SURFACE_ALT}; border: 1px solid {BORDER}; padding: 6px; }}
    QMenu::item {{ padding: 7px 28px 7px 12px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {PRIMARY}; }}
    QMenu::item:disabled {{ color: {TEXT_DISABLED}; }}
    QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 8px; }}
    QMenu::icon {{ padding-left: 8px; }}

    QPushButton {{ background: {SURFACE_ALT}; border: 1px solid {BORDER}; border-radius: 8px; padding: 7px 16px; }}
    QPushButton:hover {{ background: {SURFACE_HOVER}; }}
    QPushButton:disabled {{ color: {TEXT_DISABLED}; }}
    QPushButton#Primary {{ background: {PRIMARY}; border: none; font-weight: 600; }}
    QPushButton#Primary:hover {{ background: {PRIMARY_LIGHT}; }}
    QPushButton#Primary:disabled {{ background: {SURFACE_HOVER}; color: {TEXT_DISABLED}; }}
    QPushButton#Link {{ background: transparent; border: none; padding: 4px 6px; color: {TEXT_MUTED};
                        text-align: left; }}
    QPushButton#Link:hover {{ color: {TEXT}; }}
    QPushButton#Link::menu-indicator {{ image: none; width: 0; }}
    QPushButton#Tab {{ background: transparent; border: none; border-radius: 8px; padding: 7px 20px;
                       color: {TEXT_MUTED}; font-weight: 600; }}
    QPushButton#Tab:hover {{ color: {TEXT}; }}
    QPushButton#Tab:checked {{ background: {PRIMARY}; color: {TEXT}; }}

    QToolButton {{ background: transparent; border: none; border-radius: 8px; padding: 5px; }}
    QToolButton:hover {{ background: {SURFACE_HOVER}; }}
    QToolButton#ToolbarButton {{ background: {SURFACE_ALT}; border: 1px solid {BORDER}; padding: 5px 11px; }}
    QToolButton#ToolbarButton:hover {{ background: {SURFACE_HOVER}; }}
    QToolButton#ToolbarButton:disabled {{ color: {TEXT_DISABLED}; }}
    QToolButton#ToolbarButton::menu-indicator {{ image: none; width: 0; }}
    QToolButton#CardDelete {{ background: rgba(18, 17, 23, 200); border-radius: 15px; }}
    QToolButton#CardDelete:hover {{ background: {DANGER}; }}
    QToolButton#PlayButton {{ background: {ACCENT}; border-radius: 20px; }}
    QToolButton#PlayButton:hover {{ background: #ecff5c; }}
    QToolButton#PlayButton:disabled {{ background: {SURFACE_HOVER}; }}

    QComboBox {{ background: {SURFACE_ALT}; border: 1px solid {BORDER}; border-radius: 8px; padding: 5px 10px; }}
    QComboBox:hover {{ border-color: {PRIMARY_LIGHT}; }}
    QComboBox:disabled {{ color: {TEXT_DISABLED}; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QComboBox::down-arrow {{ image: url("{chevron}"); width: 14px; height: 14px; }}
    QComboBox QAbstractItemView {{ background: {SURFACE_ALT}; border: 1px solid {BORDER}; outline: 0;
                                   selection-background-color: {PRIMARY}; padding: 4px; }}

    QLineEdit, QSpinBox, QDoubleSpinBox {{ background: {BACKGROUND}; border: 1px solid {BORDER}; border-radius: 8px;
                                          padding: 6px 10px; selection-background-color: {PRIMARY}; }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {PRIMARY_LIGHT}; }}

    QProgressBar {{ background: {BACKGROUND}; border: none; border-radius: 6px; height: 12px;
                    text-align: center; font-size: 8pt; color: {TEXT}; }}
    QProgressBar::chunk {{ background: {PRIMARY_LIGHT}; border-radius: 6px; }}

    QSlider::groove:horizontal {{ height: 4px; background: {SURFACE_HOVER}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: {ACCENT}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}
    QSlider::groove:vertical {{ width: 4px; background: {SURFACE_HOVER}; border-radius: 2px; }}
    QSlider::add-page:vertical {{ background: {ACCENT}; border-radius: 2px; }}
    QSlider::handle:vertical {{ background: {ACCENT}; width: 14px; height: 14px; margin: 0 -5px; border-radius: 7px; }}

    QScrollArea, QListWidget {{ background: transparent; border: none; outline: 0; }}
    QListWidget#EffectList {{ background: {BACKGROUND}; border-radius: 10px; padding: 6px; }}
    QListWidget#EffectList::item {{ padding: 8px 8px; border-radius: 7px; }}
    QListWidget#EffectList::item:hover {{ background: {SURFACE_HOVER}; }}
    QListWidget#EffectList::item:selected {{ background: {PRIMARY}; color: {TEXT}; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
    QScrollBar::handle {{ background: {SURFACE_HOVER}; border-radius: 5px; min-width: 30px; min-height: 30px; }}
    QScrollBar::handle:hover {{ background: #45404f; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QSplitter::handle {{ background: {BACKGROUND}; }}
    """
