"""Token-driven theme system for the CRUD Showcase.

Provides light and dark palettes derived from system preference, plus a
complete QSS stylesheet generator.  Modeled after the editor's own
``app.shell.theme_tokens`` but scoped to the widgets used in this example.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide2.QtGui import QPalette
from PySide2.QtWidgets import QApplication


@dataclass(frozen=True)
class ThemeTokens:
    # Surfaces
    window_bg: str
    panel_bg: str
    card_bg: str
    input_bg: str

    # Text
    text_primary: str
    text_secondary: str
    text_muted: str
    text_on_accent: str

    # Borders
    border: str
    border_light: str

    # Accent
    accent: str
    accent_hover: str
    accent_pressed: str

    # Status semantic colors
    status_done: str
    status_done_bg: str
    status_in_progress: str
    status_in_progress_bg: str
    status_pending: str
    status_pending_bg: str

    # Table
    row_hover: str
    row_selected: str
    row_alt: str
    header_bg: str

    # Danger
    danger: str
    danger_hover: str

    # Misc
    scrollbar_bg: str
    scrollbar_handle: str
    shadow: str
    is_dark: bool


def detect_dark_mode() -> bool:
    """Return True if the system palette suggests a dark theme."""
    app = QApplication.instance()
    if app is None:
        return False
    palette = app.palette()
    return palette.color(QPalette.Window).lightness() < 128


def light_tokens() -> ThemeTokens:
    return ThemeTokens(
        window_bg="#F5F6F8",
        panel_bg="#FFFFFF",
        card_bg="#FFFFFF",
        input_bg="#FFFFFF",
        text_primary="#1A1D23",
        text_secondary="#495057",
        text_muted="#8B919A",
        text_on_accent="#FFFFFF",
        border="#E2E5EA",
        border_light="#EEF0F3",
        accent="#3366FF",
        accent_hover="#2952CC",
        accent_pressed="#1F3D99",
        status_done="#16A34A",
        status_done_bg="#DCFCE7",
        status_in_progress="#D97706",
        status_in_progress_bg="#FEF3C7",
        status_pending="#6B7280",
        status_pending_bg="#F1F3F5",
        row_hover="#F0F4FF",
        row_selected="#DBEAFE",
        row_alt="#FAFBFC",
        header_bg="#F5F6F8",
        danger="#DC2626",
        danger_hover="#B91C1C",
        scrollbar_bg="#F0F0F0",
        scrollbar_handle="#C4C8CC",
        shadow="rgba(0, 0, 0, 0.06)",
        is_dark=False,
    )


def dark_tokens() -> ThemeTokens:
    return ThemeTokens(
        window_bg="#1A1D23",
        panel_bg="#22262E",
        card_bg="#282D36",
        input_bg="#282D36",
        text_primary="#E4E7EC",
        text_secondary="#A0A7B4",
        text_muted="#6B7280",
        text_on_accent="#FFFFFF",
        border="#353B45",
        border_light="#2C3139",
        accent="#5B8CFF",
        accent_hover="#7BA3FF",
        accent_pressed="#4A72D4",
        status_done="#3FB950",
        status_done_bg="#1A3327",
        status_in_progress="#E5A100",
        status_in_progress_bg="#332B14",
        status_pending="#6B7280",
        status_pending_bg="#2C3139",
        row_hover="#272C35",
        row_selected="#2A3550",
        row_alt="#1E2228",
        header_bg="#1E2228",
        danger="#EF4444",
        danger_hover="#F87171",
        scrollbar_bg="#1A1D23",
        scrollbar_handle="#3C434A",
        shadow="rgba(0, 0, 0, 0.25)",
        is_dark=True,
    )


def get_tokens(is_dark: bool) -> ThemeTokens:
    return dark_tokens() if is_dark else light_tokens()


def build_stylesheet(t: ThemeTokens) -> str:
    """Generate a complete QSS stylesheet from theme tokens."""

    ghost_hover_bg = t.row_hover if t.is_dark else "#EEF0F3"
    ghost_pressed_bg = t.border if t.is_dark else "#E2E5EA"

    return f"""
/* ── Window ─────────────────────────────────────────────────────── */
QMainWindow {{
    background: {t.window_bg};
    color: {t.text_primary};
}}

/* ── Toolbar ────────────────────────────────────────────────────── */
QToolBar {{
    background: {t.panel_bg};
    border-bottom: 1px solid {t.border};
    padding: 4px 8px;
    spacing: 4px;
}}
QToolBar QToolButton {{
    background: transparent;
    color: {t.text_secondary};
    border: none;
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 12px;
}}
QToolBar QToolButton:hover {{
    background: {t.row_hover};
    color: {t.text_primary};
}}
QToolBar QToolButton:pressed {{
    background: {t.border};
    color: {t.text_primary};
}}
QToolBar::separator {{
    width: 1px;
    background: {t.border_light};
    margin: 4px 6px;
}}

/* ── Inputs ─────────────────────────────────────────────────────── */
QLineEdit {{
    background: {t.input_bg};
    color: {t.text_primary};
    border: 1px solid {t.border};
    border-radius: 6px;
    padding: 5px 10px;
    selection-background-color: {t.accent};
    selection-color: {t.text_on_accent};
}}
QLineEdit:focus {{
    border-color: {t.accent};
}}
QLineEdit#searchBox {{
    padding-left: 10px;
    min-width: 180px;
}}

QTextEdit {{
    background: {t.input_bg};
    color: {t.text_primary};
    border: 1px solid {t.border};
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: {t.accent};
    selection-color: {t.text_on_accent};
}}
QTextEdit:focus {{
    border-color: {t.accent};
}}

QComboBox {{
    background: {t.input_bg};
    color: {t.text_primary};
    border: 1px solid {t.border};
    border-radius: 6px;
    padding: 5px 10px;
    min-width: 100px;
}}
QComboBox:hover {{
    border-color: {t.accent};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {t.text_muted};
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background: {t.panel_bg};
    color: {t.text_primary};
    border: 1px solid {t.border};
    border-radius: 4px;
    padding: 4px;
    selection-background-color: {t.row_hover};
    selection-color: {t.text_primary};
    outline: none;
}}

/* ── Table ──────────────────────────────────────────────────────── */
QTableWidget {{
    background: {t.panel_bg};
    color: {t.text_primary};
    border: none;
    gridline-color: {t.border_light};
    outline: none;
    selection-background-color: {t.row_selected};
    selection-color: {t.text_primary};
    alternate-background-color: {t.row_alt};
}}
QTableWidget::item {{
    padding: 6px 10px;
    border: none;
}}
QTableWidget::item:hover {{
    background: {t.row_hover};
}}
QTableWidget::item:selected {{
    background: {t.row_selected};
    color: {t.text_primary};
}}
QHeaderView::section {{
    background: {t.header_bg};
    color: {t.text_muted};
    border: none;
    border-bottom: 2px solid {t.border};
    border-right: 1px solid {t.border_light};
    padding: 8px 10px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
}}
QHeaderView::section:last {{
    border-right: none;
}}

/* ── Tabs ───────────────────────────────────────────────────────── */
QTabWidget::pane {{
    background: {t.panel_bg};
    border: 1px solid {t.border};
    border-top: none;
    border-radius: 0px 0px 8px 8px;
}}
QTabBar::tab {{
    background: transparent;
    color: {t.text_muted};
    padding: 10px 18px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 12px;
    font-weight: 500;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    color: {t.accent};
    border-bottom-color: {t.accent};
}}
QTabBar::tab:hover:!selected {{
    color: {t.text_primary};
    background: {t.row_hover};
}}

/* ── Buttons ────────────────────────────────────────────────────── */
QPushButton {{
    background: transparent;
    color: {t.text_secondary};
    border: 1px solid {t.border};
    border-radius: 6px;
    padding: 7px 18px;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: {ghost_hover_bg};
    color: {t.text_primary};
}}
QPushButton:pressed {{
    background: {ghost_pressed_bg};
}}

QPushButton#primaryBtn {{
    background: {t.accent};
    color: {t.text_on_accent};
    border: 1px solid {t.accent};
}}
QPushButton#primaryBtn:hover {{
    background: {t.accent_hover};
    border-color: {t.accent_hover};
}}
QPushButton#primaryBtn:pressed {{
    background: {t.accent_pressed};
    border-color: {t.accent_pressed};
}}

QPushButton#dangerBtn {{
    background: transparent;
    color: {t.danger};
    border: 1px solid {t.danger};
}}
QPushButton#dangerBtn:hover {{
    background: {t.danger};
    color: {t.text_on_accent};
}}

QPushButton#probeBtn {{
    background: {t.accent};
    color: {t.text_on_accent};
    border: 1px solid {t.accent};
    padding: 10px 28px;
    font-size: 14px;
    font-weight: 600;
    border-radius: 8px;
}}
QPushButton#probeBtn:hover {{
    background: {t.accent_hover};
    border-color: {t.accent_hover};
}}
QPushButton#probeBtn:pressed {{
    background: {t.accent_pressed};
    border-color: {t.accent_pressed};
}}

/* ── Dialogs ────────────────────────────────────────────────────── */
QDialog {{
    background: {t.panel_bg};
    color: {t.text_primary};
}}
QDialog QLabel {{
    color: {t.text_secondary};
    font-size: 12px;
}}
QDialog QLabel#dialogTitle {{
    color: {t.text_primary};
    font-size: 16px;
    font-weight: 600;
}}

/* ── Text browser (detail pane) ─────────────────────────────────── */
QTextBrowser {{
    background: {t.card_bg};
    color: {t.text_primary};
    border: 1px solid {t.border_light};
    border-radius: 8px;
    padding: 12px;
}}

/* ── Status bar ─────────────────────────────────────────────────── */
QStatusBar {{
    background: {t.panel_bg};
    color: {t.text_muted};
    border-top: 1px solid {t.border};
    font-size: 11px;
    padding: 2px 8px;
}}
QStatusBar::item {{
    border: none;
}}

/* ── Splitter ───────────────────────────────────────────────────── */
QSplitter::handle {{
    background: {t.border_light};
}}
QSplitter::handle:horizontal {{
    width: 1px;
    margin: 8px 0px;
}}
QSplitter::handle:vertical {{
    height: 1px;
    margin: 0px 8px;
}}

/* ── Scrollbar ──────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {t.scrollbar_bg};
    width: 8px;
    border: none;
    border-radius: 4px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {t.scrollbar_handle};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {t.text_muted};
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {{
    background: none;
}}

QScrollBar:horizontal {{
    background: {t.scrollbar_bg};
    height: 8px;
    border: none;
    border-radius: 4px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {t.scrollbar_handle};
    border-radius: 4px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {t.text_muted};
}}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {{
    width: 0px;
}}
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {{
    background: none;
}}

/* ── Tooltip ────────────────────────────────────────────────────── */
QToolTip {{
    background: {t.card_bg};
    color: {t.text_primary};
    border: 1px solid {t.border};
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 11px;
}}

/* ── Message box ────────────────────────────────────────────────── */
QMessageBox {{
    background: {t.panel_bg};
    color: {t.text_primary};
}}
QMessageBox QLabel {{
    color: {t.text_primary};
    font-size: 13px;
}}
"""
