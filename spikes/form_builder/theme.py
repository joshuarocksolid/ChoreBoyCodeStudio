"""Design tokens, the chrome style sheet, and the runtime palette for the canvas.

The chrome style sheet is set on builder windows, never on the application, so
widgets on the canvas look like the shipped app and not like the builder.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory


@dataclass(frozen=True)
class Tokens:
    name: str
    dark: bool
    bg: str
    surface: str
    surface_alt: str
    canvas: str
    dots: str
    border: str
    border_strong: str
    text: str
    muted: str
    faint: str
    accent: str
    accent_hover: str
    accent_soft: str
    on_accent: str
    layout: str
    gap: str
    tab: str
    on_tab: str
    buddy: str
    warn: str
    danger: str
    ok: str
    focus: int = 1

    # Older call sites used these names.
    @property
    def window(self) -> str:
        return self.bg

    @property
    def panel(self) -> str:
        return self.surface

    @property
    def page(self) -> str:
        return self.surface

    @property
    def accent_text(self) -> str:
        return self.on_accent


THEMES = {
    "light": Tokens(
        "light", False,
        bg="#F5F6F8", surface="#FFFFFF", surface_alt="#F0F2F5", canvas="#E9EBEF", dots="#C6CCD5",
        border="#E2E5EA", border_strong="#CBD1D9", text="#16181D", muted="#5C6370", faint="#8C93A0",
        accent="#3D6BF0", accent_hover="#2F5BDB", accent_soft="#E7EDFE", on_accent="#FFFFFF",
        layout="#8B5CF6", gap="#E0418F", tab="#F59E0B", on_tab="#1F1300", buddy="#0E9F77",
        warn="#B86E00", danger="#D23B3B", ok="#16884A",
    ),
    "dark": Tokens(
        "dark", True,
        bg="#141619", surface="#1C1F24", surface_alt="#252930", canvas="#101215", dots="#262A31",
        border="#2A2E36", border_strong="#3A3F49", text="#ECEEF2", muted="#A2A9B6", faint="#6C7380",
        accent="#6F96FF", accent_hover="#8AAAFF", accent_soft="#1F2C4A", on_accent="#0B1020",
        layout="#A78BFA", gap="#F472B6", tab="#FBBF24", on_tab="#1F1300", buddy="#34D399",
        warn="#F0B44C", danger="#FF7A7A", ok="#4ADE80",
    ),
    "hc-light": Tokens(
        "hc-light", False,
        bg="#FFFFFF", surface="#FFFFFF", surface_alt="#F0F0F0", canvas="#E6E6E6", dots="#B0B0B0",
        border="#000000", border_strong="#000000", text="#000000", muted="#1A1A1A", faint="#3A3A3A",
        accent="#0030C0", accent_hover="#00208A", accent_soft="#DDE4FF", on_accent="#FFFFFF",
        layout="#5B00B0", gap="#B0005A", tab="#8A5000", on_tab="#FFFFFF", buddy="#006B4A",
        warn="#7A4A00", danger="#A00000", ok="#00661F", focus=2,
    ),
    "hc-dark": Tokens(
        "hc-dark", True,
        bg="#000000", surface="#000000", surface_alt="#1A1A1A", canvas="#0A0A0A", dots="#3A3A3A",
        border="#FFFFFF", border_strong="#FFFFFF", text="#FFFFFF", muted="#F0F0F0", faint="#C8C8C8",
        accent="#FFE14A", accent_hover="#FFEA80", accent_soft="#333000", on_accent="#000000",
        layout="#D0B0FF", gap="#FF8AC8", tab="#FFB000", on_tab="#000000", buddy="#5CFFC0",
        warn="#FFC060", danger="#FF9090", ok="#7CFF9C", focus=2,
    ),
}

# Type scale in pixels.
TYPE = {"overline": 10.5, "small": 12, "body": 13, "title": 15, "heading": 22, "hero": 30}


def tokens_for(name: str) -> Tokens:
    return THEMES.get(name, THEMES["light"])


_CURRENT = [THEMES["light"]]


def current() -> Tokens:
    """The tokens the chrome is drawn with right now (custom painters read this)."""
    return _CURRENT[0]


def system_theme(app: QApplication) -> str:
    scheme = app.styleHints().colorScheme()
    return "dark" if scheme == Qt.ColorScheme.Dark else "light"


detect_theme = system_theme


def ensure_style(app: QApplication) -> None:
    """Fusion everywhere, so the builder and the ChoreBoy runtime draw the same."""
    if app.style().objectName().lower() != "fusion":
        app.setStyle(QStyleFactory.create("Fusion"))
    from PySide6.QtGui import QFontDatabase

    families = set(QFontDatabase.families())
    if app.font().family() not in families:
        # Offscreen runs report a "Sans Serif" family that does not exist, and resolving
        # it makes Qt scan every font alias (~0.5 s). Use a real UI family instead.
        for name in ("DejaVu Sans", "Noto Sans", "Cantarell", "Helvetica Neue", "Helvetica", "Arial", "Liberation Sans"):
            if name in families:
                app.setFont(QFont(name, 11))
                break


def chrome_palette(tokens: Tokens) -> QPalette:
    palette = QPalette()
    roles = {
        QPalette.Window: tokens.bg,
        QPalette.WindowText: tokens.text,
        QPalette.Base: tokens.surface,
        QPalette.AlternateBase: tokens.surface_alt,
        QPalette.Text: tokens.text,
        QPalette.Button: tokens.surface,
        QPalette.ButtonText: tokens.text,
        QPalette.Highlight: tokens.accent,
        QPalette.HighlightedText: tokens.on_accent,
        QPalette.PlaceholderText: tokens.faint,
        QPalette.ToolTipBase: tokens.surface,
        QPalette.ToolTipText: tokens.text,
        QPalette.Mid: tokens.border_strong,
        QPalette.Midlight: tokens.border,
        QPalette.Dark: tokens.border_strong,
        QPalette.Light: tokens.surface,
        QPalette.Shadow: "#000000",
        QPalette.Link: tokens.accent,
        QPalette.BrightText: tokens.danger,
    }
    for role, value in roles.items():
        palette.setColor(role, QColor(value))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor(tokens.faint))
    return palette


_RUNTIME: list = []


def runtime_palette() -> QPalette:
    """What a stock PySide6 app on ChoreBoy draws with: Fusion's light palette."""
    if not _RUNTIME:
        style = QStyleFactory.create("Fusion")
        _RUNTIME.append(QPalette(style.standardPalette()))
    return QPalette(_RUNTIME[0])


def runtime_font(point_size: float = 0) -> QFont:
    font = QFont(QApplication.font())
    if point_size:
        font.setPointSizeF(point_size)
    return font


def apply_theme(app: QApplication, name: str, windows=()) -> Tokens:
    """Apply the chrome palette to the app and the style sheet to builder windows."""
    ensure_style(app)
    tokens = tokens_for(name)
    _CURRENT[0] = tokens
    app.setPalette(chrome_palette(tokens))
    sheet = chrome_qss(tokens)
    for window in windows:
        window.setStyleSheet(sheet)
    return tokens


def chrome_qss(t: Tokens) -> str:
    from spikes.form_builder.icons import qss_asset

    chevron = qss_asset("chevron-down", t.muted)
    check = qss_asset("check-mark", t.on_accent)
    f = t.focus
    return f"""
    * {{ font-size: 13px; }}
    QMainWindow, QDialog {{ background: {t.bg}; color: {t.text}; }}
    QWidget#Panel, QWidget#InspectorBody {{ background: {t.surface}; color: {t.text}; }}
    QWidget#StartScreen {{ background: {t.bg}; }}
    QWidget#TopBar {{ background: {t.surface}; border-bottom: 1px solid {t.border}; }}
    QFrame#Hairline {{ background: {t.border}; max-height: 1px; min-height: 1px; border: none; }}
    QFrame#VHairline {{ background: {t.border}; max-width: 1px; min-width: 1px; border: none; }}

    QLabel {{ color: {t.text}; background: transparent; }}
    QLabel#Overline {{ color: {t.faint}; font-size: 10.5px; font-weight: 600; letter-spacing: 0.6px; }}
    QLabel#Muted {{ color: {t.muted}; }}
    QLabel#Faint {{ color: {t.faint}; font-size: 12px; }}
    QLabel#Small {{ color: {t.muted}; font-size: 12px; }}
    QLabel#Title {{ font-size: 15px; font-weight: 600; }}
    QLabel#Heading {{ font-size: 22px; font-weight: 650; }}
    QLabel#Hero {{ font-size: 30px; font-weight: 700; }}
    QLabel#FileName {{ font-weight: 600; }}
    QLabel#Why {{ color: {t.muted}; font-size: 12px; background: {t.surface_alt};
        border-radius: 8px; padding: 8px 10px; }}
    QLabel#Warn {{ color: {t.warn}; font-size: 12px; }}
    QLabel#Danger {{ color: {t.danger}; font-size: 12px; }}
    QLabel#Kbd {{ color: {t.muted}; background: {t.surface_alt}; border: 1px solid {t.border};
        border-radius: 4px; padding: 0px 5px; font-size: 11px; }}

    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{
        background: {t.surface}; color: {t.text};
        border: 1px solid {t.border_strong}; border-radius: 6px;
        padding: 3px 8px; min-height: 20px;
        selection-background-color: {t.accent}; selection-color: {t.on_accent};
    }}
    QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: {t.faint}; }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {{
        border: {f + 1}px solid {t.accent}; padding: {3 - f}px {8 - f}px;
    }}
    QLineEdit:disabled, QSpinBox:disabled {{ color: {t.faint}; background: {t.surface_alt}; }}
    QLineEdit#NameField {{ font-size: 15px; font-weight: 600; border: 1px solid transparent;
        background: transparent; padding: 2px 4px; }}
    QLineEdit#NameField:hover {{ border-color: {t.border_strong}; }}
    QLineEdit#NameField:focus {{ border: {f + 1}px solid {t.accent}; background: {t.surface}; }}
    QLineEdit#Search {{ background: {t.surface_alt}; border: 1px solid transparent; }}
    QLineEdit#Search:focus {{ background: {t.surface}; border: {f + 1}px solid {t.accent}; }}
    QSpinBox, QDoubleSpinBox {{ padding-right: 6px; }}
    QComboBox {{ padding-right: 22px; }}
    QComboBox::drop-down {{ border: none; width: 20px; subcontrol-position: center right; }}
    QComboBox::down-arrow {{ image: url("{chevron}"); width: 12px; height: 12px; }}
    QComboBox QAbstractItemView {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border_strong};
        padding: 4px; outline: none; selection-background-color: {t.accent_soft}; selection-color: {t.text}; }}

    QCheckBox {{ color: {t.text}; spacing: 8px; background: transparent; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {t.border_strong};
        border-radius: 4px; background: {t.surface}; }}
    QCheckBox::indicator:hover {{ border-color: {t.accent}; }}
    QCheckBox::indicator:checked {{ background: {t.accent}; border-color: {t.accent}; image: url("{check}"); }}

    QPushButton {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border_strong};
        border-radius: 6px; padding: 5px 12px; min-height: 18px; }}
    QPushButton:hover {{ background: {t.surface_alt}; }}
    QPushButton:pressed {{ background: {t.border}; }}
    QPushButton:disabled {{ color: {t.faint}; border-color: {t.border}; }}
    QPushButton:focus {{ border: {f}px solid {t.accent}; }}
    QPushButton#Primary {{ background: {t.accent}; color: {t.on_accent}; border: 1px solid {t.accent}; font-weight: 600; }}
    QPushButton#Primary:hover {{ background: {t.accent_hover}; border-color: {t.accent_hover}; }}
    QPushButton#Primary:disabled {{ background: {t.border}; border-color: {t.border}; color: {t.faint}; }}
    QPushButton#Ghost {{ background: transparent; border: 1px solid transparent; color: {t.muted}; }}
    QPushButton#Ghost:hover {{ background: {t.surface_alt}; color: {t.text}; }}
    QPushButton#Link {{ background: transparent; border: none; color: {t.accent}; padding: 2px 0; text-align: left; }}
    QPushButton#Link:hover {{ text-decoration: underline; }}

    QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 6px;
        color: {t.text}; padding: 4px; }}
    QToolButton:hover {{ background: {t.surface_alt}; }}
    QToolButton:pressed, QToolButton:checked {{ background: {t.accent_soft}; color: {t.accent}; }}
    QToolButton#TextTool {{ padding: 4px 8px; color: {t.muted}; }}
    QToolButton#TextTool:hover {{ color: {t.text}; }}
    QToolButton#TextTool:checked {{ color: {t.accent}; }}

    QTreeView, QListView, QTableView {{ background: {t.surface}; color: {t.text}; border: none; outline: none;
        selection-background-color: {t.accent_soft}; selection-color: {t.text}; }}
    QTreeView::item, QListView::item {{ min-height: 26px; }}
    QTreeView::branch {{ background: transparent; }}
    QHeaderView::section {{ background: {t.surface}; color: {t.faint}; border: none;
        border-bottom: 1px solid {t.border}; padding: 4px 8px; font-size: 11px; font-weight: 600; }}
    QTableView {{ gridline-color: {t.border}; }}
    QTableView::item:selected {{ background: {t.accent_soft}; color: {t.text}; }}

    QTabBar {{ background: transparent; }}
    QTabBar::tab {{ background: transparent; color: {t.muted}; padding: 8px 10px 7px 10px; margin-right: 2px;
        border: none; border-bottom: 2px solid transparent; font-weight: 500; }}
    QTabBar::tab:hover {{ color: {t.text}; }}
    QTabBar::tab:selected {{ color: {t.text}; border-bottom: 2px solid {t.accent}; font-weight: 600; }}
    QTabWidget::pane {{ border: none; border-top: 1px solid {t.border}; top: -1px; }}

    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle {{ background: {t.border_strong}; border-radius: 3px; min-height: 24px; min-width: 24px; }}
    QScrollBar::handle:hover {{ background: {t.faint}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    QSplitter::handle {{ background: {t.border}; }}
    QSplitter::handle:horizontal {{ width: 1px; }}
    QSplitter::handle:vertical {{ height: 1px; }}
    QSplitter::handle:hover {{ background: {t.accent}; }}

    QMenuBar {{ background: {t.surface}; color: {t.text}; border-bottom: 1px solid {t.border}; }}
    QMenuBar::item {{ padding: 4px 10px; background: transparent; border-radius: 4px; }}
    QMenuBar::item:selected {{ background: {t.surface_alt}; }}
    QMenu {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border_strong}; padding: 4px; }}
    QMenu::item {{ padding: 6px 28px 6px 12px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {t.accent_soft}; color: {t.text}; }}
    QMenu::item:disabled {{ color: {t.faint}; }}
    QMenu::separator {{ height: 1px; background: {t.border}; margin: 4px 6px; }}
    QMenu::icon {{ padding-left: 8px; }}

    QStatusBar {{ background: {t.surface}; color: {t.muted}; border-top: 1px solid {t.border}; min-height: 26px; }}
    QStatusBar::item {{ border: none; }}
    QStatusBar QLabel {{ color: {t.muted}; font-size: 12px; padding: 0 8px; }}

    QToolTip {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border_strong}; padding: 4px 8px; }}

    QFrame#Card {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 12px; }}
    QFrame#Card[hover="true"] {{ border: 1px solid {t.accent}; }}
    QFrame#Rail {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 12px; }}
    QFrame#Popover {{ background: {t.surface}; border: 1px solid {t.border_strong}; border-radius: 10px; }}
    """
