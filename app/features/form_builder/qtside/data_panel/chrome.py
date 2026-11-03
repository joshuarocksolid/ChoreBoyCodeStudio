"""Theme stylesheet for the Data tab and its sheets. Colours come from tokens."""

from __future__ import annotations

from app.features.form_builder.qtside.checkbox_qss import checkbox_indicators


def chrome_qss(tokens: object, root_name: str) -> str:
    width = int(getattr(tokens, "focus_border_width", 1) or 1)
    name = root_name.replace(".", "\\.")
    sheet = (
        "QWidget#%s { background: %s; color: %s; }"
        "QLabel { color: %s; background: transparent; }"
        "QLabel[fbFaint=\"true\"] { color: %s; }"
        "QLabel[fbProblem=\"warning\"] { color: %s; }"
        "QLabel[fbProblem=\"error\"] { color: %s; }"
        "QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QListWidget { color: %s; background: %s; border: 1px solid %s; }"
        "QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QListWidget:focus { border: %dpx solid %s; }"
        "QPushButton, QToolButton { color: %s; background: %s; border: 1px solid %s; padding: 4px 8px; }"
        "QPushButton:disabled, QToolButton:disabled { color: %s; }"
        "QPushButton:focus, QToolButton:focus { border: %dpx solid %s; }"
        "QCheckBox { color: %s; background: transparent; }"
        "QLabel[fbLink=\"true\"] { color: %s; }"
        "QMessageBox QLabel, QLabel#qt_msgbox_label { color: %s; background: transparent; }"
    ) % (
        name,
        tokens.panel_bg,  # type: ignore[attr-defined]
        tokens.text_primary,  # type: ignore[attr-defined]
        tokens.text_primary,  # type: ignore[attr-defined]
        tokens.text_muted,  # type: ignore[attr-defined]
        tokens.diag_warning_color,  # type: ignore[attr-defined]
        tokens.diag_error_color,  # type: ignore[attr-defined]
        tokens.text_primary,  # type: ignore[attr-defined]
        tokens.input_bg,  # type: ignore[attr-defined]
        tokens.border,  # type: ignore[attr-defined]
        width,
        tokens.accent,  # type: ignore[attr-defined]
        tokens.text_primary,  # type: ignore[attr-defined]
        tokens.input_bg,  # type: ignore[attr-defined]
        tokens.border,  # type: ignore[attr-defined]
        tokens.text_muted,  # type: ignore[attr-defined]
        width,
        tokens.accent,  # type: ignore[attr-defined]
        tokens.text_primary,  # type: ignore[attr-defined]
        tokens.accent,  # type: ignore[attr-defined]
        tokens.text_primary,  # type: ignore[attr-defined]
    )
    return sheet + checkbox_indicators(tokens)


def apply_chrome(widget: object, tokens: object) -> None:
    if tokens is None:
        return
    name = str(getattr(widget, "objectName", lambda: "")() or "formBuilder.dataChrome")
    widget.setStyleSheet(chrome_qss(tokens, name))  # type: ignore[attr-defined]
