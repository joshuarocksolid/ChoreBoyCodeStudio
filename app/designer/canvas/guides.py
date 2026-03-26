"""Grid-snapping helpers and display utilities for canvas ergonomics."""

from __future__ import annotations

# Lightweight icon characters for widget types in tree displays.
_WIDGET_ICON_CHARS: dict[str, str] = {
    "QWidget": "\u25A1",      # □
    "QDialog": "\u25A1",      # □
    "QMainWindow": "\u25A1",  # □
    "QFrame": "\u25A0",       # ■
    "QGroupBox": "\u25A3",    # ▣
    "QTabWidget": "\u2630",   # ☰
    "QScrollArea": "\u2B13",  # ⬓
    "QLineEdit": "\u270E",    # ✎
    "QTextEdit": "\u2263",    # ≣
    "QComboBox": "\u25BE",    # ▾
    "QCheckBox": "\u2611",    # ☑
    "QRadioButton": "\u25C9", # ◉
    "QLabel": "\u24C1",       # Ⓛ
    "QPushButton": "\u25B6",  # ▶
    "QToolButton": "\u25B6",  # ▶
    "QDialogButtonBox": "\u25A4",  # ▤
    "QSpinBox": "\u2195",  # ↕
    "QDoubleSpinBox": "\u21C5",  # ⇅
    "QSlider": "\u2501",  # ━
    "QProgressBar": "\u25AD",  # ▭
    "QDateEdit": "\u2637",  # ☷
    "QTimeEdit": "\u23F2",  # ⏲
    "QDateTimeEdit": "\u23F1",  # ⏱
    "QDial": "\u25CE",  # ◎
    "QSpacerItem": "\u2B0C",  # ⬌
}


def widget_icon_char(class_name: str) -> str:
    """Return a Unicode icon character for the given widget class, or empty string."""
    return _WIDGET_ICON_CHARS.get(class_name, "")


def snap_to_grid(value: int, grid_size: int) -> int:
    """Snap integer position to nearest lower grid multiple."""
    safe_grid = max(1, int(grid_size))
    return (int(value) // safe_grid) * safe_grid


def default_snapped_geometry(*, insert_index: int, grid_size: int, class_name: str) -> dict[str, int]:
    """Generate deterministic snapped geometry for newly inserted freeform widgets."""
    base_x = 16 + insert_index * 24
    base_y = 16 + insert_index * 24
    width = 120
    height = 32
    if class_name in {"QWidget", "QFrame", "QGroupBox", "QTabWidget", "QScrollArea"}:
        width = 220
        height = 140
    return {
        "x": snap_to_grid(base_x, grid_size),
        "y": snap_to_grid(base_y, grid_size),
        "width": width,
        "height": height,
    }
