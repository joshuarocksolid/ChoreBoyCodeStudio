"""Light, dark, and high-contrast palettes. Colors come from one token table."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Tokens:
    name: str
    window: str
    panel: str
    canvas: str
    page: str
    text: str
    muted: str
    border: str
    accent: str
    accent_text: str
    accent_soft: str
    danger: str
    focus: int


THEMES = {
    "light": Tokens("light", "#f3f4f7", "#ffffff", "#e7e9ef", "#ffffff", "#1c1e24", "#5d6470", "#e1e4eb", "#3b6fe0", "#ffffff", "#e7efff", "#b42318", 1),
    "dark": Tokens("dark", "#16181d", "#1f2229", "#12141a", "#242830", "#f2f4f8", "#a7adba", "#343844", "#8eb0ff", "#0e1424", "#243049", "#ffb4ab", 1),
    "hc-light": Tokens("hc-light", "#ffffff", "#ffffff", "#ffffff", "#ffffff", "#000000", "#1a1a1a", "#000000", "#0000b0", "#ffffff", "#e8e8ff", "#8b0000", 2),
    "hc-dark": Tokens("hc-dark", "#000000", "#000000", "#000000", "#000000", "#ffffff", "#f2f2f2", "#ffffff", "#ffe14a", "#000000", "#1a1a00", "#ffb4ab", 2),
}


def tokens_for(name: str) -> Tokens:
    return THEMES.get(name, THEMES["light"])


def detect_theme(app: QApplication) -> str:
    scheme = app.styleHints().colorScheme()
    if scheme == Qt.ColorScheme.Dark:
        return "dark"
    return "light"


def apply_theme(app: QApplication, name: str) -> Tokens:
    tokens = tokens_for(name)
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(tokens.window))
    palette.setColor(QPalette.WindowText, QColor(tokens.text))
    palette.setColor(QPalette.Base, QColor(tokens.panel))
    palette.setColor(QPalette.AlternateBase, QColor(tokens.canvas))
    palette.setColor(QPalette.Text, QColor(tokens.text))
    palette.setColor(QPalette.Button, QColor(tokens.panel))
    palette.setColor(QPalette.ButtonText, QColor(tokens.text))
    palette.setColor(QPalette.Highlight, QColor(tokens.accent))
    palette.setColor(QPalette.HighlightedText, QColor(tokens.accent_text))
    palette.setColor(QPalette.PlaceholderText, QColor(tokens.muted))
    palette.setColor(QPalette.ToolTipBase, QColor(tokens.panel))
    palette.setColor(QPalette.ToolTipText, QColor(tokens.text))
    app.setPalette(palette)
    app.setStyleSheet(_qss(tokens))
    return tokens


def _qss(tokens: Tokens) -> str:
    focus = tokens.focus
    return f"""
    QMainWindow, QDialog {{
        background: {tokens.window};
        color: {tokens.text};
        font-size: 13px;
    }}
    QWidget#panel {{
        background: {tokens.panel};
    }}
    QWidget#canvasHost {{
        background: {tokens.canvas};
    }}
    QFrame#page {{
        background: {tokens.page};
        border: 1px solid {tokens.border};
        border-radius: 12px;
    }}
    QFrame#card {{
        background: {tokens.panel};
        border: 1px solid {tokens.border};
        border-radius: 12px;
    }}
    QFrame#card:hover {{
        border: 1px solid {tokens.accent};
    }}
    QLabel#title {{
        font-size: 28px;
        font-weight: 650;
    }}
    QLabel#section {{
        color: {tokens.muted};
        font-size: 11px;
        font-weight: 650;
        letter-spacing: 0.4px;
    }}
    QLabel#muted {{ color: {tokens.muted}; }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {{
        background: {tokens.panel};
        color: {tokens.text};
        border: 1px solid {tokens.border};
        border-radius: 8px;
        padding: 4px 8px;
        min-height: 22px;
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {{
        border: {focus}px solid {tokens.accent};
    }}
    QPushButton {{
        background: {tokens.panel};
        color: {tokens.text};
        border: 1px solid {tokens.border};
        border-radius: 8px;
        padding: 6px 12px;
    }}
    QPushButton:hover {{ border-color: {tokens.accent}; }}
    QPushButton:checked {{
        background: {tokens.accent_soft};
        border: {focus}px solid {tokens.accent};
    }}
    QPushButton#primary {{
        background: {tokens.accent};
        color: {tokens.accent_text};
        border: none;
        font-weight: 650;
    }}
    QToolBar {{
        background: {tokens.panel};
        border: none;
        border-bottom: 1px solid {tokens.border};
        spacing: 6px;
        padding: 6px 10px;
    }}
    QStatusBar {{
        background: {tokens.panel};
        color: {tokens.muted};
        border-top: 1px solid {tokens.border};
    }}
    QTreeWidget, QListWidget {{
        background: {tokens.panel};
        color: {tokens.text};
        border: none;
        outline: none;
    }}
    QTreeWidget::item, QListWidget::item {{
        height: 26px;
        padding-left: 4px;
        border-radius: 6px;
    }}
    QTreeWidget::item:selected, QListWidget::item:selected {{
        background: {tokens.accent_soft};
        color: {tokens.text};
    }}
    QSplitter::handle {{ background: {tokens.border}; }}
    QScrollArea {{ border: none; background: {tokens.canvas}; }}
    """
