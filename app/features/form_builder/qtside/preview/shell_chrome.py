"""Shell colours that arrived on ``Appearance.chrome``. The child has no shell."""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

from app.features.form_builder.qtside.theme.chrome import FormChrome, chrome_from_values
from app.qt.QtWidgets import QApplication, QMessageBox, QWidget

_MARKER = "/* cbcs-preview-chrome */"


def chrome_from_pairs(pairs: Sequence[Tuple[str, str]]) -> Optional[FormChrome]:
    data = {str(key): str(value) for key, value in pairs}
    if not data.get("window") or not data.get("text"):
        return None
    focus = data.get("focus_width") or "1"
    try:
        width = int(focus)
    except ValueError:
        width = 1
    return chrome_from_values(
        window=data.get("window", ""),
        panel=data.get("panel", ""),
        text=data.get("text", ""),
        muted=data.get("muted", ""),
        faint=data.get("faint", ""),
        border=data.get("border", ""),
        accent=data.get("accent", ""),
        row_hover=data.get("row_hover", ""),
        input_bg=data.get("input", ""),
        error=data.get("error", ""),
        focus_width=width,
        selected=data.get("selected", ""),
        glyph=data.get("glyph", ""),
        icon_muted=data.get("icon_muted", ""),
        is_dark=data.get("is_dark") == "1",
        is_high_contrast=data.get("is_high_contrast") == "1",
        warning=data.get("warning", ""),
        info=data.get("info", ""),
    )


def apply_shell_chrome(widget: QWidget, appearance: object, app: Optional[QApplication] = None) -> None:
    """Paint Preview chrome from the appearance. The form itself stays on the runtime palette."""
    pairs = getattr(appearance, "chrome", ()) or ()
    chrome = chrome_from_pairs(tuple(pairs))
    if chrome is None:
        return
    paint = getattr(widget, "apply_chrome", None)
    if callable(paint):
        paint(chrome)
    if app is None:
        found = QApplication.instance()
        app = found if isinstance(found, QApplication) else None
    if app is not None:
        _install_message_qss(app, chrome)
    if isinstance(widget, QMessageBox):
        widget.setStyleSheet(_message_qss(chrome))


def _install_message_qss(app: QApplication, chrome: FormChrome) -> None:
    current = app.styleSheet() or ""
    head, marker, _tail = current.partition(_MARKER)
    if marker:
        head = head.rstrip()
    sheet = head
    if sheet and not sheet.endswith("\n"):
        sheet += "\n"
    app.setStyleSheet(sheet + _MARKER + "\n" + _message_qss(chrome))


def _message_qss(chrome: FormChrome) -> str:
    return (
        "QMessageBox { background: %s; color: %s; }"
        "QMessageBox QLabel { color: %s; background: transparent; }"
        "QMessageBox QPushButton { background: %s; color: %s; border: 1px solid %s;"
        " border-radius: 5px; padding: 7px 14px; font-weight: 600; }"
        % (chrome.window, chrome.text, chrome.text, chrome.panel, chrome.text, chrome.border)
    )


__all__ = ["apply_shell_chrome", "chrome_from_pairs"]
